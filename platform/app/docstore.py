"""Comprobantes adjuntos a un ticket (E12 · punto 6.1 del CEO).

**Es el único punto del sistema donde se guarda un archivo tal como llegó.**
Las fotos se re-codifican con Pillow, lo que destruye cualquier cosa disfrazada
de imagen y borra el EXIF; un PDF o un XML no se pueden re-codificar. Por eso
toda la seguridad se traslada a dos sitios: la validación de entrada y las
cabeceras de entrega.

## Las siete reglas

1. **Sniff por bytes mágicos**, jamás por la extensión ni por el
   `Content-Type` que declara el cliente. Los dos los elige quien sube.
2. **La extensión sale del tipo detectado**, nunca del nombre recibido.
3. **El nombre en disco es un uuid.** El nombre original se guarda aparte,
   saneado, y solo se usa para mostrar y para el `filename` de la descarga.
4. **Tope de 5 MB**, con rechazo temprano antes de leer el cuerpo entero.
5. Se guarda fuera del árbol web, en `UPLOAD_DIR/docs/{ticket_id}/`.
6. **El XML se guarda como bytes opacos y NO se parsea jamás.** Eso cierra por
   construcción los ataques de entidades externas y de expansión de entidades.
   Si algún día hiciera falta leerlo: `defusedxml`, y solo `defusedxml`.
7. Se calcula y se guarda el `sha256`.

## Y una regla de entrega, que vive en la ruta

Todo comprobante se sirve **siempre como `attachment`, nunca `inline`**. Un PDF
servido inline se abre en el visor del navegador con el MISMO origen que la
aplicación, y ahí la política de contenido ya no protege nada. Si alguien
cambia eso «para previsualizar», se abre el agujero entero.
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid
from typing import Optional, Tuple

from fastapi import HTTPException, UploadFile

from .uploads import UPLOAD_DIR

#: Tope por archivo. Más bajo que el de las fotos (8 MB) a propósito: una
#: factura escaneada de 5 MB ya es generosa, y el middleware CSRF lee el
#: cuerpo multipart entero en memoria dos veces.
MAX_DOC_BYTES = int(os.environ.get("DOC_MAX_BYTES", str(5 * 1024 * 1024)))

#: Comprobantes por ticket.
MAX_DOCS_PER_TICKET = int(os.environ.get("MAX_DOCS_PER_TICKET", "5"))

#: Lo que se acepta, por tipo detectado.
#:
#: Word, Excel y ZIP quedan fuera **a propósito**: son vectores de macro y no
#: hay forma de sanearlos. Si el contador los pide, se decide entonces y se
#: escribe por qué.
TIPOS = {
    "pdf": ("application/pdf", ".pdf"),
    "xml": ("application/xml", ".xml"),
    "jpeg": ("image/jpeg", ".jpg"),
    "png": ("image/png", ".png"),
}

_NOMBRE_LIMPIO = re.compile(r"[^A-Za-z0-9._ -]")


def sanear_nombre(nombre: Optional[str]) -> str:
    """Nombre seguro para mostrar y para la cabecera de descarga.

    Se reduce a ASCII imprimible: la cabecera `Content-Disposition` no admite
    caracteres arbitrarios sin codificación adicional, y un nombre con `/` o
    `..` dentro es una invitación a escribir donde no toca.
    """
    base = os.path.basename((nombre or "").strip())[:120]
    limpio = _NOMBRE_LIMPIO.sub("_", base).strip(" .")
    return limpio or "comprobante"


def detectar_tipo(datos: bytes) -> Optional[str]:
    """Qué es esto, mirando los bytes. `None` si no se reconoce.

    No se consulta la extensión ni el `Content-Type`: los dos los controla
    quien sube el archivo, así que no son evidencia de nada.
    """
    if datos[:5] == b"%PDF-":
        return "pdf"
    if datos[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if datos[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"

    # XML: se salta el BOM y los espacios iniciales antes de mirar.
    cabeza = datos[:512]
    if cabeza[:3] == b"\xef\xbb\xbf":
        cabeza = cabeza[3:]
    cabeza = cabeza.lstrip()
    if cabeza[:5] == b"<?xml" or cabeza[:1] == b"<":
        return "xml"
    return None


def guardar_documento(archivo: UploadFile, ticket_id: int) -> dict:
    """Valida y guarda. Devuelve lo que la fila de `documents` necesita.

    Lanza 400 con un mensaje concreto ante cualquier rechazo: decir «archivo
    no válido» obliga a la persona a adivinar qué pasó.
    """
    datos = archivo.file.read(MAX_DOC_BYTES + 1)
    if not datos:
        raise HTTPException(status_code=400, detail="El archivo llegó vacío.")
    if len(datos) > MAX_DOC_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"El archivo pasa de {MAX_DOC_BYTES // (1024 * 1024)} MB.",
        )

    tipo = detectar_tipo(datos)
    if tipo is None:
        raise HTTPException(
            status_code=400,
            detail=("Solo se aceptan PDF, XML, JPG y PNG. Word, Excel y ZIP "
                    "quedan fuera a propósito: pueden llevar macros y no hay "
                    "forma de comprobar que son inofensivos."),
        )

    content_type, extension = TIPOS[tipo]
    carpeta = os.path.join(UPLOAD_DIR, "docs", str(ticket_id))
    os.makedirs(carpeta, exist_ok=True)

    # Nombre en disco = uuid. El original no toca el sistema de archivos.
    nombre_disco = f"{uuid.uuid4().hex}{extension}"
    destino = os.path.join(carpeta, nombre_disco)
    with open(destino, "wb") as fh:
        fh.write(datos)

    return {
        "stored_path": os.path.join("docs", str(ticket_id), nombre_disco),
        "file_name": sanear_nombre(archivo.filename),
        "content_type": content_type,
        "bytes": len(datos),
        "sha256": hashlib.sha256(datos).hexdigest(),
    }


def ruta_absoluta(stored_path: str) -> str:
    """Ruta en disco de un comprobante, comprobando que no se sale de sitio.

    `stored_path` sale de la base y hoy lo escribe solo esta aplicación, pero
    la comprobación va igual: es barata, y el día que alguien pueda influir en
    ese valor —una importación, una restauración— es lo único que separa una
    descarga de una lectura de cualquier archivo de la máquina.
    """
    base = os.path.abspath(UPLOAD_DIR)
    completa = os.path.abspath(os.path.join(base, stored_path))
    if not completa.startswith(base + os.sep):
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    return completa


def borrar_bytes(stored_path: str) -> bool:
    """Borra el archivo del disco. La fila se conserva con `deleted_at`.

    Los bytes desaparecen; la constancia de que el documento existió, no. Eso
    permite responder «aquí hubo un comprobante y se retiró tal día», que es
    distinto de «nunca hubo nada».
    """
    try:
        os.remove(ruta_absoluta(stored_path))
        return True
    except (OSError, HTTPException):
        return False
