"""Planes visibles y asignables (E14 · D-018, AREA_A §6).

- `GET  /owner/cuenta` — «Mi cuenta»: plan, qué incluye, casas usadas frente al
  límite y días de prueba. **Sin precios y sin botón de compra** (D-019).
- `GET  /admin/cuentas` — directorio de cuentas con su plan y su uso.
- `POST /admin/cuentas/{id}/plan` — **único escritor de `accounts.plan`.**

Sin esta última, los límites de E14 no tendrían válvula: un propietario nuevo
nace en `trial` con una sola casa, y nadie podría subirlo de plan sin tocar la
base a mano.

La cuenta del propietario sale **siempre de la sesión**: no hay `account_id` en
ninguna URL de propietario. El día que esta pantalla acepte un id ajeno filtra
el plan y el número de casas de otro cliente.
"""
from __future__ import annotations

import os
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .. import cuentas, plans
from ..db import get_db
from ..mockmode import template_context
from ..models import Account, AccountPlanEvent, User
from ..security import audit, register_template_globals
from .owner_portal import _ctx, _nav_badges, _require_owner
from .pages import _require_admin

router = APIRouter(tags=["cuentas"], include_in_schema=False)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))
register_template_globals(templates)

#: Lo que se le explica al cliente de cada derecho, en su idioma (D-014).
ETIQUETAS_DERECHO = {
    plans.AGENTE_MENSAJERIA: "Agente de WhatsApp y correo",
    plans.FISCAL_AUTOMATIZADO: "Gastos generados automáticamente",
    plans.GASTOS_RECURRENTES: "Gastos recurrentes",
    plans.COTIZACION_AUTOMATICA: "Cotización automática a proveedores",
}
ETIQUETAS_SIEMPRE = [
    "Panel, filtros y reportes de tus casas",
    "Directorio de proveedores",
    "Registro de gastos y comprobantes",
    "Paquete fiscal para tu contador",
    "Registro manual de cotizaciones",
]


@router.get("/owner/cuenta", response_class=HTMLResponse)
def mi_cuenta(request: Request, db: Session = Depends(get_db)):
    user, resp = _require_owner(request, db)
    if resp:
        return resp
    cuenta = cuentas.cuenta_de(db, user)
    est = cuentas.estado_cuenta(db, cuenta)
    derechos = plans.derechos_de(cuenta)
    return templates.TemplateResponse(
        request=request, name="owner_cuenta.html",
        context=_ctx(user, request, active="cuenta", **_nav_badges(db, user),
                     cuenta_nombre=getattr(cuenta, "name", None), est=est,
                     incluidos=ETIQUETAS_SIEMPRE,
                     derechos=[(ETIQUETAS_DERECHO[k], v) for k, v in derechos.items()],
                     fin_prueba=getattr(cuenta, "trial_ends_at", None)),
    )


@router.get("/admin/cuentas", response_class=HTMLResponse)
def cuentas_lista(request: Request, db: Session = Depends(get_db)):
    admin = _require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)
    filas = []
    for c in db.query(Account).order_by(Account.id).all():
        filas.append({
            "id": c.id, "nombre": c.name, "operadora": bool(c.is_operator),
            "usuarios": db.query(User).filter(User.account_id == c.id).count(),
            "override": c.properties_max_override, "nota": c.plan_note,
            "est": cuentas.estado_cuenta(db, c),
        })
    flash = request.session.pop("admin_flash", None)
    return templates.TemplateResponse(
        request=request, name="admin_cuentas.html",
        context={"user": admin, "active": "cuentas", "filas": filas, "flash": flash,
                 "planes": [(k, v["etiqueta"]) for k, v in plans.PLANES.items()],
                 "estados": plans.ESTADOS, "dias_max": plans.TRIAL_DIAS_MAXIMO,
                 **template_context()},
    )


@router.post("/admin/cuentas/{cuenta_id}/plan")
def cuenta_plan(cuenta_id: int, request: Request, db: Session = Depends(get_db),
                plan: str = Form(...), estado: str = Form(...),
                extender_dias: str = Form(""), limite: str = Form(""),
                nota: str = Form(""), csrf_token: str = Form("")):
    """Cambia plan, estado, prueba y tope con **nota obligatoria**.

    La nota es la referencia del acuerdo comercial. Un cambio de plan sin
    motivo escrito es imposible de explicar seis meses después.
    """
    admin = _require_admin(request, db)
    if not admin:
        return RedirectResponse(url="/login", status_code=302)
    cuenta = db.get(Account, cuenta_id)
    if cuenta is None:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    destino = RedirectResponse(url="/admin/cuentas", status_code=302)

    def error(msg):
        request.session["admin_flash"] = {"kind": "error", "message": msg}
        return destino

    texto = (nota or "").strip()
    if not texto:
        return error("Escribe el motivo o la referencia del acuerdo: queda en el historial.")
    if not plans.plan_valido(plan):
        return error("Plan no válido.")
    if estado not in plans.ESTADOS:
        return error("Estado no válido.")

    nuevo_tope = cuenta.properties_max_override
    crudo = (limite or "").strip()
    if crudo == "-":
        nuevo_tope = None
    elif crudo:
        if not crudo.isdigit():
            return error("El tope de casas tiene que ser un número, o «-» para quitarlo.")
        nuevo_tope = int(crudo)

    fin_nuevo = cuenta.trial_ends_at
    if (extender_dias or "").strip():
        if not extender_dias.strip().isdigit():
            return error("Los días de prueba tienen que ser un número.")
        extra = int(extender_dias)
        if cuenta.trial_started_at is None:
            return error("La prueba de esta cuenta no ha empezado: arranca al dar de alta "
                         "su primera casa.")
        # Solo hacia adelante y con tope duro: acortar una prueba por aquí sería
        # cortarle el acceso a un cliente sin que se viera que es eso.
        candidato = (fin_nuevo or cuenta.trial_started_at) + timedelta(days=extra)
        tope = cuenta.trial_started_at + timedelta(days=plans.TRIAL_DIAS_MAXIMO)
        if candidato > tope:
            return error(f"Una prueba no puede pasar de {plans.TRIAL_DIAS_MAXIMO} días en total.")
        fin_nuevo = candidato

    db.add(AccountPlanEvent(
        account_id=cuenta.id, from_plan=cuenta.plan, to_plan=plan,
        from_trial_ends_at=cuenta.trial_ends_at, to_trial_ends_at=fin_nuevo,
        from_status=cuenta.status, to_status=estado, note=texto[:500],
        actor_user_id=admin.id))
    antes = f"{cuenta.plan}/{cuenta.status}/{cuenta.properties_max_override}"
    cuenta.plan = plan
    cuenta.status = estado
    cuenta.trial_ends_at = fin_nuevo
    cuenta.properties_max_override = nuevo_tope
    cuenta.plan_note = texto[:500]
    cuenta.plan_assigned_at = cuentas._ahora()
    cuenta.plan_assigned_by_user_id = admin.id
    db.commit()
    audit(db, request, "cuenta.plan_cambiado", actor=admin, object_type="account",
          object_id=cuenta.id,
          meta=f"{antes} -> {plan}/{estado}/{nuevo_tope} nota={texto[:120]}")
    request.session["admin_flash"] = {"kind": "success",
                                      "message": f"Cuenta «{cuenta.name}» actualizada."}
    return destino
