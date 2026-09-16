"""Libro de gastos y panel fiscal (E13 · puntos 2.3 y 2.4 del CEO).

«Los datos son lo que importa» — CEO. Este módulo registra y organiza; no
calcula impuestos, no decide qué es deducible y no presenta nada. El descargo
va impreso en la pantalla del año fiscal y en cada exportación.

## Trampa de orden que hay que respetar

Con `gasto_id: int` como parámetro de ruta, `/owner/gastos/nuevo` cae en la
ruta parametrizada y devuelve 422 si se declara después. **Las rutas estáticas
van primero**, igual que `/owner/tickets/reporte` va antes que
`/owner/tickets/{ticket_id}`.

## Los comprobantes reutilizan `documents`

El diseño de esta área proponía una tabla `expense_receipts` propia. Se usa
`documents` en su lugar, que E12 ya dejó con `expense_id`, `stored_path`,
`content_type`, `bytes`, `sha256` y `deleted_at`: añadir una segunda tabla
para guardar exactamente lo mismo obligaría a mantener dos pipelines de
subida, dos rutas de descarga y dos criterios de borrado. La objeción original
—que `documents` mezcla comprobantes con identificaciones de inquilinos— se
resuelve donde toca: `scoped_documents` deja fuera a los inquilinos por
completo, y ninguna ruta de este módulo los deja entrar.
"""
from __future__ import annotations

import csv
import io
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile)
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .. import docstore, fiscal, fiscal_catalog
from ..db import get_db
from ..filtros_owner import escapar_csv
from ..mockmode import is_mock, reject_real_contact_in_text, template_context
from ..models import (Account, Document, DocTypeEnum, Expense, FiscalYearClosure,
                      FxRate, MaintenanceTicket, Property, Provider)
from ..scoping import (get_owned_property_or_404, get_scoped_expense_or_404,
                       owned_properties, scoped_documents, scoped_expenses,
                       scoped_tickets)
from ..security import audit, register_template_globals
from ..strings import t
from .owner_portal import _ctx, _nav_badges, _require_owner

router = APIRouter(tags=["fiscal"], include_in_schema=False)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))
register_template_globals(templates)
templates.env.globals["t"] = t
templates.env.globals["cat"] = fiscal_catalog

TOPE_FILAS_CSV = 5000


def _modulo_activo() -> bool:
    return os.environ.get("FISCAL_MODULE_ENABLED", "true").strip().lower() \
        not in {"0", "false", "no"}


def _flash(request: Request, kind: str, message: str) -> None:
    request.session["owner_flash"] = {"kind": kind, "message": message}


def _guardia(request: Request, db: Session):
    user, resp = _require_owner(request, db)
    if resp:
        return None, resp
    if not _modulo_activo():
        raise HTTPException(status_code=404, detail="No disponible")
    return user, None


def _cuenta_de(db, user) -> Optional[Account]:
    aid = getattr(user, "account_id", None)
    return db.get(Account, aid) if aid else None


def _fecha(texto, campo="la fecha") -> date:
    try:
        return date.fromisoformat((texto or "").strip())
    except ValueError:
        raise HTTPException(status_code=400,
                            detail=f"No se entiende {campo}. Usa el formato AAAA-MM-DD.")


# --- Listado de gastos -------------------------------------------------------


@router.get("/owner/gastos", response_class=HTMLResponse)
def gastos_lista(request: Request, db: Session = Depends(get_db)):
    user, resp = _guardia(request, db)
    if resp:
        return resp

    params = request.query_params
    anio = params.get("anio")
    q = scoped_expenses(db, user)
    if anio and anio.isdigit():
        q = q.filter(Expense.tax_year == int(anio))
    if params.get("propiedad", "").isdigit():
        q = q.filter(Expense.property_id == int(params["propiedad"]))
    if params.get("categoria"):
        q = q.filter(Expense.category_code == params["categoria"])

    gastos = q.order_by(Expense.expense_date.desc(), Expense.id.desc()).limit(500).all()
    props = owned_properties(db, user).order_by(Property.id).all()
    ids = [p.id for p in props]

    return templates.TemplateResponse(
        request=request, name="owner_gastos.html",
        context=_ctx(user, request, active="gastos", **_nav_badges(db, user),
                     gastos=gastos, propiedades=props,
                     nombres={p.id: p.title for p in props},
                     categorias=fiscal_catalog.activas(),
                     anios=fiscal.anios_con_datos(db, ids),
                     filtro_anio=anio, filtro_prop=params.get("propiedad", ""),
                     filtro_cat=params.get("categoria", "")),
    )


