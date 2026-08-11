"""Módulo del inquilino (fase 2b) — DESIGN.md §6.

Encendido en **modo simulación** por decisión del CEO (2026-08-08): se puede
usar y probar, pero `mockmode.py` impide capturar datos de personas reales
hasta que Legal dé el visto bueno.

Lo que puede hacer un inquilino:
- Levantar tickets con fotos (asistente AI, con formulario manual de respaldo).
- Ver el avance de sus tickets y comentar.
- Contactar a su propietario por bandeja interna, correo o WhatsApp.
- Editar sus propios datos.

Todo el filtrado por pertenencia se delega en `scoping.py`: aquí no se escribe
ni un `filter(... == user.id)` a mano.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..db import get_db
from ..mockmode import (
    template_context,
    tenant_module_enabled,
    validate_mock_phone,
    whatsapp_links_enabled,
)
from ..models import (
    Announcement,
    AnnouncementRecipient,
    Lease,
    MaintenanceTicket,
    Message,
    Property,
    RoleEnum,
    TicketCategoryEnum,
    TicketEvent,
    TicketEventTypeEnum,
    TicketPhoto,
    TicketPriorityEnum,
    TicketSourceEnum,
    TicketStatusEnum,
    User,
)
from ..scoping import owner_of_property, scoped_leases, scoped_tickets
from ..security import audit, register_template_globals
from ..uploads import MAX_PHOTOS_PER_TICKET, read_photo_bytes, save_ticket_photo
from .pages import _current_user_or_none

router = APIRouter(tags=["tenant"], include_in_schema=False)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))
register_template_globals(templates)


def _require_tenant(request: Request, db: Session):
    """Inquilino con sesión válida, o una redirección/error para devolver.

    Devuelve `(user, None)` si todo bien, o `(None, respuesta)` si hay que
    cortar. Un admin también puede entrar, para poder dar soporte.
    """
    if not tenant_module_enabled():
        return None, Response("El módulo de inquilinos está desactivado.", status_code=503)
    user = _current_user_or_none(request, db)
    if not user:
        return None, RedirectResponse(url="/login", status_code=302)
    if user.role not in (RoleEnum.tenant, RoleEnum.admin):
        return None, RedirectResponse(url="/owner", status_code=302)
    return user, None


def _ctx(request: Request, user: User, **extra) -> dict:
    ctx = {"user": user, **template_context()}
    ctx.update(extra)
    return ctx


def _active_lease(db: Session, user: User) -> Optional[Lease]:
    return scoped_leases(db, user).first()


# --- Panel ------------------------------------------------------------------


@router.get("/inquilino", response_class=HTMLResponse)
def tenant_dashboard(request: Request, db: Session = Depends(get_db)):
    user, resp = _require_tenant(request, db)
    if resp:
        return resp

    tickets = scoped_tickets(db, user).order_by(MaintenanceTicket.id.desc()).all()
    lease = _active_lease(db, user)
    prop = db.query(Property).filter(Property.id == lease.property_id).first() if lease else None
    owner = owner_of_property(db, lease.property_id) if lease else None

    return templates.TemplateResponse(
        request=request,
        name="tenant_dashboard.html",
        context=_ctx(
            request, user,
            tickets=tickets, lease=lease, prop=prop, owner=owner,
            open_count=sum(1 for t in tickets if t.status != TicketStatusEnum.resolved),
            # El teléfono que ve el inquilino es contact_phone, nunca el
            # personal del propietario (decisión del CEO, DESIGN.md §2).
            owner_phone=getattr(owner, "contact_phone", None) if owner else None,
            whatsapp_enabled=whatsapp_links_enabled(),
            **unread_counts(db, user),
        ),
    )


# --- Tickets ----------------------------------------------------------------


@router.get("/inquilino/tickets/nuevo", response_class=HTMLResponse)
def new_ticket_form(request: Request, db: Session = Depends(get_db), modo: str = ""):
    user, resp = _require_tenant(request, db)
    if resp:
        return resp

    from .. import ai_agent

    lease = _active_lease(db, user)
    if not lease:
        return templates.TemplateResponse(
            request=request, name="tenant_no_lease.html", context=_ctx(request, user)
        )

    # El asistente solo se ofrece si de verdad puede atender. Si no, se entra
    # directo al formulario manual en vez de mostrar un error.
    agent_ready = modo != "formulario" and ai_agent.is_configured() and not ai_agent.budget_exhausted(db)
    return templates.TemplateResponse(
        request=request,
        name="tenant_ticket_new.html",
        context=_ctx(
            request, user,
            lease=lease,
            agent_ready=agent_ready,
            agent_reason=None if agent_ready else "El asistente no está disponible ahora mismo; usa el formulario.",
            categories=list(TicketCategoryEnum),
            priorities=[p for p in TicketPriorityEnum if p != TicketPriorityEnum.emergencia],
            max_photos=MAX_PHOTOS_PER_TICKET,
        ),
    )


@router.post("/inquilino/tickets/nuevo", response_class=HTMLResponse)
def create_ticket(
    request: Request,
    db: Session = Depends(get_db),
    title: str = Form(...),
    description: str = Form(""),
    category: str = Form("otro"),
    priority: str = Form("media"),
    location_in_unit: str = Form(""),
    photos: List[UploadFile] = File(default=[]),
    csrf_token: str = Form(""),
):
    user, resp = _require_tenant(request, db)
    if resp:
        return resp

    lease = _active_lease(db, user)
    if not lease:
        raise HTTPException(status_code=403, detail="No tienes un arrendamiento activo.")

    # property_id sale del arrendamiento del servidor, NUNCA del formulario
    # (DESIGN.md §11): si viniera del cliente, un inquilino podría abrir
    # tickets en la casa de otro.
    try:
        cat = TicketCategoryEnum(category)
    except ValueError:
        cat = TicketCategoryEnum.otro
    try:
        pri = TicketPriorityEnum(priority)
    except ValueError:
        pri = TicketPriorityEnum.media

    # Red de seguridad: el texto puede delatar una emergencia aunque el
    # inquilino haya elegido "baja" en el desplegable.
    from ..ai_agent import apply_emergency_safety_net

    flags = apply_emergency_safety_net(f"{title} {description}", {"priority": pri.value, "is_emergency": False})
    if flags.get("is_emergency"):
        pri = TicketPriorityEnum.emergencia

    ticket = MaintenanceTicket(
        property_id=lease.property_id,
        lease_id=lease.id,
        reported_by_user_id=user.id,
        title=title.strip()[:200],
        description=(description or "").strip() or None,
        category=cat,
        priority=pri,
        location_in_unit=(location_in_unit or "").strip()[:120] or None,
        created_via=TicketSourceEnum.form,
        status=TicketStatusEnum.open,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    ticket.public_ref = f"TCK-{ticket.created_at.year if ticket.created_at else 2026}-{ticket.id:04d}"

    db.add(TicketEvent(ticket_id=ticket.id, actor_user_id=user.id,
                       event_type=TicketEventTypeEnum.created, to_status=TicketStatusEnum.open.value,
                       body=f"Ticket creado por {user.name}"))

    saved = 0
    for up in photos or []:
        if not up or not up.filename:
            continue
        if saved >= MAX_PHOTOS_PER_TICKET:
            break
        meta = save_ticket_photo(up, ticket.id, uploaded_by_user_id=user.id)
        db.add(TicketPhoto(ticket_id=ticket.id, **meta))
        saved += 1
    if saved:
        db.add(TicketEvent(ticket_id=ticket.id, actor_user_id=user.id,
                           event_type=TicketEventTypeEnum.photo_added,
                           body=f"{saved} foto(s) adjuntada(s)"))
    db.commit()

    audit(db, request, "ticket.created", actor=user, object_type="ticket", object_id=ticket.id,
          meta=f"priority={pri.value} category={cat.value}")
    return RedirectResponse(url=f"/inquilino/tickets/{ticket.id}", status_code=302)


@router.get("/inquilino/tickets/{ticket_id}", response_class=HTMLResponse)
def ticket_detail(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    user, resp = _require_tenant(request, db)
    if resp:
        return resp
    # scoped_tickets: un id ajeno da 404, sin confirmar que existe.
    ticket = scoped_tickets(db, user).filter(MaintenanceTicket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    events = db.query(TicketEvent).filter(TicketEvent.ticket_id == ticket.id).order_by(TicketEvent.id).all()
    photos = db.query(TicketPhoto).filter(TicketPhoto.ticket_id == ticket.id).all()
    return templates.TemplateResponse(
        request=request, name="tenant_ticket_detail.html",
        context=_ctx(request, user, ticket=ticket, events=events, photos=photos),
    )


@router.post("/inquilino/tickets/{ticket_id}/comentar")
def add_comment(ticket_id: int, request: Request, db: Session = Depends(get_db),
                body: str = Form(...), csrf_token: str = Form("")):
    user, resp = _require_tenant(request, db)
    if resp:
        return resp
    ticket = scoped_tickets(db, user).filter(MaintenanceTicket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    text = (body or "").strip()
    if text:
        db.add(TicketEvent(ticket_id=ticket.id, actor_user_id=user.id,
                           event_type=TicketEventTypeEnum.comment, body=text[:2000]))
        db.commit()
    return RedirectResponse(url=f"/inquilino/tickets/{ticket_id}", status_code=302)


# --- Fotos protegidas -------------------------------------------------------


@router.get("/media/tickets/{ticket_id}/{photo_id}")
def ticket_photo(ticket_id: int, photo_id: int, request: Request, db: Session = Depends(get_db)):
    """Sirve una foto solo a quien tiene derecho a verla.

    Deliberadamente NO es un `StaticFiles` público: las fotos muestran el
    interior de la vivienda de una persona. Cualquiera con la URL podría
    verlas, y las URL se filtran (historial, registros, mensajes).
    """
    user = _current_user_or_none(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    # scoped_tickets aplica la matriz de roles: el inquilino autor, el
    # propietario de esa casa y el admin. Nadie más.
    ticket = scoped_tickets(db, user).filter(MaintenanceTicket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="No encontrado")
    photo = (
        db.query(TicketPhoto)
        .filter(TicketPhoto.id == photo_id, TicketPhoto.ticket_id == ticket.id)
        .first()
    )
    if photo is None:
        raise HTTPException(status_code=404, detail="No encontrado")
    data, ctype = read_photo_bytes(photo.stored_path)
    return Response(content=data, media_type=ctype,
                    headers={"Content-Disposition": "inline", "X-Content-Type-Options": "nosniff"})


# --- Bandeja de entrada -----------------------------------------------------


def _my_owner(db: Session, user: User) -> Optional[User]:
    """El propietario de la vivienda que habita este inquilino, o None."""
    lease = _active_lease(db, user)
    return owner_of_property(db, lease.property_id) if lease else None


def unread_counts(db: Session, user: User) -> dict:
    """Mensajes y comunicados sin leer, para el indicador del panel."""
    msgs = (
        db.query(Message)
        .filter(Message.recipient_user_id == user.id, Message.read_at.is_(None))
        .count()
    )
    anns = (
        db.query(AnnouncementRecipient)
        .filter(AnnouncementRecipient.user_id == user.id,
                AnnouncementRecipient.read_at.is_(None))
        .count()
    )
    return {"unread_messages": msgs, "unread_announcements": anns, "unread_total": msgs + anns}


@router.get("/inquilino/mensajes", response_class=HTMLResponse)
def tenant_inbox(request: Request, db: Session = Depends(get_db)):
    """Bandeja: comunicados del propietario + conversación 1:1.

    Se mezclan en una sola línea de tiempo a propósito: para el inquilino son
    "cosas que me dijeron", y separarlas en dos pestañas solo obliga a revisar
    dos sitios para saber si hay algo nuevo.
    """
    user, resp = _require_tenant(request, db)
    if resp:
        return resp

    owner = _my_owner(db, user)

    # Conversación con quien sea (en la práctica, su propietario o el admin).
    messages = (
        db.query(Message)
        .filter((Message.sender_user_id == user.id) | (Message.recipient_user_id == user.id))
        .order_by(Message.id.desc())
        .all()
    )
    rows = (
        db.query(AnnouncementRecipient, Announcement)
        .join(Announcement, Announcement.id == AnnouncementRecipient.announcement_id)
        .filter(AnnouncementRecipient.user_id == user.id)
        .order_by(Announcement.id.desc())
        .all()
    )
    announcements = [{"ann": a, "rec": r} for r, a in rows]

    people = {}
    for m in messages:
        for uid in (m.sender_user_id, m.recipient_user_id):
            if uid not in people:
                u = db.query(User).filter(User.id == uid).first()
                if u:
                    people[uid] = u

    # Marcar como leído al abrir la bandeja. Se hace después de construir la
    # vista para que el usuario todavía vea resaltado lo que estaba sin leer.
    now = datetime.now(timezone.utc)
    unread_ids = [m.id for m in messages if m.recipient_user_id == user.id and m.read_at is None]
    unread_ann_ids = [x["rec"].id for x in announcements if x["rec"].read_at is None]
    if unread_ids:
        db.query(Message).filter(Message.id.in_(unread_ids)).update(
            {Message.read_at: now}, synchronize_session=False)
    if unread_ann_ids:
        db.query(AnnouncementRecipient).filter(
            AnnouncementRecipient.id.in_(unread_ann_ids)).update(
            {AnnouncementRecipient.read_at: now}, synchronize_session=False)
    if unread_ids or unread_ann_ids:
        db.commit()

    return templates.TemplateResponse(
        request=request, name="tenant_messages.html",
        context=_ctx(request, user, messages=messages, announcements=announcements,
                     people=people, owner=owner,
                     just_read_msgs=set(unread_ids), just_read_anns=set(unread_ann_ids)),
    )


@router.post("/inquilino/mensajes")
def tenant_send_message(request: Request, db: Session = Depends(get_db),
                        subject: str = Form(""), body: str = Form(...),
                        csrf_token: str = Form("")):
    """Responde a su propietario por la bandeja interna.

    El destinatario NO viene del formulario: se resuelve en el servidor a
    partir del arrendamiento activo. Así un inquilino no puede escribirle a
    un propietario que no es el suyo manipulando un campo oculto.
    """
    user, resp = _require_tenant(request, db)
    if resp:
        return resp

    owner = _my_owner(db, user)
    if owner is None:
        raise HTTPException(status_code=403, detail="No tienes un propietario asignado.")

    text = (body or "").strip()
    if text:
        db.add(Message(sender_user_id=user.id, recipient_user_id=owner.id,
                       subject=(subject or "").strip()[:200] or None, body=text[:4000]))
        db.commit()
        audit(db, request, "message.sent", actor=user, object_type="user", object_id=owner.id)
    return RedirectResponse(url="/inquilino/mensajes", status_code=302)


# --- Perfil -----------------------------------------------------------------


@router.get("/inquilino/perfil", response_class=HTMLResponse)
def profile(request: Request, db: Session = Depends(get_db)):
    user, resp = _require_tenant(request, db)
    if resp:
        return resp
    return templates.TemplateResponse(
        request=request, name="tenant_profile.html", context=_ctx(request, user, saved=False)
    )


@router.post("/inquilino/perfil", response_class=HTMLResponse)
def profile_save(request: Request, db: Session = Depends(get_db),
                 name: str = Form(...), phone: str = Form(""), csrf_token: str = Form("")):
    user, resp = _require_tenant(request, db)
    if resp:
        return resp
    # El correo de acceso NO se edita aquí: cambiarlo sin verificación es un
    # vector de secuestro de cuenta (DESIGN.md §6).
    validate_mock_phone(phone)
    user.name = (name or "").strip()[:120] or user.name
    user.phone = (phone or "").strip()[:40] or None
    db.commit()
    audit(db, request, "tenant.profile_updated", actor=user, object_type="user", object_id=user.id)
    return templates.TemplateResponse(
        request=request, name="tenant_profile.html", context=_ctx(request, user, saved=True)
    )
