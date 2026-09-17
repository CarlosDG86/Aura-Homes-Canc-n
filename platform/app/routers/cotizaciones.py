"""Cotizaciones de un ticket (E14 · andamiaje del punto 7.4).

## Lo que hay hoy

- **Alta manual** en todos los planes: el propietario teclea lo que le
  pasaron por teléfono o WhatsApp. Comparar dos precios antes de decidir es la
  función que se usa el lunes, exista o no la IA.
- **Aprobar y rechazar SOLO sellan el estado.** El texto del CEO se corta en
  «If owner approves…» y D-017 quedó omitida por decisión suya: aprobar **no**
  avisa al proveedor, **no** agenda, **no** cambia el estado del ticket, **no**
  asigna proveedor y **no** crea ningún pagadero. `status` es VARCHAR para que
  cerrar esa frase mañana no exija tocar la base.
- **La cotización automática es un esqueleto con cuatro cerrojos** que no
  hace ninguna llamada saliente ni escribe `AiUsage`. Existe para que la
  puerta esté probada antes de que haya algo detrás.

## Orden de comprobación (AREA_A §5.3)

Sesión → aislamiento (404) → bandera y puerta legal → plan (403). En la ruta
automática el plan va ANTES que las banderas a propósito: a quien no lo tiene
contratado se le explica qué le falta, en vez de un 501 técnico que no le dice
nada. Pero siempre DESPUÉS del aislamiento: un 403 sobre un ticket ajeno
confirmaría que existe.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .. import ai_agent, cuentas, fiscal, plans
from ..db import get_db
from ..mockmode import data_mode, reject_real_contact_in_text
from ..models import (MaintenanceTicket, TicketEvent, TicketEventTypeEnum,
                      TicketQuote)
from ..scoping import (current_account_id, get_scoped_provider_or_404,
                       scoped_tickets)
from ..security import audit, register_template_globals
from .owner_portal import _ctx, _nav_badges, _require_owner

router = APIRouter(tags=["cotizaciones"], include_in_schema=False)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))
register_template_globals(templates)

REGISTRADA = "registrada"
APROBADA = "aprobada"
RECHAZADA = "rechazada"
ESTADOS = (REGISTRADA, APROBADA, RECHAZADA)

MAX_POR_TICKET = 20


def _flash(request: Request, kind: str, message: str) -> None:
    request.session["owner_flash"] = {"kind": kind, "message": message}


def _ticket(db, user, ticket_id: int) -> MaintenanceTicket:
    t = scoped_tickets(db, user).filter(MaintenanceTicket.id == ticket_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return t


def _ahora():
    return datetime.now(timezone.utc)


@router.post("/owner/tickets/{ticket_id}/cotizaciones")
def cotizaciones_post(ticket_id: int, request: Request, db: Session = Depends(get_db),
                      accion: str = Form(...), cotizacion_id: str = Form(""),
                      proveedor_id: str = Form(""), proveedor_nombre: str = Form(""),
                      monto: str = Form(""), moneda: str = Form("MXN"),
                      vigencia: str = Form(""), alcance: str = Form(""),
                      csrf_token: str = Form("")):
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    ticket = _ticket(db, user, ticket_id)
    destino = RedirectResponse(url=f"/owner/tickets/{ticket.id}#cotizaciones", status_code=302)

    if accion == "registrar":
        cuentas.exigir_escritura(db, request, user)
        n = db.query(TicketQuote).filter(TicketQuote.ticket_id == ticket.id).count()
        if n >= MAX_POR_TICKET:
            _flash(request, "error", f"Este reporte ya tiene {MAX_POR_TICKET} cotizaciones.")
            return destino

        proveedor = None
        if proveedor_id.strip().isdigit():
            proveedor = get_scoped_provider_or_404(db, user, int(proveedor_id))
        nombre = proveedor.name if proveedor else (proveedor_nombre or "").strip()[:160]
        if not nombre:
            _flash(request, "error", "Elige un proveedor o escribe de quién es la cotización.")
            return destino

        mon = (moneda or "MXN").strip().upper()
        if mon not in fiscal.MONEDAS:
            _flash(request, "error", "Moneda no admitida.")
            return destino
        try:
            importe = fiscal.parsear_importe(monto)
            notas = (alcance or "").strip()[:2000] or None
            reject_real_contact_in_text(notas, "el alcance de la cotización")
            if not proveedor:
                reject_real_contact_in_text(nombre, "el nombre del proveedor")
        except HTTPException as e:
            # En pantalla y no como JSON: el propietario tiene que poder
            # corregir sin perder la ficha del ticket.
            _flash(request, "error", str(e.detail))
            return destino
        valido = None
        if vigencia.strip():
            try:
                valido = date.fromisoformat(vigencia.strip())
            except ValueError:
                _flash(request, "error", "La vigencia debe ir como AAAA-MM-DD.")
                return destino

        q = TicketQuote(account_id=current_account_id(user),
                        ticket_id=ticket.id,
                        provider_id=proveedor.id if proveedor else None,
                        provider_name_snapshot=nombre, status=REGISTRADA,
                        source="manual", amount=importe, currency=mon,
                        valid_until=valido, scope_notes=notas,
                        requested_by_user_id=user.id, responded_at=_ahora())
        db.add(q)
        db.commit()
        audit(db, request, "ticket.cotizacion_registrada", actor=user,
              object_type="ticket_quote", object_id=q.id,
              meta=f"ticket={ticket.id} {importe} {mon} modo={data_mode()}")
        _flash(request, "ok", f"Cotización de {nombre} registrada.")
        return destino

    if accion in ("aprobar", "rechazar"):
        if not cotizacion_id.isdigit():
            raise HTTPException(status_code=400, detail="Falta la cotización.")
        # Filtrada por ticket, y el ticket ya pasó por el aislamiento: una
        # cotización de otro ticket —o de otra cuenta— es un 404.
        q = (db.query(TicketQuote)
             .filter(TicketQuote.id == int(cotizacion_id),
                     TicketQuote.ticket_id == ticket.id).first())
        if q is None:
            raise HTTPException(status_code=404, detail="Cotización no encontrada")

        if accion == "aprobar":
            if q.status != REGISTRADA:
                _flash(request, "error", f"Esta cotización ya está {q.status}.")
                return destino
            otra = (db.query(TicketQuote)
                    .filter(TicketQuote.ticket_id == ticket.id,
                            TicketQuote.status == APROBADA).first())
            if otra is not None:
                _flash(request, "error", f"Ya aprobaste la de {otra.provider_name_snapshot}. "
                                         f"Recházala primero si cambiaste de opinión.")
                return destino
            q.status = APROBADA
            texto = f"Cotización aprobada: {q.provider_name_snapshot} ({q.amount} {q.currency})"
        else:
            if q.status == RECHAZADA:
                _flash(request, "error", "Esta cotización ya estaba rechazada.")
                return destino
            q.status = RECHAZADA
            texto = f"Cotización rechazada: {q.provider_name_snapshot}"

        q.decided_at = _ahora()
        q.decided_by_user_id = user.id
        # Constancia en el historial del ticket, y nada más. Ver el docstring:
        # sin D-017 aprobar no tiene consecuencias fuera de esta fila.
        db.add(TicketEvent(ticket_id=ticket.id, actor_user_id=user.id,
                           event_type=TicketEventTypeEnum.comment, body=texto))
        db.commit()
        audit(db, request, f"ticket.cotizacion_{q.status}", actor=user,
              object_type="ticket_quote", object_id=q.id, meta=f"ticket={ticket.id}")
        _flash(request, "ok", texto + ".")
        return destino

    _flash(request, "error", "Acción no reconocida.")
    return destino


def _no_disponible(request, db, user, ticket, codigo: int, titulo: str, mensaje: str):
    return templates.TemplateResponse(
        request=request, name="owner_no_disponible.html", status_code=codigo,
        context=_ctx(user, request, active="tickets", **_nav_badges(db, user),
                     titulo=titulo, mensaje=mensaje,
                     volver=f"/owner/tickets/{ticket.id}"),
    )


@router.post("/owner/tickets/{ticket_id}/cotizaciones/solicitar")
def cotizacion_automatica(ticket_id: int, request: Request, db: Session = Depends(get_db),
                          csrf_token: str = Form("")):
    """Esqueleto de la cotización automática. **No llama a nadie.**

    Cuatro cerrojos, todos en el servidor:

    1. plan con `cotizacion_automatica` → si falta, 403 con explicación.
    2. `QUOTES_AGENT_ENABLED` (apagada por omisión).
    3. agente de IA configurado y con presupuesto.
    4. `DATA_MODE=live` con `LEGAL_CLEARANCE_REF`.

    Con el plan pero cualquiera de los otros apagado → 501. Y con los cuatro
    abiertos, también 501: en esta fase no hay nada construido detrás.
    """
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    ticket = _ticket(db, user, ticket_id)

    cuenta = cuentas.cuenta_de(db, user)
    if not plans.tiene_derecho(cuenta, plans.COTIZACION_AUTOMATICA):
        audit(db, request, "ticket.cotizacion_auto_sin_plan", actor=user,
              object_type="ticket", object_id=ticket.id)
        return _no_disponible(
            request, db, user, ticket, 403, "No incluido en tu plan",
            "Pedir cotizaciones automáticamente a tus proveedores es parte de "
            "Enterprise +. Puedes seguir registrando a mano las que te lleguen "
            "por teléfono o WhatsApp, en todos los planes.")

    cerrado = []
    if os.environ.get("QUOTES_AGENT_ENABLED", "false").strip().lower() not in {"1", "true", "yes"}:
        cerrado.append("bandera")
    if not ai_agent.is_configured() or ai_agent.budget_exhausted(db):
        cerrado.append("agente")
    if data_mode() != "live" or not os.environ.get("LEGAL_CLEARANCE_REF", "").strip():
        cerrado.append("legal")

    audit(db, request, "ticket.cotizacion_auto_no_disponible", actor=user,
          object_type="ticket", object_id=ticket.id,
          meta="cerrojos=" + (",".join(cerrado) or "ninguno_pero_sin_construir"))
    return _no_disponible(
        request, db, user, ticket, 501, "Todavía no disponible",
        "La cotización automática está incluida en tu plan, pero aún no está "
        "activa. Mientras tanto, registra a mano las cotizaciones que recibas.")
