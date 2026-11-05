"""Geometría de las gráficas del panel (orden del CEO, 2026-10-14).

El CEO pidió «resúmenes visuales en vez de solo texto corrido». Esto calcula
las barras en Python y la plantilla solo dibuja un `<svg>` con atributos.

**Por qué así y no con una librería de gráficas:** la CSP de la plataforma
prohíbe el JavaScript en línea y el `style=` en línea —hay una prueba que
falla si aparecen—, así que una librería de cliente exigiría relajarla.
Una barra es un rectángulo; no vale una dependencia nueva ni un agujero en la
política de seguridad.

Los atributos `x`, `y`, `width` y `height` de un `<rect>` **no son CSS en
línea**: son atributos del propio SVG. El color va por clase.
"""
from __future__ import annotations

from decimal import Decimal

#: Altura de cada barra horizontal y separación entre ellas, en píxeles.
ALTO_BARRA = 26
SEPARACION = 10
#: Ancho del lienzo. El SVG se escala al contenedor con `viewBox`, así que
#: esto es proporción, no tamaño final en pantalla.
ANCHO = 520
#: Espacio reservado a la izquierda para la etiqueta de cada barra.
ANCHO_ETIQUETA = 190


def _num(valor) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def barras_horizontales(filas: list, etiqueta="etiqueta", valor="total") -> dict:
    """Barras de izquierda a derecha, una por fila. Para categorías y casas.

    Devuelve el lienzo completo —alto incluido— para que la plantilla no
    tenga que calcular nada. Si todo vale cero, las barras salen vacías en
    vez de dividir entre cero.
    """
    datos = [(str(f.get(etiqueta, "")), _num(f.get(valor))) for f in filas]
    maximo = max((v for _, v in datos), default=0.0)
    util = ANCHO - ANCHO_ETIQUETA - 70        # hueco final para la cifra
    barras = []
    for i, (texto, v) in enumerate(datos):
        ancho = int(util * (v / maximo)) if maximo > 0 else 0
        barras.append({
            "etiqueta": texto,
            "valor": v,
            "y": i * (ALTO_BARRA + SEPARACION),
            "ancho": max(ancho, 2 if v > 0 else 0),
            "texto_x": ANCHO_ETIQUETA + max(ancho, 0) + 8,
        })
    return {
        "barras": barras,
        "ancho": ANCHO,
        "alto": max(len(barras) * (ALTO_BARRA + SEPARACION), ALTO_BARRA),
        "alto_barra": ALTO_BARRA,
        "x": ANCHO_ETIQUETA,
        "hay_datos": maximo > 0,
    }


MESES_CORTOS = ("Ene", "Feb", "Mar", "Abr", "May", "Jun",
                "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")


def columnas_mensuales(meses: list) -> dict:
    """Doce columnas, una por mes, incluidos los meses en cero."""
    alto = 180
    ancho_col = 38
    hueco = 8
    valores = [_num(m.get("total")) for m in meses]
    maximo = max(valores, default=0.0)
    cols = []
    for i, mes in enumerate(meses):
        v = _num(mes.get("total"))
        h = int((alto - 24) * (v / maximo)) if maximo > 0 else 0
        cols.append({
            "nombre": MESES_CORTOS[i] if i < 12 else str(i + 1),
            "x": i * (ancho_col + hueco),
            "y": alto - h,
            "alto": h,
            "ancho": ancho_col,
            "valor": v,
            "n": mes.get("n", 0),
            "centro": i * (ancho_col + hueco) + ancho_col // 2,
        })
    return {
        "columnas": cols,
        "ancho": 12 * (ancho_col + hueco),
        "alto": alto,
        "base": alto,
        "hay_datos": maximo > 0,
    }


def reparto(filas: list, valor="total") -> list:
    """Porcentaje de cada fila sobre el total, para la barra apilada.

    Devuelve enteros que suman 100 salvo redondeo; la plantilla los usa como
    ancho en porcentaje de una barra de una sola línea.
    """
    total = sum(_num(f.get(valor)) for f in filas)
    if total <= 0:
        return []
    out = []
    for f in filas:
        v = _num(f.get(valor))
        if v <= 0:
            continue
        out.append({**f, "pct": round(v * 100 / total, 1)})
    return out


def pesos(valor) -> str:
    """Formato de importe para la gráfica: sin decimales, con separador."""
    try:
        return f"{Decimal(valor or 0):,.0f}".replace(",", " ")
    except Exception:
        return "0"
