"""Cadenas de la interfaz, fuera de las plantillas (D-014).

La plataforma se queda en español por ahora, pero los textos salen del HTML
para que traducirla más adelante no obligue a reescribir 27 plantillas. Es la
mitad barata de la internacionalización: extraer al escribir cuesta poco;
extraer después de haber duplicado el número de pantallas, no.

Uso desde una plantilla, con `t` registrado como global de Jinja:

    {{ t("panel.propiedades") }}

Una clave que no existe devuelve la propia clave en vez de romper la página:
una etiqueta fea es un fallo cosmético, una plantilla rota no.
"""
from __future__ import annotations

from . import es

_IDIOMAS = {"es": es.TEXTOS}
IDIOMA_POR_OMISION = "es"


def t(clave: str, idioma: str = IDIOMA_POR_OMISION, **formato) -> str:
    textos = _IDIOMAS.get(idioma) or _IDIOMAS[IDIOMA_POR_OMISION]
    valor = textos.get(clave)
    if valor is None:
        return clave
    return valor.format(**formato) if formato else valor
