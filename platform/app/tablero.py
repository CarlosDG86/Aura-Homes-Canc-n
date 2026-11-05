"""Estados de un reporte y el tablero que los ordena (orden del CEO, 2026-10-14).

El CEO pidió ver los reportes como un **tablero por columnas** en vez de una
tabla: nuevo, en progreso, esperando al cliente y resuelto. Eso obligó a dos
cosas que viven aquí.

## 1. Un estado nuevo: «esperando al cliente»

`TicketStatusEnum` tenía tres miembros y el tablero pide cuatro. Añadir un
miembro a un enum que se guarda **por nombre** es la única operación segura
sobre un enum ya en uso: lo viejo se sigue leyendo igual. Lo que no se puede
es renombrar ni quitar, porque las filas escritas dejarían de cargar.

El riesgo real está en el otro sentido: si se despliega esta versión, alguien
mueve tickets a `esperando_cliente` y después se revierte el despliegue, esas
filas reventarían la lectura del ORM. Por eso `etiqueta()` **nunca falla** ante
un valor que no conoce — devuelve el texto crudo — y por eso ninguna consulta
pregunta por este estado con `==`: las que importan preguntan por
`!= resolved`, que lo incluye sin nombrarlo.

## 2. Las etiquetas en español, fuera de la plantilla

Antes cada pantalla imprimía `t.status.value` y el propietario leía
«in_progress». Aquí están una sola vez (D-014), listas para traducir.
"""
from __future__ import annotations

#: Valor guardado → cómo se lee en pantalla.
ETIQUETAS = {
    "open": "Nuevo",
    "in_progress": "En progreso",
    "esperando_cliente": "Esperando al cliente",
    "resolved": "Resuelto",
}

#: Las cuatro columnas del tablero, en el orden en que avanza el trabajo.
#: La clave CSS va aquí y no en la plantilla para que el color de una columna
#: y su estado no puedan divergir.
COLUMNAS = (
    ("open", "Nuevo", "nuevo"),
    ("in_progress", "En progreso", "proceso"),
    ("esperando_cliente", "Esperando al cliente", "esperando"),
    ("resolved", "Resuelto", "resuelto"),
)


def etiqueta(estado) -> str:
    """Nombre legible de un estado. Nunca falla: lo desconocido se muestra tal cual."""
    valor = getattr(estado, "value", estado)
    if valor is None:
        return "—"
    return ETIQUETAS.get(str(valor), str(valor))


def repartir(tickets: list) -> dict:
    """Agrupa los reportes por columna, respetando el orden recibido.

    Devuelve **todas** las claves aunque vengan vacías: una columna que
    desaparece cuando no tiene tarjetas rompe la lectura del tablero, que es
    justo lo que el tablero viene a arreglar.
    """
    cajas = {clave: [] for clave, _, _ in COLUMNAS}
    for t in tickets:
        valor = getattr(getattr(t, "status", None), "value", None)
        cajas.setdefault(valor if valor in cajas else "open", []).append(t)
    return cajas