# OJO: esta ruta ESTÁTICA va antes que `/owner/gastos/{gasto_id}`. Al revés,
# «nuevo» caería en el parámetro entero y devolvería 422.
@router.get("/owner/gastos/nuevo", response_class=HTMLResponse)
def gasto_nuevo(request: Request, db: Session = Depends(get_db)):
    user, resp = _guardia(request, db)
    if resp:
        return resp
    props = owned_properties(db, user).order_by(Property.id).all()
    cuenta = _cuenta_de(db, user)
    try:
        proveedores = db.query(Provider).filter(
            Provider.account_id == user.account_id,
            Provider.is_active.is_(True)).order_by(Provider.name).all()
    except Exception:  # noqa: BLE001 — sin cuenta todavía
        proveedores = []
    return templates.TemplateResponse(
        request=request, name="owner_gasto_form.html",
        context=_ctx(user, request, active="gastos", **_nav_badges(db, user),
                     propiedades=props, proveedores=proveedores,
                     categorias=fiscal_catalog.activas(),
                     monedas=fiscal.MONEDAS,
                     moneda_base=fiscal.moneda_base_de(db, cuenta),
                     hoy=date.today().isoformat(),
                     prop_sel=request.query_params.get("propiedad", ""),
                     ticket_sel=request.query_params.get("ticket", "")),
    )


def _crear_gasto(db, request, user, datos, archivo=None) -> Expense:
    """Alta común al formulario propio y al que cuelga de un ticket."""
    prop = get_owned_property_or_404(db, user, int(datos["property_id"]))
    cuenta = _cuenta_de(db, user)

    fecha = _fecha(datos.get("expense_date"), "la fecha del gasto")
    tax_year = fecha.year
    fiscal.exigir_year_abierto(db, getattr(user, "account_id", None), prop.id, tax_year)

    codigo = (datos.get("category_code") or "").strip()
    if not fiscal_catalog.es_valido(codigo):
        raise HTTPException(status_code=400, detail="Esa categoría no existe.")

    moneda = (datos.get("currency") or "MXN").strip().upper()
    if moneda not in fiscal.MONEDAS:
        raise HTTPException(status_code=400, detail="Moneda no admitida.")

    nota = (datos.get("note") or "").strip()[:2000] or None
    reject_real_contact_in_text(nota, "la nota del gasto")

    ticket_id = None
    if str(datos.get("ticket_id") or "").isdigit():
        # El ticket tiene que ser del propietario Y de la misma casa: si no, un
        # gasto podría acabar colgando del ticket de otra propiedad.
        tk = scoped_tickets(db, user).filter(
            MaintenanceTicket.id == int(datos["ticket_id"])).first()
        if tk is None:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")
        if tk.property_id != prop.id:
            raise HTTPException(status_code=400,
                                detail="Ese reporte es de otra propiedad.")
        ticket_id = tk.id

    proveedor_id = None
    nombre_proveedor = (datos.get("provider_name") or "").strip()[:160] or None
    if str(datos.get("provider_id") or "").isdigit():
        pv = db.query(Provider).filter(
            Provider.id == int(datos["provider_id"]),
            Provider.account_id == getattr(user, "account_id", None)).first()
        if pv is None:
            raise HTTPException(status_code=404, detail="Proveedor no encontrado")
        proveedor_id = pv.id
        # Instantánea del nombre: sobrevive a que el proveedor se borre o se
        # le supriman los datos, y un registro fiscal tiene que poder decir a
        # quién se le pagó.
        nombre_proveedor = pv.name[:160]

    gasto = Expense(
        account_id=getattr(user, "account_id", None),
        property_id=prop.id,
        ticket_id=ticket_id,
        expense_date=fecha,
        tax_year=tax_year,
        category_code=codigo,
        provider_id=proveedor_id,
        provider_name_snapshot=nombre_proveedor,
        tax_doc_ref=(datos.get("tax_doc_ref") or "").strip()[:64] or None,
        amount=fiscal.parsear_importe(datos.get("amount")),
        currency=moneda,
        base_currency=fiscal.moneda_base_de(db, cuenta),
        is_capital=str(datos.get("is_capital") or "").lower() in {"1", "true", "on", "si"},
        payment_method=(datos.get("payment_method") or "").strip()[:30] or None,
        note=nota,
        status=fiscal.CONFIRMADO,
        data_mode="mock" if is_mock() else "live",
        created_by_user_id=user.id,
    )
    fiscal.aplicar_conversion(db, gasto, getattr(user, "account_id", None))
    db.add(gasto)
    db.flush()

    if archivo is not None and getattr(archivo, "filename", None):
        _adjuntar(db, user, gasto, archivo)

    db.commit()
    audit(db, request, "expense.create", actor=user, object_type="expense",
          object_id=gasto.id, meta=f"prop={prop.id} anio={tax_year} cat={codigo}")
    return gasto


