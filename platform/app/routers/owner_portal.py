"""Portal del propietario (fase 2b, etapa E4) — DESIGN.md §5.

Cierra el ciclo abierto por el módulo de inquilinos: hasta ahora un inquilino
podía reportar una falla y nadie del otro lado la atendía.

Lo que puede hacer un propietario:
- Dar de alta inquilinos y vincularlos a **sus** viviendas.
- Leer, comentar, asignar y resolver los tickets de sus propiedades.
- Ver un reporte por unidad (y descargarlo en CSV).
- Enviar comunicados a sus inquilinos (bandeja y, opcionalmente, correo).
- Conversar 1:1 por la bandeja interna.
- Registrar su teléfono de contacto, distinto del personal.

Como en `tenant.py`, aquí no se escribe ni un filtro de pertenencia a mano:
todo pasa por `scoping.py`.
"""
from __future__ import annotations

import csv
import io
import os
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import hash_password
from ..db import get_db
from ..email_utils import send_temp_password_email
from ..mockmode import (
    emails_are_sent,
    template_context,
    validate_mock_email,
    validate_mock_phone,
)
from ..models import (
    Announcement,
    AnnouncementRecipient,
    Lease,
    LeaseStatusEnum,
    MaintenanceTicket,
    Message,
    Property,
    RoleEnum,
    TicketEvent,
    TicketEventTypeEnum,
    TicketPhoto,
    TicketStatusEnum,
    User,
)
from ..scoping import (
    assert_can_assign_property,
    owned_properties,
    scoped_leases,
    scoped_tickets,
    scoped_users,
)
from ..security import audit, register_template_globals
from .pages import _current_user_or_none

router = APIRouter(tags=["owner-portal"], include_in_schema=False)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))
register_template_globals(templates)


def _require_owner(request: Request, db: Session):
    user = _current_user_or_none(request, db)
    if not user:
        return None, RedirectResponse(url="/login", status_code=302)
    if user.role not in (RoleEnum.owner, RoleEnum.admin):
        return None, RedirectResponse(url="/inquilino", status_code=302)
    return user, None


def _ctx(user: User, **extra) -> dict:
    ctx = {"user": user, **template_context()}
    ctx.update(extra)
    return ctx


def _my_tenants(db: Session, user: User) -> List[User]:
    """Inquilinos con arrendamiento en las viviendas de este propietario."""
    return [u for u in scoped_users(db, user).all() if u.role == RoleEnum.tenant]


# --- Tickets ----------------------------------------------------------------


@router.get("/owner/tickets", response_class=HTMLResponse)
def tickets_list(request: Request, db: Session = Depends(get_db),
                 estado: str = "", propiedad: str = ""):
    user, resp = _require_owner(request, db)
    if resp:
        return resp

    q = scoped_tickets(db, user)
    if estado:
        try:
            q = q.filter(MaintenanceTicket.status == TicketStatusEnum(estado))
        except ValueError:
            pass
    if propiedad.isdigit():
        # Se filtra dentro del conjunto ya acotado: aunque llegue el id de una
        # propiedad ajena, `scoped_tickets` ya lo dejó fuera. El filtro es
        # comodidad, no control de acceso.
        q = q.filter(MaintenanceTicket.property_id == int(propiedad))

    tickets = q.order_by(MaintenanceTicket.id.desc()).all()
    props = owned_properties(db, user).order_by(Property.id).all()
    prop_names = {p.id: p.title for p in props}
    return templates.TemplateResponse(
        request=request, name="owner_tickets.html",
        context=_ctx(user, tickets=tickets, properties=props, prop_names=prop_names,
                     estado=estado, propiedad=propiedad,
                     statuses=list(TicketStatusEnum)),
    )


