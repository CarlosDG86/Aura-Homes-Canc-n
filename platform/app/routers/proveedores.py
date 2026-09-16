"""Proveedores y adjuntos del ticket (E12 · puntos 5, 6.1 y 6.2 del CEO).

Módulo propio porque `owner_portal.py` ya pasa de 500 líneas y va a crecer con
el módulo fiscal.

## Lo que este módulo NO hace, y es deliberado

**Asignar un proveedor no le manda nada.** No le genera un enlace, no le crea
cuenta y no le da acceso a la plataforma. Es una anotación interna del
propietario. Que la plataforma pueda escribirle al proveedor es una decisión
de negocio abierta (D-028), y mandarle fotos del interior de la vivienda de un
inquilino es exactamente el tipo de cosa que no se hace por defecto.

**El inquilino no tiene ninguna ruta de comprobantes**, ni de lectura ni de
escritura. Ve las fotos del trabajo terminado; la factura, el importe y el
nombre del proveedor son asunto del propietario.

## Por qué los adjuntos van en rutas propias

`POST /owner/tickets/{id}/actualizar` es el despachador caliente: comentar,
cambiar estado, resolver, asignar. Convertirlo en `multipart` haría que cada
comentario pagara el coste de que el middleware CSRF lea el cuerpo entero en
memoria y lo vuelva a parsear. Se queda urlencoded.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .. import docstore
from ..db import get_db
from ..mockmode import (is_mock, reject_real_contact_in_text, reject_tax_id_in_mock,
                        template_context, validate_mock_optional_email,
                        validate_mock_phone)
from ..models import (Document, DocTypeEnum, MaintenanceTicket, Provider,
                      TicketCategoryEnum, TicketEvent, TicketEventTypeEnum,
                      TicketPhoto)
from ..scoping import (assert_can_assign_provider, current_account_id,
                       get_scoped_document_or_404, get_scoped_provider_or_404,
                       scoped_documents, scoped_providers, scoped_tickets)
from ..security import audit, register_template_globals
from ..strings import t
from ..uploads import MAX_PHOTOS_PER_TICKET, save_ticket_photo
from .owner_portal import _ctx, _nav_badges, _require_owner

router = APIRouter(tags=["proveedores"], include_in_schema=False)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))
register_template_globals(templates)
templates.env.globals["t"] = t

#: Oficios válidos: los nombres de las categorías de ticket que ya existen,
#: más «otro». No se crea un catálogo paralelo que pudiera divergir.
OFICIOS = tuple(c.value for c in TicketCategoryEnum) + ("otro",)

#: Fotos del propietario por ticket, repartidas entre trabajo y cierre. Van
#: aparte del cupo del inquilino: con un tope único compartido, un ticket con
#: 5 fotos del inquilino dejaba al propietario sin margen para la evidencia
#: justo en el momento de cerrar.
MAX_FOTOS_PROPIETARIO = int(os.environ.get("MAX_OWNER_PHOTOS_PER_TICKET", "10"))
MAX_FOTOS_POR_ENVIO = 3

FASES_PROPIETARIO = ("work", "closing")


def _modulo_activo(nombre: str, por_omision: str = "true") -> bool:
    return os.environ.get(nombre, por_omision).strip().lower() not in {"0", "false", "no"}


def _flash(request: Request, kind: str, message: str) -> None:
    request.session["owner_flash"] = {"kind": kind, "message": message}


# --- Directorio de proveedores (punto 5) -------------------------------------


@router.get("/owner/proveedores", response_class=HTMLResponse)
def proveedores_page(request: Request, db: Session = Depends(get_db)):
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    if not _modulo_activo("PROVIDERS_MODULE_ENABLED"):
        raise HTTPException(status_code=404, detail="No disponible")

    mostrar_archivados = request.query_params.get("archivados") == "1"
    proveedores = (scoped_providers(db, user, include_archived=mostrar_archivados)
                   .order_by(Provider.is_active.desc(), Provider.name).all())
    return templates.TemplateResponse(
        request=request, name="owner_proveedores.html",
        context=_ctx(user, request, active="proveedores", **_nav_badges(db, user),
                     proveedores=proveedores, oficios=OFICIOS,
                     mostrar_archivados=mostrar_archivados, es_mock=is_mock()),
    )


@router.post("/owner/proveedores")
def proveedores_submit(request: Request, db: Session = Depends(get_db),
                       accion: str = Form(...), proveedor_id: str = Form(""),
                       name: str = Form(""), contact_name: str = Form(""),
                       trade: str = Form(""), phone: str = Form(""),
                       email: str = Form(""), tax_id: str = Form(""),
                       notes: str = Form(""), csrf_token: str = Form("")):
    """Alta, edición, archivado, restauración, borrado y supresión de contacto.

    Una sola ruta despachada por `accion`, mismo patrón que la de tickets.
    `account_id` sale **siempre del servidor** y nunca del formulario: un
    proveedor no puede migrarse de cuenta.
    """
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    if not _modulo_activo("PROVIDERS_MODULE_ENABLED"):
        raise HTTPException(status_code=404, detail="No disponible")

    destino = RedirectResponse(url="/owner/proveedores", status_code=302)
    cuenta = current_account_id(user)   # 503 diagnosticable si falta

    if accion == "crear" or accion == "editar":
        nombre = (name or "").strip()
        if not nombre:
            _flash(request, "error", "El nombre del proveedor es obligatorio.")
            return destino
        oficio = (trade or "").strip() or None
        if oficio and oficio not in OFICIOS:
            _flash(request, "error", "Ese oficio no está en la lista.")
            return destino

        # Puerta legal D-016. El correo es opcional, así que se usa la variante
        # que tolera el campo vacío: la original lanza 400 con cadena vacía.
        validate_mock_optional_email(email)
        validate_mock_phone(phone)
        reject_tax_id_in_mock(tax_id)
        reject_real_contact_in_text(notes, "la nota del proveedor")

        if accion == "crear":
            p = Provider(account_id=cuenta, created_by_user_id=user.id)
            db.add(p)
        else:
            p = get_scoped_provider_or_404(db, user, int(proveedor_id or 0))

        p.name = nombre[:200]
        p.contact_name = (contact_name or "").strip()[:200] or None
        p.trade = oficio
        p.phone = (phone or "").strip()[:60] or None
        p.email = (email or "").strip().lower()[:200] or None
        p.tax_id = (tax_id or "").strip()[:40] or None
        p.notes = (notes or "").strip()[:2000] or None
        db.commit()
        audit(db, request, f"provider.{accion}", actor=user,
              object_type="provider", object_id=p.id)
        _flash(request, "ok", f"Proveedor «{p.name}» guardado.")
        return destino

    # El resto de acciones operan sobre uno existente.
    p = get_scoped_provider_or_404(db, user, int(proveedor_id or 0))

    if accion == "archivar":
        p.is_active = False
        p.archived_at = datetime.now(timezone.utc)
        db.commit()
        _flash(request, "ok", f"«{p.name}» ya no aparecerá al asignar, "
                              f"pero sigue visible en el historial.")

    elif accion == "restaurar":
        p.is_active = True
        p.archived_at = None
        db.commit()
        _flash(request, "ok", f"«{p.name}» vuelve a estar disponible.")

    elif accion == "eliminar":
        # El conteo lo hace la aplicación porque la base NO lo va a hacer:
        # `PRAGMA foreign_keys` está apagado, así que SQLite no impediría
        # dejar punteros muertos apuntando a un proveedor borrado.
        refs = (db.query(MaintenanceTicket).filter(
                    MaintenanceTicket.provider_id == p.id).count()
                + db.query(Document).filter(Document.provider_id == p.id).count())
        if refs:
            # Se archiva y se dice por qué. Borrarlo destruiría la identidad
            # de a quién se le pagó, que es justo lo que un auditor pide.
            p.is_active = False
            p.archived_at = datetime.now(timezone.utc)
            db.commit()
            _flash(request, "error",
                   f"«{p.name}» aparece en {refs} registro(s) —tickets o "
                   f"comprobantes—, así que se archivó en vez de borrarse. "
                   f"Borrarlo dejaría esos registros sin saber a quién se le pagó.")
        else:
            nombre = p.name
            db.delete(p)
            db.commit()
            _flash(request, "ok", f"«{nombre}» se eliminó.")
        audit(db, request, "provider.eliminar", actor=user,
              object_type="provider", object_id=p.id, meta=f"referencias={refs}")

    elif accion == "redactar":
        # Respuesta a una supresión de datos del proveedor: desaparece el
        # contacto, se conserva el nombre. Sin el nombre, el registro fiscal
        # que lo cita se queda sin decir a quién se le pagó.
        p.phone = p.email = p.tax_id = p.contact_name = None
        p.notes = None
        p.redacted_at = datetime.now(timezone.utc)
        db.commit()
        audit(db, request, "provider.redactar", actor=user,
              object_type="provider", object_id=p.id)
        _flash(request, "ok", f"Se borraron los datos de contacto de «{p.name}». "
                              f"El nombre se conserva para los registros que lo citan.")
    else:
        _flash(request, "error", "Acción no reconocida.")

    return destino


# --- Adjuntos del ticket (puntos 6.1 y 6.2) ----------------------------------


def _ticket_o_404(db, user, ticket_id: int) -> MaintenanceTicket:
    ticket = scoped_tickets(db, user).filter(
        MaintenanceTicket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return ticket


@router.post("/owner/tickets/{ticket_id}/fotos")
async def subir_fotos(ticket_id: int, request: Request,
                      db: Session = Depends(get_db),
                      fase: str = Form("work"),
                      fotos: List[UploadFile] = File(default=[]),
                      csrf_token: str = Form("")):
    """Fotos del trabajo o del cierre, tomadas con la cámara del teléfono.

    Reutiliza `save_ticket_photo` sin tocar una línea: valida por bytes con
    Pillow, re-codifica a JPEG y destruye el EXIF, incluidas las coordenadas
    GPS. Ese es exactamente el control que hace segura una foto tomada con el
    móvil dentro de la vivienda de alguien.

    Funciona **en cualquier estado, también después de resolver**, que es lo
    que pidió el CEO.
    """
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    if not _modulo_activo("TICKET_ATTACHMENTS_ENABLED"):
        raise HTTPException(status_code=404, detail="No disponible")

    # Pertenencia ANTES de leer un solo byte.
    ticket = _ticket_o_404(db, user, ticket_id)
    destino = RedirectResponse(url=f"/owner/tickets/{ticket_id}", status_code=302)

    if fase not in FASES_PROPIETARIO:
        fase = "work"

    entrantes = [f for f in (fotos or []) if f and f.filename][:MAX_FOTOS_POR_ENVIO]
    if not entrantes:
        _flash(request, "error", "No se recibió ninguna foto.")
        return destino

    ya = (db.query(TicketPhoto)
          .filter(TicketPhoto.ticket_id == ticket.id,
                  TicketPhoto.phase.in_(FASES_PROPIETARIO)).count())
    if ya + len(entrantes) > MAX_FOTOS_PROPIETARIO:
        _flash(request, "error",
               f"Máximo {MAX_FOTOS_PROPIETARIO} fotos tuyas por ticket; ya hay {ya}.")
        return destino

    guardadas = 0
    for archivo in entrantes:
        # `save_ticket_photo` ya acepta y devuelve `uploaded_by_user_id`:
        # pasárselo aquí y también en el constructor lo duplicaría.
        datos = save_ticket_photo(archivo, ticket.id, uploaded_by_user_id=user.id)
        db.add(TicketPhoto(ticket_id=ticket.id, phase=fase, **datos))
        guardadas += 1

    if guardadas:
        etiqueta = "del trabajo" if fase == "work" else "del cierre"
        db.add(TicketEvent(ticket_id=ticket.id, actor_user_id=user.id,
                           event_type=TicketEventTypeEnum.photo_added,
                           body=f"{guardadas} foto(s) {etiqueta}."))
        db.commit()
        audit(db, request, "ticket.fotos_propietario", actor=user,
              object_type="ticket", object_id=ticket.id,
              meta=f"fase={fase} n={guardadas}")
        _flash(request, "ok", f"{guardadas} foto(s) añadida(s).")
    return destino


@router.post("/owner/tickets/{ticket_id}/documentos")
async def subir_documento(ticket_id: int, request: Request,
                          db: Session = Depends(get_db),
                          documento: UploadFile = File(...),
                          tipo: str = Form("invoice"),
                          csrf_token: str = Form("")):
    """Un comprobante por envío. Punto 6.1 del CEO."""
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    if not _modulo_activo("TICKET_ATTACHMENTS_ENABLED"):
        raise HTTPException(status_code=404, detail="No disponible")

    ticket = _ticket_o_404(db, user, ticket_id)
    destino = RedirectResponse(url=f"/owner/tickets/{ticket_id}", status_code=302)

    ya = scoped_documents(db, user).filter(Document.ticket_id == ticket.id).count()
    if ya >= docstore.MAX_DOCS_PER_TICKET:
        _flash(request, "error",
               f"Máximo {docstore.MAX_DOCS_PER_TICKET} comprobantes por ticket.")
        return destino

    guardado = docstore.guardar_documento(documento, ticket.id)
    try:
        doc_type = DocTypeEnum(tipo)
    except ValueError:
        doc_type = DocTypeEnum.invoice

    ahora = datetime.now(timezone.utc)
    db.add(Document(
        ticket_id=ticket.id,
        property_id=ticket.property_id,
        account_id=getattr(user, "account_id", None),
        provider_id=ticket.provider_id,
        owner_id=user.id,
        uploaded_by_user_id=user.id,
        doc_type=doc_type,
        doc_date=ahora.date(),
        # Materializado, no calculado al leer: la exportación por año fiscal
        # filtra por aquí y un índice sobre columna es barato.
        fiscal_year=ahora.year,
        # Sella los archivos nacidos en modo pruebas. No se puede validar el
        # contenido de un PDF, así que esto es lo que permitirá purgar con
        # exactitud los comprobantes de la época de pruebas al pasar a real.
        meta="mock" if is_mock() else None,
        file_url=None,   # deprecada: estos archivos no se sirven en público
        **guardado,
    ))
    # La línea de tiempo la ve TAMBIÉN el inquilino: nada de nombre de archivo
    # ni de importe.
    db.add(TicketEvent(ticket_id=ticket.id, actor_user_id=user.id,
                       event_type=TicketEventTypeEnum.comment,
                       body="Comprobante adjuntado por el propietario."))
    db.commit()
    audit(db, request, "ticket.documento_subido", actor=user,
          object_type="ticket", object_id=ticket.id, meta=f"tipo={doc_type.value}")
    _flash(request, "ok", "Comprobante adjuntado.")
    return destino


@router.post("/owner/tickets/{ticket_id}/documentos/{doc_id}/eliminar")
def eliminar_documento(ticket_id: int, doc_id: int, request: Request,
                       db: Session = Depends(get_db), csrf_token: str = Form("")):
    """Retira un comprobante mal subido.

    Los bytes desaparecen del disco; la fila se conserva con `deleted_at`. Eso
    permite responder «aquí hubo un comprobante y se retiró tal día», que no
    es lo mismo que «nunca hubo nada».
    """
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    doc = get_scoped_document_or_404(db, user, doc_id)
    if doc.stored_path:
        docstore.borrar_bytes(doc.stored_path)
    doc.deleted_at = datetime.now(timezone.utc)
    db.commit()
    audit(db, request, "ticket.documento_eliminado", actor=user,
          object_type="document", object_id=doc.id)
    _flash(request, "ok", "Comprobante retirado.")
    return RedirectResponse(url=f"/owner/tickets/{ticket_id}", status_code=302)


@router.get("/media/documentos/{documento_id}")
def descargar_documento(documento_id: int, request: Request,
                        db: Session = Depends(get_db)):
    """Entrega endurecida. **Siempre `attachment`, jamás `inline`.**

    Un PDF servido inline se abre en el visor del navegador con el MISMO
    origen que la aplicación, y ahí la política de contenido ya no protege
    nada. Si alguien cambia esto «para previsualizar», se abre el agujero
    entero.

    Un inquilino autenticado recibe 404 y no 403: un 403 confirmaría que la
    factura existe.
    """
    from .pages import _current_user_or_none

    user = _current_user_or_none(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    doc = get_scoped_document_or_404(db, user, documento_id)
    if not doc.stored_path:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    ruta = docstore.ruta_absoluta(doc.stored_path)
    if not os.path.exists(ruta):
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    audit(db, request, "document.download", actor=user,
          object_type="document", object_id=doc.id)
    nombre = docstore.sanear_nombre(doc.file_name)
    return FileResponse(
        ruta,
        # octet-stream y no el tipo real: que el navegador no intente
        # interpretarlo por su cuenta.
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )
