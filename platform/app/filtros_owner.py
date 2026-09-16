"""Filtros y agregados del panel del propietario (E11 · puntos 2.1 y 2.2).

Módulo sin router, a propósito: lo importan `owner_dashboard.py` y
`owner_portal.py`, y si viviera en cualquiera de los dos habría importación
circular — `owner_portal` ya importa de `pages`.

## Dos reglas que gobiernan todo lo de aquí

**Este módulo no escribe nada.** Todas sus funciones leen. Una pantalla de
solo lectura no puede ser el vector de un cambio no querido, y esa garantía es
más barata de auditar que cualquier permiso.

**Presupuesto: ≤ 8 sentencias SQL por carga, constante en el número de
propiedades, contratos y tickets.** Hay una prueba que lo verifica. Por eso
las agregaciones van con `GROUP BY` y `func.count()`, nunca con `.all()` para
contar: el panel anterior hidrataba en objetos ORM *todos* los tickets del
propietario en cada carga solo para contarlos.

**Toda agregación arranca en `properties` acotada por scoping y sale con LEFT
JOIN**, nunca al revés: con `PRAGMA foreign_keys = 0` pueden existir contratos
o tickets huérfanos apuntando a casas borradas, y contarlos desde el otro lado
daría ocupaciones por encima del 100 %.
"""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func

from .models import (Lease, LeaseStatusEnum, MaintenanceTicket, Property,
                     PropertyStatusEnum, TicketStatusEnum)
from .scoping import owned_properties

#: Tramos de metros cuadrados. Una línea para cambiarlos.
#: Aviso honesto: con la cartera real del CEO (62, 180 y 192 m²) el tramo
#: intermedio queda vacío.
TRAMOS_M2 = (("hasta80", None, 80), ("80a150", 80, 150), ("mas150", 150, None))

RECAMARAS_VALIDAS = ("1", "2", "3", "4mas", "sin-dato")
OCUPACION_VALIDA = ("ocupada", "vacante", "revisar")
SIN_DATO = "sin-dato"
SIN_ZONA = "sin-zona"

#: Tope de casas seleccionables por URL. Separa un enlace compartido de un
#: intento de volcar la cartera entera en la barra de direcciones.
MAX_SELECCION = 200

#: Tope de filas de cualquier CSV de esta área.
TOPE_FILAS_CSV = 2000


def clave_zona(z: Optional[str]) -> str:
    """Normaliza una zona para poder compararla y agrupar.

    Se hace en Python y NO en SQL porque `LOWER()` de SQLite es solo ASCII:
    comprobado contra la base real, `lower('POLÍGONO')` y `lower('Polígono')`
    **no son iguales**. Una comparación de zona insensible a mayúsculas y
    acentos no se puede escribir en SQL aquí sin una función propia o una
    columna almacenada.

    Tampoco se crea una columna `zone_key`: `Property` es espejo del JSON
    público y la sincronización sobrescribe solo las claves que espeja, así
    que una columna derivada quedaría obsoleta y el filtro empezaría a perder
    casas semanas después, en silencio. Ese es el peor fallo posible en un
    filtro.
    """
    if not z:
        return ""
    s = unicodedata.normalize("NFKD", z)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _entero(valor) -> Optional[int]:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def tramo_de(area) -> Optional[str]:
    """En qué tramo de m² cae una superficie. `None` si no hay dato."""
    if area is None:
        return None
    try:
        a = float(area)
    except (TypeError, ValueError):
        return None
    for clave, desde, hasta in TRAMOS_M2:
        if (desde is None or a > desde) and (hasta is None or a <= hasta):
            return clave
    return None


def cubeta_recamaras(n) -> Optional[str]:
    if n is None:
        return None
    return "4mas" if n >= 4 else str(n)


# --- Lectura de los parámetros ----------------------------------------------


def leer_filtros(params, zonas_validas: set) -> dict:
    """Valida por lista blanca. Un valor no reconocido se ignora y se anuncia.

    Nunca lanza y nunca interpola en SQL: un filtro con basura devuelve la
    cartera completa y un aviso, jamás un 500.
    """
    avisos = []

    def blanca(campo, permitidos):
        crudo = (params.get(campo) or "").strip()
        if not crudo:
            return None
        if crudo in permitidos:
            return crudo
        avisos.append(campo)
        return None

    zona = blanca("zona", zonas_validas | {SIN_ZONA})
    recamaras = blanca("recamaras", set(RECAMARAS_VALIDAS))
    m2 = blanca("m2", {c for c, _, _ in TRAMOS_M2} | {SIN_DATO})
    ocupacion = blanca("ocupacion", set(OCUPACION_VALIDA))

    # `prop` es repetible. Los no numéricos se descartan en silencio: vienen
    # de una URL editada a mano, no de la interfaz.
    crudos = params.getlist("prop") if hasattr(params, "getlist") else []
    seleccion = [n for n in (_entero(v) for v in crudos) if n is not None][:MAX_SELECCION]

    return {"zona": zona, "recamaras": recamaras, "m2": m2,
            "ocupacion": ocupacion, "seleccion": seleccion, "avisos": avisos}