@router.get("/owner/tickets/reporte")
def tickets_report(request: Request, db: Session = Depends(get_db), formato: str = ""):
    """Reporte por unidad (DESIGN.md §5.4). `?formato=csv` lo descarga."""
    user, resp = _require_owner(request, db)
    if resp:
        return resp

    tickets = scoped_tickets(db, user).all()
    props = owned_properties(db, user).order_by(Property.id).all()

    rows = []
    for p in props:
        ts = [t for t in tickets if t.property_id == p.id]
        resolved = [t for t in ts if t.status == TicketStatusEnum.resolved and t.resolved_at and t.created_at]
        # Tiempo medio de resolución en horas: la señal más útil para el CEO,
        # porque un promedio alto indica que los reportes se están quedando
        # parados, no que haya muchos.
        avg_h = (
            round(sum((t.resolved_at - t.created_at).total_seconds() for t in resolved) / len(resolved) / 3600, 1)
            if resolved else None
        )
        by_cat = {}
        for t in ts:
            key = t.category.value if t.category else "otro"
            by_cat[key] = by_cat.get(key, 0) + 1
        rows.append({
            "property": p.title,
            "unit": p.unit_label if hasattr(p, "unit_label") else None,
            "total": len(ts),
            "abiertos": sum(1 for t in ts if t.status == TicketStatusEnum.open),
            "en_proceso": sum(1 for t in ts if t.status == TicketStatusEnum.in_progress),
            "resueltos": len(resolved),
            "emergencias": sum(1 for t in ts if t.priority and t.priority.value == "emergencia"),
            "horas_promedio": avg_h,
            "top_categoria": max(by_cat, key=by_cat.get) if by_cat else "—",
        })

    if formato == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Propiedad", "Total", "Abiertos", "En proceso", "Resueltos",
                    "Emergencias", "Horas promedio resolución", "Categoría más frecuente"])
        for r in rows:
            w.writerow([r["property"], r["total"], r["abiertos"], r["en_proceso"],
                        r["resueltos"], r["emergencias"], r["horas_promedio"] or "", r["top_categoria"]])
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]), media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="reporte-tickets.csv"'},
        )

    return templates.TemplateResponse(
        request=request, name="owner_report.html", context=_ctx(user, rows=rows)
    )