def _adjuntar(db, user, gasto: Expense, archivo: UploadFile) -> Document:
    guardado = docstore.guardar_documento(archivo, gasto.ticket_id or 0)
    doc = Document(
        expense_id=gasto.id,
        ticket_id=gasto.ticket_id,
        property_id=gasto.property_id,
        account_id=gasto.account_id,
        provider_id=gasto.provider_id,
        owner_id=user.id,
        uploaded_by_user_id=user.id,
        doc_type=DocTypeEnum.invoice,
        doc_date=gasto.expense_date,
        fiscal_year=gasto.tax_year,
        meta="mock" if is_mock() else None,
        file_url=None,
        **guardado,
    )
    db.add(doc)
    return doc


@router.post("/owner/gastos")
async def gasto_crear(request: Request, db: Session = Depends(get_db),
                      property_id: str = Form(...), expense_date: str = Form(...),
                      category_code: str = Form(...), amount: str = Form(...),
                      currency: str = Form("MXN"), provider_id: str = Form(""),
                      provider_name: str = Form(""), tax_doc_ref: str = Form(""),
                      payment_method: str = Form(""), note: str = Form(""),
                      is_capital: str = Form(""), ticket_id: str = Form(""),
                      comprobante: UploadFile = File(default=None),
                      csrf_token: str = Form("")):
    user, resp = _guardia(request, db)
    if resp:
        return resp
    gasto = _crear_gasto(db, request, user, locals(), comprobante)
    _flash(request, "ok", "Gasto registrado.")
    return RedirectResponse(url=f"/owner/gastos/{gasto.id}", status_code=302)


@router.post("/owner/tickets/{ticket_id}/gastos")
async def gasto_desde_ticket(ticket_id: int, request: Request,
                             db: Session = Depends(get_db),
                             expense_date: str = Form(...),
                             category_code: str = Form(...), amount: str = Form(...),
                             currency: str = Form("MXN"), tax_doc_ref: str = Form(""),
                             note: str = Form(""), is_capital: str = Form(""),
                             comprobante: UploadFile = File(default=None),
                             csrf_token: str = Form("")):
    """Punto 2.4: el gasto que cuelga de un reporte concreto.

    La propiedad y el proveedor se derivan del ticket **en el servidor**: si
    vinieran del formulario, un gasto podría acabar cargado a otra casa.
    """
    user, resp = _guardia(request, db)
    if resp:
        return resp
    tk = scoped_tickets(db, user).filter(MaintenanceTicket.id == ticket_id).first()
    if tk is None:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")

    datos = dict(property_id=tk.property_id, ticket_id=tk.id,
                 provider_id=tk.provider_id or "", expense_date=expense_date,
                 category_code=category_code, amount=amount, currency=currency,
                 tax_doc_ref=tax_doc_ref, note=note, is_capital=is_capital,
                 provider_name="", payment_method="")
    _crear_gasto(db, request, user, datos, comprobante)
    _flash(request, "ok", "Gasto registrado y ligado a este reporte.")
    return RedirectResponse(url=f"/owner/tickets/{ticket_id}", status_code=302)


