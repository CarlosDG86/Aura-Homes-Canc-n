"""Lógica del libro de gastos (E13 · puntos 2.3 y 2.4 del CEO).

Módulo sin router: lo usan `routers/fiscal.py` y, más adelante, la exportación
para auditoría.

## Las tres reglas que gobiernan todo

**1. Lo capturado no se sobrescribe.** `amount` y `currency` son lo que se
pagó. La conversión se guarda aparte y congelada.

**2. Sin tasa no hay conversión inventada.** Si falta el tipo de cambio,
`amount_base` queda en NULL y el hueco se cuenta y se muestra antes de los
totales. Un reporte visiblemente incompleto es infinitamente mejor que uno
silenciosamente falso, porque el segundo se entrega sin que nadie lo revise.

**3. No se borra, se anula.** Borrar la fila destruiría la constancia de que
existió, que es justo lo que un auditor viene a revisar.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func

from . import fiscal_catalog
from .models import Account, Expense, FiscalYearClosure, FxRate, Property

#: Estados de un gasto.
CONFIRMADO = "confirmado"
BORRADOR = "borrador"

MONEDAS = ("MXN", "USD")


def jurisdiccion_de(db, prop: Property, cuenta: Optional[Account] = None) -> str:
    """Jurisdicción fiscal de una casa: la suya, la de su cuenta, o México.

    Se resuelve en cascada y no se materializa en la propiedad: así una cuenta
    que cambie de criterio no obliga a un UPDATE masivo, y una casa concreta
    puede desviarse sin inventar una excepción.
    """
    propia = (getattr(prop, "tax_jurisdiction", None) or "").strip().upper()
    if propia in fiscal_catalog.JURISDICCIONES:
        return propia
    if cuenta is None and getattr(prop, "account_id", None):
        cuenta = db.get(Account, prop.account_id)
    de_cuenta = (getattr(cuenta, "default_tax_jurisdiction", None) or "").strip().upper()
    return de_cuenta if de_cuenta in fiscal_catalog.JURISDICCIONES else "MX"


def moneda_base_de(db, cuenta: Optional[Account]) -> str:
    base = (getattr(cuenta, "base_currency", None) or "").strip().upper()
    return base if base in MONEDAS else "MXN"


# --- Dinero ------------------------------------------------------------------


def parsear_importe(texto) -> Decimal:
    """Convierte lo tecleado en un importe. Lanza 400 con un mensaje claro.

    Se usa `Decimal` y no `float` porque los importes de un reporte fiscal no
    pueden arrastrar error de redondeo. SQLite no tiene tipo decimal nativo,
    así que además se cuantiza a dos posiciones antes de guardar.
    """
    crudo = str(texto or "").strip().replace(",", "").replace("$", "").replace(" ", "")
    if not crudo:
        raise HTTPException(status_code=400, detail="Falta el importe.")
    try:
        valor = Decimal(crudo)
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400,
                            detail="El importe no se entiende. Escribe solo números, por ejemplo 1250.50")
    if valor <= 0:
        raise HTTPException(status_code=400, detail="El importe tiene que ser mayor que cero.")
    if valor >= Decimal("1000000000000"):
        raise HTTPException(status_code=400, detail="Ese importe es demasiado grande.")
    return valor.quantize(Decimal("0.01"))


def buscar_tasa(db, account_id, desde: str, hacia: str,
                cuando: date) -> Optional[FxRate]:
    """La tasa aplicable: la más reciente que no sea posterior a la fecha.

    Se busca hacia atrás y nunca hacia adelante: usar una tasa del futuro para
    convertir un gasto del pasado es exactamente el tipo de cosa que no se
    puede explicar ante un auditor.
    """
    if desde == hacia:
        return None
    q = (db.query(FxRate)
         .filter(FxRate.currency_from == desde, FxRate.currency_to == hacia,
                 FxRate.rate_date <= cuando)
         .order_by(FxRate.rate_date.desc(), FxRate.id.desc()))
    if account_id is not None:
        propia = q.filter(FxRate.account_id == account_id).first()
        if propia:
            return propia
    return q.filter(FxRate.account_id.is_(None)).first()


def aplicar_conversion(db, gasto: Expense, account_id=None) -> None:
    """Congela en la fila la conversión a moneda base.

    Si la moneda coincide con la base, la tasa es 1 y el importe se copia. Si
    difiere y no hay tasa, **se deja en NULL a propósito** y el hueco aflora en
    la pantalla y en el reporte.
    """
    if gasto.currency == gasto.base_currency:
        gasto.fx_rate = Decimal("1")
        gasto.fx_rate_date = gasto.expense_date
        gasto.fx_source = "misma moneda"
        gasto.amount_base = gasto.amount
        return

    tasa = buscar_tasa(db, account_id, gasto.currency, gasto.base_currency,
                       gasto.expense_date)
    if tasa is None:
        gasto.fx_rate = None
        gasto.fx_rate_date = None
        gasto.fx_source = None
        gasto.amount_base = None
        return

    gasto.fx_rate = tasa.rate
    gasto.fx_rate_date = tasa.rate_date
    gasto.fx_source = tasa.source
    gasto.amount_base = (Decimal(gasto.amount) * Decimal(tasa.rate)).quantize(Decimal("0.01"))


def recalcular_por_tasa_nueva(db, account_id, tasa: FxRate) -> int:
    """Al cargar una tasa, rellena los gastos que se quedaron sin conversión.

    Solo toca **años abiertos** y gastos no anulados: un año cerrado ya se
    entregó, y cambiarle las cifras después convertiría el cierre en una
    promesa vacía.
    """
    candidatos = (db.query(Expense)
                  .filter(Expense.account_id == account_id,
                          Expense.currency == tasa.currency_from,
                          Expense.base_currency == tasa.currency_to,
                          Expense.amount_base.is_(None),
                          Expense.voided_at.is_(None))
                  .all())
    tocados = 0
    for g in candidatos:
        if esta_cerrado(db, account_id, g.property_id, g.tax_year):
            continue
        antes = g.amount_base
        aplicar_conversion(db, g, account_id)
        if g.amount_base is not None and antes is None:
            tocados += 1
    return tocados


# --- Cierre de año -----------------------------------------------------------


def esta_cerrado(db, account_id, property_id, tax_year: int) -> bool:
    """¿Está cerrado este año para esta casa?

    Se consulta en el momento de escribir en vez de guardar una bandera en el
    gasto: una bandera denormalizada puede quedar desincronizada del cierre
    real, y esta consulta no cuesta nada dentro de un POST.
    """
    q = (db.query(FiscalYearClosure)
         .filter(FiscalYearClosure.tax_year == tax_year,
                 FiscalYearClosure.reopened_at.is_(None)))
    if account_id is not None:
        q = q.filter(FiscalYearClosure.account_id == account_id)
    # Un cierre con `property_id` NULL cubre toda la cuenta.
    return q.filter((FiscalYearClosure.property_id == property_id)
                    | (FiscalYearClosure.property_id.is_(None))).first() is not None


def exigir_year_abierto(db, account_id, property_id, tax_year: int) -> None:
    if esta_cerrado(db, account_id, property_id, tax_year):
        raise HTTPException(
            status_code=409,
            detail=(f"El año {tax_year} está cerrado. Para corregir algo, "
                    f"registra un asiento de ajuste o reabre el año explicando "
                    f"por qué."),
        )


# --- Agregados ---------------------------------------------------------------


def resumen_por_categoria(db, ids_propiedades: list, tax_year: int,
                          jurisdiccion: str = "MX") -> list:
    """Totales por categoría, con su mapeo fiscal y sus huecos.

    Devuelve también cuántos gastos de cada categoría se quedaron sin
    conversión: el hueco viaja junto al total, no en una nota al pie que nadie
    lee.
    """
    if not ids_propiedades:
        return []
    filas = (db.query(Expense.category_code, Expense.is_capital,
                      func.count(Expense.id),
                      func.sum(Expense.amount_base))
             .filter(Expense.property_id.in_(ids_propiedades),
                     Expense.tax_year == tax_year,
                     Expense.voided_at.is_(None),
                     Expense.status == CONFIRMADO)
             .group_by(Expense.category_code, Expense.is_capital).all())

    sin_conv = dict(
        db.query(Expense.category_code, func.count(Expense.id))
        .filter(Expense.property_id.in_(ids_propiedades),
                Expense.tax_year == tax_year,
                Expense.voided_at.is_(None),
                Expense.status == CONFIRMADO,
                Expense.amount_base.is_(None))
        .group_by(Expense.category_code).all())

    out = []
    for code, capital, n, total in filas:
        out.append({
            "code": code,
            "etiqueta": fiscal_catalog.etiqueta(code),
            "is_capital": bool(capital),
            "mapeo": fiscal_catalog.mapeo(code, jurisdiccion, bool(capital)),
            "n": n,
            "total": total or Decimal("0"),
            "sin_conversion": sin_conv.get(code, 0),
        })
    return sorted(out, key=lambda r: (-(r["total"] or 0), r["etiqueta"]))


def totales_del_anio(db, ids_propiedades: list, tax_year: int) -> dict:
    if not ids_propiedades:
        return {"n": 0, "total": Decimal("0"), "capital": Decimal("0"),
                "corriente": Decimal("0"), "sin_conversion": 0, "anulados": 0}

    base = (db.query(Expense)
            .filter(Expense.property_id.in_(ids_propiedades),
                    Expense.tax_year == tax_year))
    vivos = base.filter(Expense.voided_at.is_(None), Expense.status == CONFIRMADO)

    def suma(q):
        return q.with_entities(func.sum(Expense.amount_base)).scalar() or Decimal("0")

    return {
        "n": vivos.count(),
        "total": suma(vivos),
        "capital": suma(vivos.filter(Expense.is_capital.is_(True))),
        "corriente": suma(vivos.filter(Expense.is_capital.is_(False))),
        # El hueco se cuenta SIEMPRE y se muestra antes que los totales.
        "sin_conversion": vivos.filter(Expense.amount_base.is_(None)).count(),
        "anulados": base.filter(Expense.voided_at.isnot(None)).count(),
    }


def anios_con_datos(db, ids_propiedades: list) -> list:
    if not ids_propiedades:
        return []
    filas = (db.query(Expense.tax_year)
             .filter(Expense.property_id.in_(ids_propiedades))
             .distinct().order_by(Expense.tax_year.desc()).all())
    anios = [f[0] for f in filas]
    actual = datetime.now(timezone.utc).year
    if actual not in anios:
        anios.insert(0, actual)
    return anios


def totales_por_propiedad(db, ids_propiedades: list, tax_year: int) -> list:
    """Cuánto costó cada casa en el año. Para la pestaña «Propiedades».

    Solo suma lo convertido, igual que el resto del módulo: lo que no tiene
    tipo de cambio no entra en ningún total, y se cuenta aparte para que el
    hueco viaje al lado de la cifra.
    """
    if not ids_propiedades:
        return []
    filas = (db.query(Expense.property_id, func.count(Expense.id),
                      func.sum(Expense.amount_base))
             .filter(Expense.property_id.in_(ids_propiedades),
                     Expense.tax_year == tax_year,
                     Expense.voided_at.is_(None),
                     Expense.status == CONFIRMADO)
             .group_by(Expense.property_id).all())
    huecos = dict(
        db.query(Expense.property_id, func.count(Expense.id))
        .filter(Expense.property_id.in_(ids_propiedades),
                Expense.tax_year == tax_year,
                Expense.voided_at.is_(None),
                Expense.status == CONFIRMADO,
                Expense.amount_base.is_(None))
        .group_by(Expense.property_id).all())
    out = [{"property_id": pid, "n": n, "total": total or Decimal("0"),
            "sin_conversion": huecos.get(pid, 0)} for pid, n, total in filas]
    return sorted(out, key=lambda r: -(r["total"] or 0))


def totales_por_mes(db, ids_propiedades: list, tax_year: int) -> list:
    """Los doce meses del año, siempre los doce.

    Un mes sin gastos se devuelve en cero en vez de desaparecer: una gráfica
    a la que le faltan los meses vacíos miente sobre la forma del año.
    """
    meses = [{"mes": m, "n": 0, "total": Decimal("0")} for m in range(1, 13)]
    if not ids_propiedades:
        return meses
    filas = (db.query(Expense.expense_date, Expense.amount_base)
             .filter(Expense.property_id.in_(ids_propiedades),
                     Expense.tax_year == tax_year,
                     Expense.voided_at.is_(None),
                     Expense.status == CONFIRMADO).all())
    for fecha, importe in filas:
        if not fecha:
            continue
        casilla = meses[fecha.month - 1]
        casilla["n"] += 1
        if importe is not None:
            casilla["total"] += Decimal(importe)
    return meses
