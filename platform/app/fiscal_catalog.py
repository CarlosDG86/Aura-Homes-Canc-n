"""Catálogo de categorías de gasto (E13 · punto 2.3 del CEO).

**Vive en un módulo de Python y no en una tabla.** Es dato de referencia que
cambia con la ley, no con el usuario: así va versionado en git, es idéntico en
la base de pruebas y en la real, y un cambio de mapeo se revisa en un diff.
Una tabla con edición desde el panel permitiría que el mapeo divergiera entre
las dos bases en silencio, que es justo lo que no puede pasar con algo que va
a ver un contador.

Coste aceptado: cambiar el mapeo exige un despliegue. En este producto un
despliegue es un push, así que es asumible.

## Un catálogo, dos columnas de mapeo — no dos catálogos

México y Estados Unidos clasifican distinto, pero bifurcar el modelo por
jurisdicción sería el error caro: obligaría a clasificar cada gasto dos veces,
garantizaría que las dos clasificaciones divergieran con el tiempo, y dejaría
en el limbo a una propiedad que cambia de jurisdicción.

Con un catálogo puente, toda la ambigüedad se concentra en quince filas que un
contador revisa de una sentada, en vez de repartirse entre miles de gastos.

## Lo que este módulo NO hace

No calcula impuestos, no decide qué es deducible y no presenta nada. El
etiquetado es **orientativo** y así se imprime, en pantalla y en cada
exportación.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

#: Se estampa en cada exportación. Si el contador pregunta «¿con qué criterio
#: se clasificó esto?», la respuesta es un número que identifica un commit.
CATALOG_VERSION = "2026.1"

#: Texto obligatorio bajo cualquier resumen fiscal y en cada paquete.
#: Pendiente de que el CEO lo apruebe y su abogado lo revise (D-027).
DESCARGO = (
    "Aura registra y organiza tus datos de gastos. No da asesoría fiscal, no "
    "calcula impuestos, no determina qué es deducible, no valida ni timbra "
    "CFDI y no presenta ninguna declaración. El etiquetado SAT / IRS "
    "Schedule E es orientativo: confírmalo con tu contador."
)

JURISDICCIONES = ("MX", "US", "BOTH")


@dataclass(frozen=True)
class Categoria:
    code: str                          # estable: NUNCA se renombra
    label_es: str
    help_es: str
    irs_schedule_e: Optional[str]      # None = sin equivalencia limpia
    sat_concepto: Optional[str]
    is_capital_default: bool
    requires_receipt: bool
    sort_order: int
    active: bool = True


def _c(code, label, ayuda, irs, sat, capital, recibo, orden):
    return Categoria(code, label, ayuda, irs, sat, capital, recibo, orden)


CATEGORIAS: dict[str, Categoria] = {c.code: c for c in (
    _c("mantenimiento", "Mantenimiento y reparaciones",
       "Arreglar algo que se descompuso, sin aumentar el valor del inmueble.",
       "14 Repairs", "Mantenimiento y conservación", False, True, 10),
    _c("mejora_capital", "Mejora o remodelación (capitalizable)",
       "Añade valor o alarga la vida del inmueble. No se deduce en el año: se deprecia.",
       "18 Depreciation", "Inversión — no deducible en el ejercicio", True, True, 20),
    _c("predial", "Impuesto predial",
       "El impuesto sobre la propiedad.",
       "16 Taxes", "Impuesto predial", False, True, 30),
    _c("servicios", "Servicios (agua, luz, gas)",
       "Solo los que pagas tú, no los que paga el inquilino.",
       "17 Utilities", "Servicios", False, True, 40),
    _c("seguro", "Seguro del inmueble",
       "Primas del seguro de la vivienda.",
       "9 Insurance", "Primas de seguros", False, True, 50),
    _c("admin_cuota", "Cuota de administración o condominio",
       "La cuota mensual de la privada o el edificio.",
       "7 Cleaning and maintenance", "Mantenimiento y conservación", False, True, 60),
    _c("honorarios_admin", "Honorarios de administración",
       "Lo que le pagas a quien administra la propiedad por ti.",
       "11 Management fees", "Salarios y honorarios", False, True, 70),
    _c("honorarios_prof", "Honorarios legales y contables",
       "Abogado, contador, notario.",
       "10 Legal and other professional fees", "Honorarios profesionales", False, True, 80),
    _c("intereses_hipoteca", "Intereses de crédito hipotecario",
       "Solo los intereses, no el abono a capital.",
       "12 Mortgage interest", "Intereses reales por préstamo", False, True, 90),
    _c("publicidad", "Publicidad y promoción",
       "Anuncios para rentar el inmueble.",
       "5 Advertising", "Gastos de publicidad", False, True, 100),
    _c("comisiones", "Comisiones de arrendamiento",
       "Lo que cobra quien te consiguió al inquilino.",
       "5 Advertising", "Comisiones y mediaciones", False, True, 110),
    _c("limpieza", "Limpieza y jardinería",
       "Servicio de limpieza, jardinero, fumigación.",
       "7 Cleaning and maintenance", "Mantenimiento y conservación", False, True, 120),
    _c("suministros", "Materiales y suministros",
       "Pintura, focos, herramientas, refacciones.",
       "15 Supplies", "Materiales", False, True, 130),
    _c("viajes", "Traslados a la propiedad",
       "Gasolina, casetas o vuelos para ir a atender el inmueble.",
       "6 Auto and travel", "Gastos de traslado", False, False, 140),
    _c("otro", "Otro",
       "Lo que no cabe en las demás. Describe qué fue en la nota.",
       None, None, False, False, 999),
)}

#: Los códigos retirados NUNCA se borran de aquí: un gasto histórico tiene que
#: seguir pudiendo mostrar su etiqueta. Pasan a este diccionario con
#: `active=False`.
RETIRADOS: dict[str, Categoria] = {}


def obtener(code: str) -> Optional[Categoria]:
    return CATEGORIAS.get(code) or RETIRADOS.get(code)


def etiqueta(code: str) -> str:
    """Nombre legible de un código. Nunca falla: un código desconocido se
    muestra tal cual en vez de romper la página."""
    cat = obtener(code)
    return cat.label_es if cat else (code or "—")


def activas() -> list[Categoria]:
    return sorted((c for c in CATEGORIAS.values() if c.active),
                  key=lambda c: c.sort_order)


def es_valido(code: str) -> bool:
    cat = CATEGORIAS.get(code)
    return bool(cat and cat.active)


def mapeo(code: str, jurisdiccion: str = "MX", is_capital: bool = False) -> str:
    """Cómo se etiqueta este gasto en la jurisdicción indicada.

    `is_capital` manda sobre la categoría: una mejora capitalizable se deprecia
    aunque se haya clasificado como mantenimiento. Es la única distinción que
    las dos jurisdicciones tratan igual de distinto.
    """
    cat = obtener(code)
    if cat is None:
        return "—"
    if is_capital and jurisdiccion in ("US", "BOTH"):
        return "18 Depreciation"
    if jurisdiccion == "US":
        return cat.irs_schedule_e or "—"
    if jurisdiccion == "MX":
        return cat.sat_concepto or "—"
    # BOTH: se imprimen las dos, porque el contador de cada lado busca la suya.
    partes = [p for p in (cat.sat_concepto, cat.irs_schedule_e) if p]
    return " · ".join(partes) if partes else "—"


def columna_de(jurisdiccion: str) -> str:
    """Encabezado de la columna de mapeo, según la jurisdicción."""
    return {"US": "IRS Schedule E", "MX": "Concepto SAT",
            "BOTH": "SAT · IRS"}.get(jurisdiccion, "Concepto SAT")