@router.get("/owner/gastos/{gasto_id}", response_class=HTMLResponse)
def gasto_detalle(gasto_id: int, request: Request, db: Session = Depends(get_db)):
    user, resp = _guardia(request, db)
    if resp:
        return resp
    gasto = get_scoped_expense_or_404(db, user, gasto_id)
    prop = db.get(Property, gasto.property_id)
    cuenta = _cuenta_de(db, user)
    juris = fiscal.jurisdiccion_de(db, prop, cuenta)
    comprobantes = scoped_documents(db, user).filter(
        Document.expense_id == gasto.id).all()
    return templates.TemplateResponse(
        request=request, name="owner_gasto_detalle.html",
        context=_ctx(user, request, active="gastos", **_nav_badges(db, user),
                     gasto=gasto, prop=prop, comprobantes=comprobantes,
                     jurisdiccion=juris,
                     mapeo=fiscal_catalog.mapeo(gasto.category_code, juris, gasto.is_capital),
                     columna=fiscal_catalog.columna_de(juris),
                     categoria=fiscal_catalog.obtener(gasto.category_code),
                     cerrado=fiscal.esta_cerrado(db, gasto.account_id,
                                                 gasto.property_id, gasto.tax_year),
                     descargo=fiscal_catalog.DESCARGO),
    )


@router.post("/owner/gastos/{gasto_id}/actualizar")
async def gasto_actualizar(gasto_id: int, request: Request,
                           db: Session = Depends(get_db), accion: str = Form(...),
                           motivo: str = Form(""), note: str = Form(""),
                           comprobante: UploadFile = File(default=None),
                           documento_id: str = Form(""), csrf_token: str = Form("")):
    """Anular, adjuntar o retirar un comprobante. Un solo endpoint por `accion`.

    **No hay «eliminar».** Un gasto se anula con motivo: borrar la fila
    destruiría la constancia de que existió, que es justo lo que un auditor
    viene a revisar.
    """
    user, resp = _guardia(request, db)
    if resp:
        return resp
    gasto = get_scoped_expense_or_404(db, user, gasto_id)
    destino = RedirectResponse(url=f"/owner/gastos/{gasto.id}", status_code=302)

    if accion == "anular":
        fiscal.exigir_year_abierto(db, gasto.account_id, gasto.property_id, gasto.tax_year)
        razon = (motivo or "").strip()
        if not razon:
            _flash(request, "error", "Para anular un gasto hay que explicar por qué.")
            return destino
        gasto.voided_at = datetime.now(timezone.utc)
        gasto.voided_by_user_id = user.id
        gasto.voided_reason = razon[:200]
        db.commit()
        audit(db, request, "expense.void", actor=user, object_type="expense",
              object_id=gasto.id, meta=razon[:150])
        _flash(request, "ok", "Gasto anulado. Sigue en el historial con el motivo.")

    elif accion == "adjuntar":
        if not (comprobante and comprobante.filename):
            _flash(request, "error", "No se recibió ningún archivo.")
            return destino
        _adjuntar(db, user, gasto, comprobante)
        db.commit()
        audit(db, request, "expense.receipt_add", actor=user,
              object_type="expense", object_id=gasto.id)
        _flash(request, "ok", "Comprobante adjuntado.")

    elif accion == "quitar_comprobante":
        if not documento_id.isdigit():
            _flash(request, "error", "Falta el comprobante.")
            return destino
        doc = scoped_documents(db, user).filter(
            Document.id == int(documento_id),
            Document.expense_id == gasto.id).first()
        if doc is None:
            raise HTTPException(status_code=404, detail="Comprobante no encontrado")
        if doc.stored_path:
            docstore.borrar_bytes(doc.stored_path)
        doc.deleted_at = datetime.now(timezone.utc)
        db.commit()
        _flash(request, "ok", "Comprobante retirado.")

    elif accion == "nota":
        fiscal.exigir_year_abierto(db, gasto.account_id, gasto.property_id, gasto.tax_year)
        texto = (note or "").strip()[:2000] or None
        reject_real_contact_in_text(texto, "la nota del gasto")
        gasto.note = texto
        db.commit()
        _flash(request, "ok", "Nota actualizada.")
    else:
        _flash(request, "error", "Acción no reconocida.")
    return destino