@router.get("/owner/tickets/{ticket_id}", response_class=HTMLResponse)
def ticket_detail(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    ticket = scoped_tickets(db, user).filter(MaintenanceTicket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    events = db.query(TicketEvent).filter(TicketEvent.ticket_id == ticket.id).order_by(TicketEvent.id).all()
    photos = db.query(TicketPhoto).filter(TicketPhoto.ticket_id == ticket.id).all()
    reporter = db.query(User).filter(User.id == ticket.reported_by_user_id).first()
    prop = db.query(Property).filter(Property.id == ticket.property_id).first()
    return templates.TemplateResponse(
        request=request, name="owner_ticket_detail.html",
        context=_ctx(user, ticket=ticket, events=events, photos=photos,
                     reporter=reporter, prop=prop, statuses=list(TicketStatusEnum)),
    )


@router.post("/owner/tickets/{ticket_id}/actualizar")
def ticket_update(ticket_id: int, request: Request, db: Session = Depends(get_db),
                  accion: str = Form(...), body: str = Form(""), csrf_token: str = Form("")):
    """Comentar, cambiar estado, resolver o reabrir. Todo queda en el historial."""
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    ticket = scoped_tickets(db, user).filter(MaintenanceTicket.id == ticket_id).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")

    text = (body or "").strip()[:2000]
    prev = ticket.status.value if ticket.status else None

    if accion == "comentar":
        if text:
            db.add(TicketEvent(ticket_id=ticket.id, actor_user_id=user.id,
                               event_type=TicketEventTypeEnum.comment, body=text))
    elif accion == "en_proceso":
        ticket.status = TicketStatusEnum.in_progress
        db.add(TicketEvent(ticket_id=ticket.id, actor_user_id=user.id,
                           event_type=TicketEventTypeEnum.status_changed,
                           from_status=prev, to_status=ticket.status.value,
                           body=text or "Trabajo iniciado"))
    elif accion == "resolver":
        # Resolver exige nota: sin ella, el inquilino no sabe qué se hizo y el
        # historial no sirve para una disputa posterior.
        if not text:
            raise HTTPException(status_code=400, detail="Para resolver hay que explicar qué se hizo.")
        ticket.status = TicketStatusEnum.resolved
        ticket.resolved_at = datetime.now(timezone.utc)
        ticket.resolution_notes = text
        db.add(TicketEvent(ticket_id=ticket.id, actor_user_id=user.id,
                           event_type=TicketEventTypeEnum.resolved,
                           from_status=prev, to_status=ticket.status.value, body=text))
    elif accion == "reabrir":
        ticket.status = TicketStatusEnum.open
        ticket.resolved_at = None
        db.add(TicketEvent(ticket_id=ticket.id, actor_user_id=user.id,
                           event_type=TicketEventTypeEnum.reopened,
                           from_status=prev, to_status=ticket.status.value,
                           body=text or "Reabierto"))
    db.commit()
    audit(db, request, f"ticket.{accion}", actor=user, object_type="ticket", object_id=ticket.id)
    return RedirectResponse(url=f"/owner/tickets/{ticket_id}", status_code=302)


# --- Inquilinos -------------------------------------------------------------


@router.get("/owner/inquilinos", response_class=HTMLResponse)
def tenants_page(request: Request, db: Session = Depends(get_db)):
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    leases = scoped_leases(db, user).all()
    tenants = {u.id: u for u in _my_tenants(db, user)}
    props = {p.id: p for p in owned_properties(db, user).all()}
    flash = request.session.pop("owner_flash", None)
    return templates.TemplateResponse(
        request=request, name="owner_tenants.html",
        context=_ctx(user, leases=leases, tenants=tenants, props=props,
                     properties=list(props.values()), flash=flash),
    )


@router.post("/owner/inquilinos")
def create_tenant(request: Request, db: Session = Depends(get_db),
                  name: str = Form(...), email: str = Form(...), phone: str = Form(""),
                  property_id: int = Form(...), csrf_token: str = Form("")):
    """Da de alta un inquilino y lo vincula a una vivienda del propietario."""
    user, resp = _require_owner(request, db)
    if resp:
        return resp

    # Control clave (DESIGN.md §11): la propiedad debe ser suya. Si viniera
    # manipulada en el formulario, esto lanza 404 antes de crear nada.
    prop = assert_can_assign_property(db, user, property_id)

    addr = (email or "").strip().lower()
    validate_mock_email(addr)   # en modo pruebas, solo dominios de prueba
    validate_mock_phone(phone)

    if db.query(User).filter(User.email == addr).first():
        request.session["owner_flash"] = {"kind": "error", "message": "Ya existe una cuenta con ese correo."}
        return RedirectResponse(url="/owner/inquilinos", status_code=302)

    temp_password = secrets.token_urlsafe(9)
    tenant = User(
        name=(name or "").strip()[:120], email=addr,
        phone=(phone or "").strip()[:40] or None,
        password_hash=hash_password(temp_password),
        role=RoleEnum.tenant, created_by_user_id=user.id,
        must_change_password=True,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    db.add(Lease(property_id=prop.id, tenant_id=tenant.id,
                 status=LeaseStatusEnum.active, created_by_user_id=user.id))
    db.commit()

    # En modo pruebas no sale ningún correo: la clave se muestra en pantalla
    # para poder probar el acceso sin enviar nada a nadie.
    sent = False
    if emails_are_sent():
        try:
            result = send_temp_password_email(tenant.name, tenant.email, temp_password,
                                              login_url=str(request.base_url) + "login")
            sent = bool(getattr(result, "sent", False))
        except Exception:
            sent = False

    audit(db, request, "tenant.created", actor=user, object_type="user", object_id=tenant.id,
          meta=f"property={prop.id}")
    request.session["owner_flash"] = {
        "kind": "ok",
        "message": (
            f"Inquilino {tenant.name} dado de alta en «{prop.title}». "
            + ("Se le envió su clave temporal por correo."
               if sent else f"Clave temporal (modo pruebas, no se envió correo): {temp_password}")
        ),
    }
    return RedirectResponse(url="/owner/inquilinos", status_code=302)


@router.post("/owner/inquilinos/{lease_id}/terminar")
def end_lease(lease_id: int, request: Request, db: Session = Depends(get_db),
              csrf_token: str = Form("")):
    """Termina un arrendamiento. El inquilino pierde el acceso a la vivienda."""
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    lease = scoped_leases(db, user).filter(Lease.id == lease_id).first()
    if lease is None:
        raise HTTPException(status_code=404, detail="Arrendamiento no encontrado")
    lease.status = LeaseStatusEnum.ended
    db.commit()
    audit(db, request, "lease.ended", actor=user, object_type="lease", object_id=lease.id)
    request.session["owner_flash"] = {"kind": "ok", "message": "Arrendamiento terminado."}
    return RedirectResponse(url="/owner/inquilinos", status_code=302)


# --- Comunicados ------------------------------------------------------------


@router.get("/owner/comunicados", response_class=HTMLResponse)
def announcements_page(request: Request, db: Session = Depends(get_db)):
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    sent = (db.query(Announcement).filter(Announcement.author_user_id == user.id)
            .order_by(Announcement.id.desc()).all())
    return templates.TemplateResponse(
        request=request, name="owner_announcements.html",
        context=_ctx(user, announcements=sent,
                     properties=owned_properties(db, user).all(),
                     flash=request.session.pop("owner_flash", None)),
    )


@router.post("/owner/comunicados")
def send_announcement(request: Request, db: Session = Depends(get_db),
                      title: str = Form(...), body: str = Form(...),
                      audience: str = Form("todos"), property_id: str = Form(""),
                      send_email: str = Form(""), csrf_token: str = Form("")):
    user, resp = _require_owner(request, db)
    if resp:
        return resp

    targets = _my_tenants(db, user)
    prop_id = None
    if audience == "propiedad" and property_id.isdigit():
        prop = assert_can_assign_property(db, user, int(property_id))
        prop_id = prop.id
        tenant_ids = {l.tenant_id for l in scoped_leases(db, user).filter(Lease.property_id == prop_id).all()}
        targets = [t for t in targets if t.id in tenant_ids]

    ann = Announcement(author_user_id=user.id, property_id=prop_id,
                       title=title.strip()[:200], body=body.strip(),
                       send_email=bool(send_email))
    db.add(ann)
    db.commit()
    db.refresh(ann)

    # La bandeja se entrega siempre; el correo es adicional y puede fallar sin
    # que el comunicado se pierda.
    for t in targets:
        db.add(AnnouncementRecipient(announcement_id=ann.id, user_id=t.id))
    db.commit()

    audit(db, request, "announcement.sent", actor=user, object_type="announcement",
          object_id=ann.id, meta=f"recipients={len(targets)}")
    request.session["owner_flash"] = {
        "kind": "ok",
        "message": f"Comunicado enviado a {len(targets)} inquilino(s)."
                   + ("" if emails_are_sent() or not send_email
                      else " (Modo pruebas: no se envió correo, solo bandeja.)"),
    }
    return RedirectResponse(url="/owner/comunicados", status_code=302)


# --- Mensajes 1:1 -----------------------------------------------------------


@router.get("/owner/mensajes", response_class=HTMLResponse)
def messages_page(request: Request, db: Session = Depends(get_db)):
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    msgs = (db.query(Message)
            .filter((Message.sender_user_id == user.id) | (Message.recipient_user_id == user.id))
            .order_by(Message.id.desc()).all())
    people = {u.id: u for u in scoped_users(db, user).all()}

    # Se marca leído al abrir la bandeja, pero se conserva qué estaba sin leer
    # para poder resaltarlo en esta misma vista: si se marcara antes, el
    # propietario nunca vería cuál era el mensaje nuevo.
    unread_ids = [m.id for m in msgs if m.recipient_user_id == user.id and m.read_at is None]
    if unread_ids:
        db.query(Message).filter(Message.id.in_(unread_ids)).update(
            {Message.read_at: datetime.now(timezone.utc)}, synchronize_session=False)
        db.commit()

    return templates.TemplateResponse(
        request=request, name="owner_messages.html",
        context=_ctx(user, messages=msgs, people=people, tenants=_my_tenants(db, user),
                     just_read=set(unread_ids)),
    )


@router.post("/owner/mensajes")
def send_message(request: Request, db: Session = Depends(get_db),
                 recipient_id: int = Form(...), subject: str = Form(""),
                 body: str = Form(...), csrf_token: str = Form("")):
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    # El destinatario debe estar dentro de su alcance: un propietario no puede
    # escribirle al inquilino de otro.
    recipient = scoped_users(db, user).filter(User.id == recipient_id).first()
    if recipient is None:
        raise HTTPException(status_code=404, detail="Destinatario no encontrado")
    db.add(Message(sender_user_id=user.id, recipient_user_id=recipient.id,
                   subject=(subject or "").strip()[:200] or None, body=body.strip()))
    db.commit()
    audit(db, request, "message.sent", actor=user, object_type="user", object_id=recipient.id)
    return RedirectResponse(url="/owner/mensajes", status_code=302)


# --- Perfil del propietario -------------------------------------------------


@router.get("/owner/perfil", response_class=HTMLResponse)
def owner_profile(request: Request, db: Session = Depends(get_db)):
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    return templates.TemplateResponse(
        request=request, name="owner_profile.html", context=_ctx(user, saved=False)
    )


@router.post("/owner/perfil", response_class=HTMLResponse)
def owner_profile_save(request: Request, db: Session = Depends(get_db),
                       name: str = Form(...), contact_phone: str = Form(""),
                       csrf_token: str = Form("")):
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    # contact_phone es el número que verán los inquilinos. Se guarda aparte de
    # `phone` para que el propietario pueda dar uno de trabajo y conservar el
    # personal en privado (decisión del CEO).
    validate_mock_phone(contact_phone)
    user.name = (name or "").strip()[:120] or user.name
    user.contact_phone = (contact_phone or "").strip()[:40] or None
    db.commit()
    audit(db, request, "owner.profile_updated", actor=user, object_type="user", object_id=user.id)
    return templates.TemplateResponse(
        request=request, name="owner_profile.html", context=_ctx(user, saved=True)
    )