# --- Agregados ---------------------------------------------------------------


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def cartera(db, user) -> list:
    """Las casas del propietario. UNA consulta, reutilizada por todo el panel.

    Sirve a la tabla, al desplegable de zonas, al filtro de tamaño y a la
    detección de discrepancias. Con carteras de 3 a 7 casas traerlas a memoria
    es correcto, y es lo que hace viable normalizar la zona en Python.
    """
    return owned_properties(db, user).order_by(Property.id).all()


def contratos_activos_por_casa(db, ids: list) -> dict:
    """{property_id: nº de contratos vigentes}. Una consulta agregada."""
    if not ids:
        return {}
    filas = (db.query(Lease.property_id, func.count(Lease.id))
             .filter(Lease.property_id.in_(ids),
                     Lease.status == LeaseStatusEnum.active)
             .group_by(Lease.property_id).all())
    return {pid: n for pid, n in filas}


def inquilinos_activos(db, ids: list) -> int:
    """Personas distintas con contrato vigente.

    Va en su propia consulta, y no derivado del diccionario anterior, porque
    un inquilino con dos contratos en dos casas es UNA persona.

    No sale de `scoped_users`: esa función hace el DISTINCT sobre
    `Lease.tenant_id` **sin filtrar por estado**, así que incluiría a
    ex-inquilinos y el indicador saldría inflado.
    """
    if not ids:
        return 0
    return (db.query(func.count(func.distinct(Lease.tenant_id)))
            .filter(Lease.property_id.in_(ids),
                    Lease.status == LeaseStatusEnum.active).scalar() or 0)


def tickets_por_casa(db, ids: list) -> dict:
    """{property_id: {'abiertos': n, 'emergencias': n}}. Una consulta."""
    if not ids:
        return {}
    filas = (db.query(MaintenanceTicket.property_id,
                      MaintenanceTicket.priority,
                      func.count(MaintenanceTicket.id))
             .filter(MaintenanceTicket.property_id.in_(ids),
                     MaintenanceTicket.status != TicketStatusEnum.resolved)
             .group_by(MaintenanceTicket.property_id,
                       MaintenanceTicket.priority).all())
    out = {}
    for pid, prioridad, n in filas:
        d = out.setdefault(pid, {"abiertos": 0, "emergencias": 0})
        d["abiertos"] += n
        if getattr(prioridad, "value", None) == "emergencia":
            d["emergencias"] += n
    return out


def dias_ticket_mas_viejo(db, ids: list) -> Optional[int]:
    if not ids:
        return None
    mas_viejo = (db.query(func.min(MaintenanceTicket.created_at))
                 .filter(MaintenanceTicket.property_id.in_(ids),
                         MaintenanceTicket.status != TicketStatusEnum.resolved)
                 .scalar())
    if not mas_viejo:
        return None
    if mas_viejo.tzinfo is None:
        mas_viejo = mas_viejo.replace(tzinfo=timezone.utc)
    return max(0, (_ahora() - mas_viejo).days)


def calidad_de_datos(db, ids: list) -> dict:
    """Lo que falta capturar. Dos consultas, ambas agregadas.

    No es un adorno: es lo que decide si en marzo el dato existe.
    """
    if not ids:
        return {"sin_renta": 0, "sin_fechas": 0}
    sin_renta = (db.query(func.count(Lease.id))
                 .filter(Lease.property_id.in_(ids),
                         Lease.status == LeaseStatusEnum.active,
                         Lease.monthly_rent.is_(None)).scalar() or 0)
    sin_fechas = (db.query(func.count(Lease.id))
                  .filter(Lease.property_id.in_(ids),
                          Lease.status == LeaseStatusEnum.active,
                          (Lease.start_date.is_(None) | Lease.end_date.is_(None)))
                  .scalar() or 0)
    return {"sin_renta": sin_renta, "sin_fechas": sin_fechas}


# --- Composición -------------------------------------------------------------


def estado_ocupacion(prop, n_contratos: int) -> str:
    """`ocupada`, `vacante` o `revisar`.

    `revisar` marca que lo publicado en el sitio y el contrato no dicen lo
    mismo. No se reconcilia ni se ofrece un botón de corregir: escribir
    `status` desde aquí lo revertiría la siguiente sincronización y podría
    cambiar lo que ve el público.
    """
    ocupada = n_contratos > 0
    publicada_rentada = prop.status == PropertyStatusEnum.rented
    if ocupada != publicada_rentada:
        return "revisar"
    return "ocupada" if ocupada else "vacante"