@router.get("/owner/gastos/{gasto_id}/comprobante/{documento_id}")
def descargar_comprobante(gasto_id: int, documento_id: int, request: Request,
                          db: Session = Depends(get_db)):
    """Siempre como descarga, nunca abierto en el navegador. Ver `docstore`."""
    user, resp = _guardia(request, db)
    if resp:
        return resp
    get_scoped_expense_or_404(db, user, gasto_id)
    doc = scoped_documents(db, user).filter(
        Document.id == documento_id, Document.expense_id == gasto_id).first()
    if doc is None or not doc.stored_path:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")
    ruta = docstore.ruta_absoluta(doc.stored_path)
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")
    audit(db, request, "expense.receipt_download", actor=user,
          object_type="document", object_id=doc.id)
    from fastapi.responses import FileResponse
    return FileResponse(
        ruta, media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{docstore.sanear_nombre(doc.file_name)}"',
                 "X-Content-Type-Options": "nosniff",
                 "Content-Security-Policy": "sandbox"},
    )


# --- Panel del año fiscal ----------------------------------------------------


@router.get("/owner/fiscal", response_class=HTMLResponse)
def panel_fiscal(request: Request, db: Session = Depends(get_db)):
    user, resp = _guardia(request, db)
    if resp:
        return resp
    props = owned_properties(db, user).order_by(Property.id).all()
    ids = [p.id for p in props]
    anios = fiscal.anios_con_datos(db, ids)
    crudo = request.query_params.get("anio")
    anio = int(crudo) if crudo and crudo.isdigit() else (anios[0] if anios else date.today().year)

    cuenta = _cuenta_de(db, user)
    juris = fiscal.jurisdiccion_de(db, props[0], cuenta) if props else "MX"

    return templates.TemplateResponse(
        request=request, name="owner_fiscal.html",
        context=_ctx(user, request, active="fiscal", **_nav_badges(db, user),
                     anio=anio, anios=anios,
                     totales=fiscal.totales_del_anio(db, ids, anio),
                     resumen=fiscal.resumen_por_categoria(db, ids, anio, juris),
                     jurisdiccion=juris,
                     columna=fiscal_catalog.columna_de(juris),
                     cerrado=fiscal.esta_cerrado(db, getattr(user, "account_id", None),
                                                 None, anio),
                     descargo=fiscal_catalog.DESCARGO,
                     version_catalogo=fiscal_catalog.CATALOG_VERSION),
    )


