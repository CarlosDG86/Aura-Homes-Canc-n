"""Paquete fiscal para el contador — la «Auditors View» de D-015 (E14).

D-015 fijó que la vista de auditores **no es un rol**: es un archivo que el
propietario descarga y entrega. Nadie de fuera entra a la plataforma y
`scoping.py` no se toca para terceros.

## Qué lleva el ZIP

    LEEME.txt                  qué es, qué NO es, y el descargo
    MANIFIESTO.json            conteos, huecos y si van fotos o no
    gastos.csv                 una línea por gasto, con su tasa y su origen
    resumen_por_categoria.csv  totales con mapeo SAT e IRS lado a lado
    tickets.csv                inquilinos SEUDONIMIZADOS
    comprobantes/<gasto>/…     los archivos originales
    fotos/<ticket>/…           SOLO si se marcó la casilla
    SHA256SUMS.txt             hash de cada archivo de arriba

CSV y archivos originales, no PDF: un PDF necesitaría una dependencia nueva y
le daría al contador un documento que no puede procesar. «Los datos son lo
que importa.»

## Las cinco reglas que este módulo no negocia

1. **Nombre, correo y teléfono de un inquilino no salen nunca.** Se escribe
   `Inquilino #<id de contrato>`. El contador necesita saber que se gastaron
   4 200 pesos en plomería, no quién vive ahí.
2. **Fotos del interior: fuera por omisión.** Muestran la casa de alguien que
   no es el cliente.
3. **Sello de modo.** Una fila nacida en otro `DATA_MODE` no entra, y el
   manifiesto dice cuántas se quedaron fuera.
4. **Anti-fórmulas.** Toda celda de texto pasa por `escapar_csv`: el contador
   abre esto en Excel.
5. **El ZIP no se arma en memoria.** Se escribe a disco archivo por archivo y
   se sirve en streaming. Solo los CSV —texto, acotado por `TOPE_FILAS`— pasan
   por memoria.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from . import docstore, fiscal, fiscal_catalog, uploads
from .db import PLATFORM_ROOT
from .filtros_owner import escapar_csv
from .mockmode import data_mode, is_mock
from .models import (Document, Expense, FiscalExport, Lease, MaintenanceTicket,
                     Property, Provider, TicketPhoto, User)

TOPE_FILAS = 5000

#: Tope del paquete, sumando los archivos que se van a meter. El volumen de
#: producción es 1 GB compartido con la base y las fotos: un paquete sin tope
#: puede llenar el disco y tumbar la plataforma entera.
MAX_BYTES = int(os.environ.get("EXPORT_MAX_BYTES", str(200 * 1024 * 1024)))

MARCA_PRUEBAS = "DATOS-DE-PRUEBA"


def _resolver_directorio() -> str:
    """Separado por modo, igual que la base y las subidas.

    Un `EXPORT_DIR` explícito siempre gana: es lo que usan las pruebas.
    """
    explicito = os.environ.get("EXPORT_DIR")
    if explicito:
        return explicito
    sufijo = "exports-mock" if is_mock() else "exports"
    return os.path.join(PLATFORM_ROOT, "data", sufijo)


def directorio() -> str:
    # Se resuelve en cada llamada, no al importar: las pruebas fijan la
    # variable antes de arrancar y un valor congelado las mandaría a data/.
    ruta = _resolver_directorio()
    os.makedirs(ruta, exist_ok=True)
    return ruta


def ruta_absoluta(stored_path: str) -> str:
    """Ruta en disco de un paquete, sin salirse del directorio de exportaciones."""
    base = os.path.abspath(directorio())
    completa = os.path.abspath(os.path.join(base, stored_path))
    if not completa.startswith(base + os.sep):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Exportación no encontrada")
    return completa


class PaqueteDemasiadoGrande(Exception):
    """El paquete superaría `MAX_BYTES`: hay que exportar por propiedad."""


@dataclass
class Vista:
    """Lo que saldría, calculado SIN escribir nada.

    La pantalla de confirmación lo muestra antes de generar: quien descarga
    tiene que ver cuántas fotos de interiores está a punto de sacar.
    """
    anio: int
    propiedades: list
    gastos: list = field(default_factory=list)
    excluidos_otro_modo: int = 0
    comprobantes: list = field(default_factory=list)
    tickets: list = field(default_factory=list)
    fotos: list = field(default_factory=list)
    sin_conversion: int = 0

    @property
    def bytes_estimados(self) -> int:
        return sum(d.bytes or 0 for d in self.comprobantes)

    @property
    def bytes_fotos(self) -> int:
        return sum(f.bytes or 0 for f in self.fotos)


def calcular(db, propiedades: list, anio: int) -> Vista:
    ids = [p.id for p in propiedades]
    v = Vista(anio=anio, propiedades=propiedades)
    if not ids:
        return v

    todos = (db.query(Expense)
             .filter(Expense.property_id.in_(ids), Expense.tax_year == anio,
                     Expense.voided_at.is_(None),
                     Expense.status == fiscal.CONFIRMADO)
             .order_by(Expense.expense_date, Expense.id).limit(TOPE_FILAS).all())
    modo = data_mode()
    v.gastos = [g for g in todos if (g.data_mode or "mock") == modo]
    v.excluidos_otro_modo = len(todos) - len(v.gastos)
    v.sin_conversion = sum(1 for g in v.gastos if g.amount_base is None)

    ids_gasto = [g.id for g in v.gastos]
    if ids_gasto:
        v.comprobantes = (db.query(Document)
                          .filter(Document.expense_id.in_(ids_gasto),
                                  Document.deleted_at.is_(None),
                                  Document.stored_path.isnot(None))
                          .order_by(Document.id).all())

    # Tickets del año: los que nacieron o se resolvieron en él, más los que
    # tienen un gasto del año colgando aunque sean de antes.
    desde = datetime(anio, 1, 1)
    hasta = datetime(anio + 1, 1, 1)
    con_gasto = {g.ticket_id for g in v.gastos if g.ticket_id}
    candidatos = (db.query(MaintenanceTicket)
                  .filter(MaintenanceTicket.property_id.in_(ids))
                  .order_by(MaintenanceTicket.id).limit(TOPE_FILAS).all())
    v.tickets = [t for t in candidatos
                 if t.id in con_gasto
                 or (t.created_at and desde <= t.created_at < hasta)
                 or (t.resolved_at and desde <= t.resolved_at < hasta)]

    ids_ticket = [t.id for t in v.tickets]
    if ids_ticket:
        v.fotos = (db.query(TicketPhoto)
                   .filter(TicketPhoto.ticket_id.in_(ids_ticket))
                   .order_by(TicketPhoto.id).all())
    return v


# --- Escritura del paquete ---------------------------------------------------


def _csv(filas: list) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    for f in filas:
        w.writerow(f)
    # BOM: sin él, Excel en español abre los acentos como basura.
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _n(valor) -> str:
    return "" if valor is None else str(valor)


def _seudonimo(db, ticket, cache: dict) -> str:
    """Quién reportó, sin decir quién es.

    Con contrato: `Inquilino #<lease_id>`, estable entre exportaciones para que
    el contador pueda agrupar. Sin contrato se dice solo el papel.
    """
    if ticket.lease_id:
        return f"Inquilino #{ticket.lease_id}"
    uid = ticket.reported_by_user_id
    if uid not in cache:
        u = db.get(User, uid) if uid else None
        cache[uid] = getattr(getattr(u, "role", None), "value", None)
    rol = cache[uid]
    if rol == "owner":
        return "Propietario"
    if rol == "admin":
        return "Administración"
    return "Inquilino (sin contrato registrado)"


def _gastos_csv(db, v: Vista, juris: dict, nombres: dict, docs_por_gasto: dict) -> bytes:
    filas = [["id_gasto", "fecha", "propiedad", "jurisdiccion", "categoria",
              "codigo_categoria", "mapeo_fiscal", "capitalizable", "proveedor",
              "comprobante_fiscal", "importe", "moneda", "importe_convertido",
              "moneda_base", "tasa", "fecha_tasa", "origen_tasa", "ticket",
              "archivos_comprobante", "nota"]]
    for g in v.gastos:
        j = juris.get(g.property_id, "MX")
        filas.append([
            g.id, g.expense_date.isoformat() if g.expense_date else "",
            escapar_csv(nombres.get(g.property_id, "")), j,
            escapar_csv(fiscal_catalog.etiqueta(g.category_code)),
            escapar_csv(g.category_code),
            escapar_csv(fiscal_catalog.mapeo(g.category_code, j, g.is_capital)),
            "si" if g.is_capital else "no",
            escapar_csv(g.provider_name_snapshot or ""),
            escapar_csv(g.tax_doc_ref or ""),
            _n(g.amount), g.currency,
            # Vacío y no cero: un cero se sumaría y mentiría.
            _n(g.amount_base), g.base_currency, _n(g.fx_rate),
            g.fx_rate_date.isoformat() if g.fx_rate_date else "",
            escapar_csv(g.fx_source or ""),
            g.ticket_id or "",
            escapar_csv(" | ".join(docs_por_gasto.get(g.id, []))),
            escapar_csv(g.note or ""),
        ])
    return _csv(filas)


def _resumen_csv(v: Vista) -> bytes:
    """Una fila por categoría y tipo; SAT e IRS en columnas contiguas.

    Se calcula sobre `v.gastos` —ya filtrados por modo— y no con
    `fiscal.resumen_por_categoria`, que no sabe del sello de modo.
    """
    grupos: dict = {}
    for g in v.gastos:
        k = (g.category_code, bool(g.is_capital), g.base_currency)
        e = grupos.setdefault(k, {"n": 0, "total": Decimal("0"), "sin": 0})
        e["n"] += 1
        if g.amount_base is None:
            e["sin"] += 1
        else:
            e["total"] += Decimal(g.amount_base)
    filas = [["codigo_categoria", "categoria", "capitalizable", "linea_schedule_e_irs",
              "concepto_sat", "gastos", "sin_tipo_de_cambio", "moneda_base",
              "total_corriente", "total_capitalizable"]]
    for (codigo, cap, moneda), e in sorted(grupos.items()):
        filas.append([
            escapar_csv(codigo), escapar_csv(fiscal_catalog.etiqueta(codigo)),
            "si" if cap else "no",
            escapar_csv(fiscal_catalog.mapeo(codigo, "US", cap)),
            escapar_csv(fiscal_catalog.mapeo(codigo, "MX", cap)),
            e["n"], e["sin"], moneda,
            "" if cap else str(e["total"]),
            str(e["total"]) if cap else "",
        ])
    return _csv(filas)


def _tickets_csv(db, v: Vista, nombres: dict) -> bytes:
    """Sin descripción del inquilino: es texto libre y ahí sale de todo.

    Va el título, que es corto, y la resolución que escribió el propietario.
    """
    cache: dict = {}
    proveedores: dict = {}
    filas = [["ticket", "propiedad", "reportado_por", "titulo", "categoria",
              "prioridad", "estado", "creado", "resuelto", "proveedor", "resolucion"]]
    for t in v.tickets:
        prov = ""
        if t.provider_id:
            if t.provider_id not in proveedores:
                p = db.get(Provider, t.provider_id)
                proveedores[t.provider_id] = p.name if p else ""
            prov = proveedores[t.provider_id]
        filas.append([
            escapar_csv(t.public_ref or f"#{t.id}"),
            escapar_csv(nombres.get(t.property_id, "")),
            _seudonimo(db, t, cache),
            escapar_csv(t.title or ""),
            getattr(t.category, "value", "") or "",
            getattr(t.priority, "value", "") or "",
            getattr(t.status, "value", "") or "",
            t.created_at.strftime("%Y-%m-%d") if t.created_at else "",
            t.resolved_at.strftime("%Y-%m-%d") if t.resolved_at else "",
            escapar_csv(prov),
            escapar_csv(t.resolution_notes or ""),
        ])
    return _csv(filas)


def _leeme(v: Vista, alcance: str, fotos: bool, generado: str) -> bytes:
    prueba = is_mock()
    lineas = []
    if prueba:
        lineas += [f"*** {MARCA_PRUEBAS} ***",
                   "Este paquete salió del modo de pruebas. Nada de lo que contiene",
                   "es información fiscal real ni debe entregarse a ninguna autoridad.",
                   ""]
    lineas += [
        f"Aura Homes Cancún — paquete fiscal {v.anio}",
        f"Alcance: {alcance}",
        f"Generado: {generado}",
        "",
        "QUÉ CONTIENE",
        "  gastos.csv                 una línea por gasto confirmado y no anulado",
        "  resumen_por_categoria.csv  totales por categoría, con SAT e IRS lado a lado",
        "  tickets.csv                reportes de mantenimiento del año",
        "  comprobantes/<gasto>/      los archivos originales que se subieron",
        ("  fotos/<ticket>/            fotos de los reportes (incluidas a petición)"
         if fotos else "  (sin fotos: se excluyen por omisión)"),
        "  MANIFIESTO.json            conteos y huecos, legible por máquina",
        "  SHA256SUMS.txt             hash de cada archivo",
        "",
        "QUÉ NO ES",
        "  No es una declaración, no calcula impuestos y no decide qué es deducible.",
        "  " + fiscal_catalog.DESCARGO,
        "",
        "HUECOS",
    ]
    if v.sin_conversion:
        lineas.append(f"  {v.sin_conversion} gasto(s) sin tipo de cambio: su importe convertido "
                      f"va VACÍO y no suma.")
    else:
        lineas.append("  Todos los gastos tienen tipo de cambio.")
    if v.excluidos_otro_modo:
        lineas.append(f"  {v.excluidos_otro_modo} gasto(s) excluidos por haberse capturado en "
                      f"otro modo de datos.")
    lineas += [
        "",
        "PRIVACIDAD",
        "  Los inquilinos aparecen como «Inquilino #<número de contrato>». Nombre,",
        "  correo y teléfono no salen de la plataforma.",
        "",
        "INTEGRIDAD",
        "  SHA256SUMS.txt permite comprobar que ningún archivo cambió después de",
        "  generarse. El cierre de año de la plataforma es un control de la",
        "  aplicación, NO una inmutabilidad criptográfica.",
        "",
        f"Catálogo fiscal versión {fiscal_catalog.CATALOG_VERSION}.",
    ]
    return ("\r\n".join(lineas) + "\r\n").encode("utf-8")


def _nombre_seguro(nombre: Optional[str], respaldo: str) -> str:
    limpio = docstore.sanear_nombre(nombre or "") or respaldo
    return limpio.replace("/", "_").replace("\\", "_")


def generar(db, *, user, propiedades: list, anio: int, incluir_fotos: bool,
            propiedad_unica: Optional[Property], cuenta) -> FiscalExport:
    """Escribe el ZIP a disco y deja la fila en `fiscal_exports`.

    Escribe primero a un nombre temporal y renombra al final: un paquete a
    medias nunca queda con nombre de paquete bueno.
    """
    v = calcular(db, propiedades, anio)

    total = v.bytes_estimados + (v.bytes_fotos if incluir_fotos else 0)
    if total > MAX_BYTES:
        raise PaqueteDemasiadoGrande(
            f"El paquete ocuparía {total // (1024 * 1024)} MB y el tope es "
            f"{MAX_BYTES // (1024 * 1024)} MB. Expórtalo propiedad por propiedad"
            + ("" if not incluir_fotos else " o sin fotos") + ".")

    nombres = {p.id: p.title for p in propiedades}
    juris = {p.id: fiscal.jurisdiccion_de(db, p, cuenta) for p in propiedades}
    generado = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    alcance = (f"propiedad «{propiedad_unica.title}»" if propiedad_unica
               else f"todas las propiedades ({len(propiedades)})")

    base = directorio()
    cuenta_dir = str(getattr(cuenta, "id", None) or f"u{user.id}")
    os.makedirs(os.path.join(base, cuenta_dir), exist_ok=True)
    relativa = f"{cuenta_dir}/{uuid.uuid4().hex}.zip"
    destino = ruta_absoluta(relativa)
    temporal = destino + ".parcial"

    sumas: list = []
    docs_por_gasto: dict = {}
    n_comprobantes = 0
    n_fotos = 0

    try:
        with zipfile.ZipFile(temporal, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            def poner_bytes(nombre, datos: bytes):
                zf.writestr(nombre, datos)
                sumas.append((hashlib.sha256(datos).hexdigest(), nombre))

            def poner_archivo(nombre, ruta) -> bool:
                if not os.path.isfile(ruta):
                    return False
                h = hashlib.sha256()
                with open(ruta, "rb") as fh:
                    for bloque in iter(lambda: fh.read(1024 * 1024), b""):
                        h.update(bloque)
                zf.write(ruta, nombre)
                sumas.append((h.hexdigest(), nombre))
                return True

            # Comprobantes primero: `gastos.csv` lista qué archivo entró de
            # verdad, no qué archivo debería haber.
            for d in v.comprobantes:
                try:
                    ruta = docstore.ruta_absoluta(d.stored_path)
                except Exception:
                    continue
                nombre = f"comprobantes/{d.expense_id}/{d.id}-{_nombre_seguro(d.file_name, 'archivo')}"
                if poner_archivo(nombre, ruta):
                    n_comprobantes += 1
                    docs_por_gasto.setdefault(d.expense_id, []).append(nombre)

            if incluir_fotos:
                for f in v.fotos:
                    try:
                        ruta = uploads.resolve_stored_path(f.stored_path)
                    except Exception:
                        continue
                    ext = os.path.splitext(f.stored_path)[1] or ".jpg"
                    nombre = f"fotos/{f.ticket_id}/{f.id}-{f.phase or 'report'}{ext}"
                    if poner_archivo(nombre, ruta):
                        n_fotos += 1

            poner_bytes("gastos.csv", _gastos_csv(db, v, juris, nombres, docs_por_gasto))
            poner_bytes("resumen_por_categoria.csv", _resumen_csv(v))
            poner_bytes("tickets.csv", _tickets_csv(db, v, nombres))
            poner_bytes("LEEME.txt", _leeme(v, alcance, incluir_fotos, generado))

            manifiesto = {
                "anio": anio,
                "alcance": "propiedad" if propiedad_unica else "cuenta",
                "propiedad_id": propiedad_unica.id if propiedad_unica else None,
                "propiedades": [{"id": p.id, "titulo": p.title,
                                 "jurisdiccion": juris[p.id]} for p in propiedades],
                "moneda_base": fiscal.moneda_base_de(db, cuenta),
                "catalog_version": fiscal_catalog.CATALOG_VERSION,
                "gastos": len(v.gastos),
                "comprobantes": n_comprobantes,
                "tickets": len(v.tickets),
                "fotos_incluidas": bool(incluir_fotos),
                "fotos": n_fotos,
                "missing_fx_count": v.sin_conversion,
                "excluded_other_mode_count": v.excluidos_otro_modo,
                "data_mode": data_mode(),
                "datos_de_prueba": is_mock(),
                "generado_en": generado,
                "descargo": fiscal_catalog.DESCARGO,
            }
            poner_bytes("MANIFIESTO.json",
                        json.dumps(manifiesto, ensure_ascii=False, indent=2).encode("utf-8"))

            zf.writestr("SHA256SUMS.txt",
                        "".join(f"{h}  {n}\n" for h, n in sumas).encode("utf-8"))

        os.replace(temporal, destino)
    except BaseException:
        if os.path.exists(temporal):
            os.remove(temporal)
        raise

    h = hashlib.sha256()
    with open(destino, "rb") as fh:
        for bloque in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(bloque)

    fila = FiscalExport(
        account_id=getattr(cuenta, "id", None), owner_user_id=user.id, tax_year=anio,
        property_id=propiedad_unica.id if propiedad_unica else None,
        stored_path=relativa, bytes=os.path.getsize(destino), sha256=h.hexdigest(),
        includes_ticket_photos=bool(incluir_fotos),
        expense_count=len(v.gastos), receipt_count=n_comprobantes,
        missing_fx_count=v.sin_conversion,
        excluded_other_mode_count=v.excluidos_otro_modo,
        catalog_version=fiscal_catalog.CATALOG_VERSION, data_mode=data_mode(),
        created_by_user_id=user.id,
    )
    db.add(fila)
    db.flush()
    return fila


def nombre_de_descarga(db, fila: FiscalExport) -> str:
    """`aura-fiscal-{propiedad-N|cuenta}-{anio}-{aaaammdd}[-DATOS-DE-PRUEBA].zip`."""
    alcance = f"propiedad-{fila.property_id}" if fila.property_id else "cuenta"
    fecha = (fila.created_at or datetime.now(timezone.utc)).strftime("%Y%m%d")
    sufijo = f"-{MARCA_PRUEBAS}" if (fila.data_mode or "mock") != "live" else ""
    return f"aura-fiscal-{alcance}-{fila.tax_year}-{fecha}{sufijo}.zip"
