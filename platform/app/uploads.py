"""Subida de fotos de tickets — endurecida según SECURITY.md §6.

Las cargas de archivo son el vector de ataque más común en una aplicación como
esta. Los controles, en orden de importancia:

1. **Re-codificar siempre.** No se guarda nunca el archivo que llegó. Se abre
   con Pillow y se vuelve a escribir como JPEG. Eso destruye de un golpe los
   archivos políglota (un JPEG que también es HTML o PHP ejecutable), las
   cargas útiles escondidas en metadatos y **las coordenadas GPS del EXIF**
   — publicar dónde vive un inquilino es una fuga de datos personales.
2. **Validar por contenido, no por extensión.** El nombre y el `Content-Type`
   los controla quien sube el archivo; los bytes no mienten.
3. **Nombre aleatorio.** Nunca se usa el nombre recibido: evita el salto de
   directorios (`../../`) y las colisiones.
4. **Fuera del árbol web.** Los archivos viven en `platform/data/uploads/` y
   solo se sirven por una ruta que comprueba permisos.
"""
from __future__ import annotations

import hashlib
import io
import os
import uuid
from typing import Optional, Tuple

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.environ.get("UPLOAD_DIR") or os.path.join(PLATFORM_ROOT, "data", "uploads")

MAX_BYTES = int(os.environ.get("UPLOAD_MAX_BYTES", str(8 * 1024 * 1024)))  # 8 MB
MAX_PHOTOS_PER_TICKET = int(os.environ.get("AI_MAX_PHOTOS_PER_TICKET", "5"))

#: Tamaño máximo del lado mayor. 1568 px es el límite útil de Claude Haiku 4.5
#: (AI_TICKET_AGENT.md §2): enviar más grande no mejora el análisis y sí cuesta
#: más tokens, así que reducir aquí ahorra dinero y espacio a la vez.
MAX_EDGE_PX = int(os.environ.get("UPLOAD_MAX_EDGE_PX", "1568"))

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

#: Tope contra bombas de descompresión: una imagen de pocos KB puede declarar
#: dimensiones enormes y agotar la memoria al abrirse.
Image.MAX_IMAGE_PIXELS = 40_000_000


def _ticket_dir(ticket_id: int) -> str:
    return os.path.join(UPLOAD_DIR, "tickets", str(ticket_id))


def resolve_stored_path(stored_path: str) -> str:
    """Ruta absoluta de una foto, garantizando que no escapa del directorio.

    `stored_path` viene de la base de datos, pero se valida igualmente: si
    alguna vez se corrompiera o alguien lograra escribir ahí, esto impide leer
    archivos arbitrarios del servidor.
    """
    base = os.path.realpath(UPLOAD_DIR)
    full = os.path.realpath(os.path.join(base, stored_path))
    if not full.startswith(base + os.sep) and full != base:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return full


def save_ticket_photo(
    upload: UploadFile, ticket_id: int, uploaded_by_user_id: Optional[int] = None
) -> dict:
    """Valida, re-codifica y guarda una foto. Devuelve los datos para `TicketPhoto`.

    Lanza `HTTPException` con un mensaje entendible si el archivo no sirve; el
    inquilino debe poder corregir el problema sin ayuda técnica.
    """
    raw = upload.file.read(MAX_BYTES + 1)
    if not raw:
        raise HTTPException(status_code=400, detail="El archivo llegó vacío.")
    if len(raw) > MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"La imagen supera el máximo de {MAX_BYTES // (1024*1024)} MB.",
        )

    # Validación por contenido: Pillow falla si los bytes no son una imagen,
    # sin importar cómo se llame el archivo ni qué Content-Type declare.
    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()  # detecta corrupción sin decodificar entero
        img = Image.open(io.BytesIO(raw))  # verify() deja la imagen inutilizable
    except (UnidentifiedImageError, OSError):
        raise HTTPException(
            status_code=400,
            detail="El archivo no es una imagen válida (se aceptan JPG, PNG o WEBP).",
        )

    if (img.format or "").upper() not in ALLOWED_FORMATS:
        raise HTTPException(status_code=400, detail="Formato no admitido. Usa JPG, PNG o WEBP.")

    # Re-codificación. `convert("RGB")` descarta transparencia y perfiles raros;
    # el resultado se escribe desde cero, así que NADA del archivo original
    # (incluido el EXIF con GPS) sobrevive.
    img = img.convert("RGB")
    img.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=82, optimize=True)
    data = out.getvalue()

    directory = _ticket_dir(ticket_id)
    os.makedirs(directory, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"  # nombre aleatorio, jamás el recibido
    with open(os.path.join(directory, filename), "wb") as fh:
        fh.write(data)

    return {
        "stored_path": os.path.join("tickets", str(ticket_id), filename).replace("\\", "/"),
        "original_name": (upload.filename or "")[:200] or None,
        "content_type": "image/jpeg",
        "bytes": len(data),
        "width": img.width,
        "height": img.height,
        "sha256": hashlib.sha256(data).hexdigest(),
        "uploaded_by_user_id": uploaded_by_user_id,
        "exif_stripped": True,
    }


def read_photo_bytes(stored_path: str) -> Tuple[bytes, str]:
    """Lee una foto ya guardada. Solo la llaman rutas que ya verificaron permisos."""
    full = resolve_stored_path(stored_path)
    if not os.path.exists(full):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    with open(full, "rb") as fh:
        return fh.read(), "image/jpeg"