@router.get("/owner/fiscal/reporte")
def reporte_fiscal(request: Request, db: Session = Depends(get_db)):
    """CSV plano del año. El paquete completo para el contador llega en E14."""
    user, resp = _guardia(request, db)
    if resp:
        return resp
    props = owned_properties(db, user).order_by(Property.id).all()
    ids = [p.id for p in props]
    nombres = {p.id: p.title for p in props}
    crudo = request.query_params.get("anio")
    anio = int(crudo) if crudo and crudo.isdigit() else date.today().year
    cuenta = _cuenta_de(db, user)
    juris = fiscal.jurisdiccion_de(db, props[0], cuenta) if props else "MX"

    gastos = (scoped_expenses(db, user)
              .filter(Expense.tax_year == anio, Expense.voided_at.is_(None))
              .order_by(Expense.expense_date).limit(TOPE_FILAS_CSV).all())
    tot = fiscal.totales_del_anio(db, ids, anio)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"Aura Homes Cancún — gastos {anio}"])
    w.writerow(["Generado", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")])
    w.writerow(["Propietario", escapar_csv(user.name)])
    w.writerow(["Jurisdicción", juris])
    w.writerow(["Versión del catálogo", fiscal_catalog.CATALOG_VERSION])
    # El hueco va ARRIBA, antes de cualquier total: quien abra esto tiene que
    # ver lo que falta antes que la cifra.
    if tot["sin_conversion"]:
        w.writerow(["AVISO", f"{tot['sin_conversion']} gasto(s) sin tipo de cambio: "
                             f"su importe convertido va VACÍO y NO suma en el total."])
    w.writerow(["Descargo", fiscal_catalog.DESCARGO])
    w.writerow([])
    w.writerow(["Fecha", "Propiedad", "Categoría", fiscal_catalog.columna_de(juris),
                "Capitalizable", "Proveedor", "Comprobante fiscal", "Importe",
                "Moneda", "Importe convertido", "Moneda base", "Tasa", "Origen tasa",
                "Nota"])
    for g in gastos:
        w.writerow([
            g.expense_date.isoformat() if g.expense_date else "",
            escapar_csv(nombres.get(g.property_id, "")),
            escapar_csv(fiscal_catalog.etiqueta(g.category_code)),
            escapar_csv(fiscal_catalog.mapeo(g.category_code, juris, g.is_capital)),
            "sí" if g.is_capital else "no",
            escapar_csv(g.provider_name_snapshot or ""),
            escapar_csv(g.tax_doc_ref or ""),
            g.amount, g.currency,
            # Vacío y no cero: un cero se sumaría y mentiría.
            g.amount_base if g.amount_base is not None else "",
            g.base_currency,
            g.fx_rate if g.fx_rate is not None else "",
            escapar_csv(g.fx_source or ""),
            escapar_csv(g.note or ""),
        ])
    w.writerow([])
    w.writerow(["TOTAL CONVERTIDO", "", "", "", "", "", "", "", "",
                tot["total"], "", "", "", ""])
    w.writerow(["  del cual capitalizable", "", "", "", "", "", "", "", "",
                tot["capital"], "", "", "", ""])

    audit(db, request, "fiscal.report.export", actor=user, object_type="report",
          meta=f"anio={anio} filas={len(gastos)} sin_fx={tot['sin_conversion']}")
    return Response(
        content="﻿" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="gastos-{anio}.csv"'},
    )


@router.post("/owner/fiscal/cierre")
def cierre_fiscal(request: Request, db: Session = Depends(get_db),
                  accion: str = Form(...), anio: str = Form(...),
                  motivo: str = Form(""), csrf_token: str = Form("")):
    """Cerrar y reabrir un año.

    Reabrir **exige motivo escrito**. La reversibilidad con huella es
    preferible a la irreversibilidad, que empuja a la gente a falsear datos
    antes que a admitir un error.
    """
    user, resp = _guardia(request, db)
    if resp:
        return resp
    if not anio.isdigit():
        raise HTTPException(status_code=400, detail="Año no válido.")
    anio_i = int(anio)
    cuenta_id = getattr(user, "account_id", None)
    destino = RedirectResponse(url=f"/owner/fiscal?anio={anio_i}", status_code=302)

    fila = (db.query(FiscalYearClosure)
            .filter(FiscalYearClosure.account_id == cuenta_id,
                    FiscalYearClosure.property_id.is_(None),
                    FiscalYearClosure.tax_year == anio_i).first())

    if accion == "cerrar":
        if fila and fila.reopened_at is None:
            _flash(request, "error", f"El año {anio_i} ya estaba cerrado.")
            return destino
        if fila:
            fila.reopened_at = None
            fila.reopen_reason = None
            fila.closed_at = datetime.now(timezone.utc)
            fila.closed_by_user_id = user.id
        else:
            db.add(FiscalYearClosure(account_id=cuenta_id, property_id=None,
                                     tax_year=anio_i,
                                     closed_at=datetime.now(timezone.utc),
                                     closed_by_user_id=user.id))
        db.commit()
        audit(db, request, "fiscal.year_close", actor=user, object_type="fiscal_year",
              object_id=anio_i)
        _flash(request, "ok", f"Año {anio_i} cerrado. Para corregir algo tendrás "
                              f"que reabrirlo explicando por qué.")

    elif accion == "reabrir":
        razon = (motivo or "").strip()
        if not razon:
            _flash(request, "error", "Para reabrir un año hay que explicar por qué. "
                                     "Queda registrado.")
            return destino
        if not fila or fila.reopened_at is not None:
            _flash(request, "error", f"El año {anio_i} no está cerrado.")
            return destino
        fila.reopened_at = datetime.now(timezone.utc)
        fila.reopened_by_user_id = user.id
        fila.reopen_reason = razon[:300]
        db.commit()
        audit(db, request, "fiscal.year_reopen", actor=user,
              object_type="fiscal_year", object_id=anio_i, meta=razon[:150])
        _flash(request, "ok", f"Año {anio_i} reabierto. El motivo quedó registrado.")
    else:
        _flash(request, "error", "Acción no reconocida.")
    return destino


# --- Tipos de cambio ---------------------------------------------------------


@router.get("/owner/fiscal/tipos-de-cambio", response_class=HTMLResponse)
def tasas_page(request: Request, db: Session = Depends(get_db)):
    user, resp = _guardia(request, db)
    if resp:
        return resp
    cuenta_id = getattr(user, "account_id", None)
    tasas = (db.query(FxRate).filter(FxRate.account_id == cuenta_id)
             .order_by(FxRate.rate_date.desc()).limit(200).all())
    return templates.TemplateResponse(
        request=request, name="owner_tipos_cambio.html",
        context=_ctx(user, request, active="fiscal", **_nav_badges(db, user),
                     tasas=tasas, monedas=fiscal.MONEDAS,
                     hoy=date.today().isoformat()),
    )


@router.post("/owner/fiscal/tipos-de-cambio")
def tasa_crear(request: Request, db: Session = Depends(get_db),
               currency_from: str = Form(...), currency_to: str = Form(...),
               rate_date: str = Form(...), rate: str = Form(...),
               source: str = Form(...), kind: str = Form("diario"),
               csrf_token: str = Form("")):
    """Alta manual de una tasa. **No hay consulta automática.**

    Una llamada saliente produciría una cifra cuyo origen no podríamos
    justificar ante un auditor, y añadiría un punto de fallo a algo que tiene
    que funcionar en marzo. El propietario elige la tasa y declara su fuente,
    y esa fuente se imprime en cada línea del reporte.
    """
    user, resp = _guardia(request, db)
    if resp:
        return resp
    desde, hacia = currency_from.strip().upper(), currency_to.strip().upper()
    if desde not in fiscal.MONEDAS or hacia not in fiscal.MONEDAS or desde == hacia:
        raise HTTPException(status_code=400, detail="Par de monedas no admitido.")
    origen = (source or "").strip()[:40]
    if not origen:
        raise HTTPException(status_code=400,
                            detail="Di de dónde sacaste la tasa: un auditor lo va a preguntar.")
    valor = fiscal.parsear_importe(rate)
    cuenta_id = getattr(user, "account_id", None)

    db.add(FxRate(account_id=cuenta_id, currency_from=desde, currency_to=hacia,
                  rate_date=_fecha(rate_date, "la fecha de la tasa"),
                  rate=valor, kind=kind if kind in ("diario", "promedio_anual") else "diario",
                  source=origen, entered_by_user_id=user.id))
    db.commit()

    tasa = (db.query(FxRate).filter(FxRate.account_id == cuenta_id)
            .order_by(FxRate.id.desc()).first())
    rellenados = fiscal.recalcular_por_tasa_nueva(db, cuenta_id, tasa)
    db.commit()
    audit(db, request, "fiscal.fx_rate_add", actor=user, object_type="fx_rate",
          object_id=tasa.id, meta=f"{desde}->{hacia} {valor} ({origen})")
    _flash(request, "ok", f"Tasa guardada."
                          + (f" Se completaron {rellenados} gasto(s) que estaban sin convertir."
                             if rellenados else ""))
    return RedirectResponse(url="/owner/fiscal/tipos-de-cambio", status_code=302)