def componer(db, user, params) -> dict:
    """Todo lo que el panel necesita, en un presupuesto fijo de consultas."""
    props = cartera(db, user)
    ids = [p.id for p in props]

    zonas = {}
    for p in props:
        k = clave_zona(p.zone)
        if k:
            zonas.setdefault(k, p.zone)

    f = leer_filtros(params, set(zonas))
    contratos = contratos_activos_por_casa(db, ids)
    tickets = tickets_por_casa(db, ids)

    filas = []
    for p in props:
        n = contratos.get(p.id, 0)
        t = tickets.get(p.id, {"abiertos": 0, "emergencias": 0})
        filas.append({
            "prop": p,
            "zona_clave": clave_zona(p.zone),
            "tramo": tramo_de(p.area_m2),
            "cubeta_rec": cubeta_recamaras(p.bedrooms),
            "contratos": n,
            "ocupacion": estado_ocupacion(p, n),
            "abiertos": t["abiertos"],
            "emergencias": t["emergencias"],
        })

    visibles = [r for r in filas if _pasa(r, f)]
    seleccion_pedida = set(f["seleccion"])
    if seleccion_pedida:
        # El id ajeno simplemente desaparece: el filtro es comodidad, no
        # control de acceso — eso lo hace `owned_properties`. El aviso es
        # neutro y no confirma si la casa existe.
        visibles = [r for r in visibles if r["prop"].id in seleccion_pedida]
        f["seleccion_parcial"] = len(visibles) != len(seleccion_pedida)

    total = len(filas)
    ocupadas = sum(1 for r in filas if r["contratos"] > 0)
    calidad = calidad_de_datos(db, ids)

    return {
        "filas": filas,
        "visibles": visibles,
        "filtros": f,
        "zonas": sorted(zonas.items(), key=lambda kv: kv[1].lower()),
        "kpi": {
            "propiedades": total,
            "inquilinos": inquilinos_activos(db, ids),
            "abiertos": sum(r["abiertos"] for r in filas),
            "emergencias": sum(r["emergencias"] for r in filas),
            "ocupacion_pct": round(ocupadas * 100 / total) if total else 0,
            "vacias": total - ocupadas,
            "dias_mas_viejo": dias_ticket_mas_viejo(db, ids),
        },
        "calidad": {
            **calidad,
            "discrepancias": sum(1 for r in filas if r["ocupacion"] == "revisar"),
            "sin_zona": sum(1 for r in filas if not r["zona_clave"]),
            "sin_m2": sum(1 for r in filas if r["prop"].area_m2 is None),
            "sin_recamaras": sum(1 for r in filas if r["prop"].bedrooms is None),
        },
        "sin_contratos": ocupadas == 0 and total > 0,
    }


def _pasa(fila, f) -> bool:
    if f["zona"]:
        if f["zona"] == SIN_ZONA:
            if fila["zona_clave"]:
                return False
        elif fila["zona_clave"] != f["zona"]:
            return False
    if f["recamaras"]:
        if f["recamaras"] == SIN_DATO:
            if fila["cubeta_rec"] is not None:
                return False
        elif fila["cubeta_rec"] != f["recamaras"]:
            return False
    if f["m2"]:
        if f["m2"] == SIN_DATO:
            if fila["tramo"] is not None:
                return False
        elif fila["tramo"] != f["m2"]:
            return False
    if f["ocupacion"] and fila["ocupacion"] != f["ocupacion"]:
        return False
    return True


def descripcion_filtro(f, zonas: list) -> str:
    """El filtro en prosa, para la cabecera de procedencia del CSV.

    Un CSV filtrado que llega a un tercero no puede parecer la cartera
    completa.
    """
    partes = []
    if f["zona"]:
        nombre = dict(zonas).get(f["zona"], f["zona"])
        partes.append(f"zona: {nombre}")
    if f["recamaras"]:
        partes.append(f"recámaras: {f['recamaras']}")
    if f["m2"]:
        partes.append(f"tamaño: {f['m2']}")
    if f["ocupacion"]:
        partes.append(f"ocupación: {f['ocupacion']}")
    if f["seleccion"]:
        partes.append(f"selección manual de {len(f['seleccion'])} casa(s)")
    return "; ".join(partes) if partes else "sin filtro (cartera completa)"


def escapar_csv(valor) -> str:
    """Neutraliza una celda que Excel interpretaría como fórmula.

    Sin esto, un título de propiedad que empiece por `=` se ejecuta al abrir
    el archivo. Hoy el reporte de tickets vuelca el título crudo.
    """
    s = "" if valor is None else str(valor)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def puede_exportar(user) -> bool:
    """Único punto donde se decide quién descarga.

    Hoy devuelve True para todo el mundo: descargar los propios datos no se
    cobra (D-018). Cuando los planes tengan dientes se cambia esta función, no
    seis rutas.
    """
    return user is not None
