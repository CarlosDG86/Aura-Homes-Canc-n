"""Pagos (fase 2c) — configuración previa, sin procesar cobros.

Decisión del CEO (2026-08-08): "deja las conexiones y los requisitos para el
método de pago, puede ser desde el módulo de admin en un submenú".

Lo que hay aquí es exactamente eso y nada más:
- **Métodos de pago**: dónde y cómo quiere el CEO que le paguen (cuenta,
  referencia, instrucciones para el inquilino). Son datos de configuración,
  no credenciales de cobro.
- **Requisitos**: la lista de lo que Legal y un eventual proveedor van a
  exigir antes de poder mover dinero de verdad.

Lo que **no** hay, deliberadamente: ningún cobro, ninguna pasarela, ningún
dato de tarjeta. `PAYMENTS_MODULE_ENABLED` sigue en `false` y las rutas de
cobro de la API devuelven 501. Guardar un número de tarjeta obligaría a
cumplir PCI-DSS, que es un proyecto en sí mismo y está fuera de alcance.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..db import get_db
from ..mockmode import template_context
from ..models import PlatformSetting, RoleEnum
from ..security import audit, register_template_globals
from .pages import _current_user_or_none

router = APIRouter(tags=["payments"], include_in_schema=False)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))
register_template_globals(templates)

NOT_AVAILABLE = {
    "detail": "El módulo de pagos no está disponible: requiere revisión de Legal.",
}

#: Claves de configuración del método de pago. Se guardan como ajustes con
#: nombre, no en columnas nuevas, porque son texto libre que el CEO ajustará
#: varias veces antes de que exista un cobro real.
PAYMENT_FIELDS = [
    ("pago_titular", "Titular de la cuenta", "A nombre de quién se deposita"),
    ("pago_banco", "Banco", "Institución donde está la cuenta"),
    ("pago_clabe", "CLABE / cuenta", "Los inquilinos verán este dato para transferir"),
    ("pago_referencia", "Formato de referencia", "Ej. AURA-{unidad}-{mes}"),
    ("pago_dia_corte", "Día de corte", "Día del mes en que vence la renta"),
    ("pago_instrucciones", "Instrucciones para el inquilino", "Texto que verá al pagar"),
]


def _require_admin_page(request: Request, db: Session):
    user = _current_user_or_none(request, db)
    if not user:
        return None, RedirectResponse(url="/login", status_code=302)
    if user.role != RoleEnum.admin:
        return None, RedirectResponse(url="/owner", status_code=302)
    return user, None


def _get_setting(db: Session, key: str) -> str:
    row = db.query(PlatformSetting).filter(PlatformSetting.key == key).first()
    return row.value if row and row.value else ""


@router.get("/admin/pagos/metodos", response_class=HTMLResponse)
def payment_methods(request: Request, db: Session = Depends(get_db)):
    user, resp = _require_admin_page(request, db)
    if resp:
        return resp
    values = {k: _get_setting(db, k) for k, _, _ in PAYMENT_FIELDS}
    return templates.TemplateResponse(
        request=request, name="admin_payment_methods.html",
        context={"user": user, "active": "pay-methods", "fields": PAYMENT_FIELDS,
                 "values": values, "saved": request.session.pop("pay_saved", None),
                 **template_context()},
    )


@router.post("/admin/pagos/metodos")
async def payment_methods_save(request: Request, db: Session = Depends(get_db)):
    user, resp = _require_admin_page(request, db)
    if resp:
        return resp
    form = await request.form()
    for key, _, _ in PAYMENT_FIELDS:
        value = (form.get(key) or "").strip()[:500]
        row = db.query(PlatformSetting).filter(PlatformSetting.key == key).first()
        if row is None:
            db.add(PlatformSetting(key=key, value=value))
        else:
            row.value = value
    db.commit()
    # No se registra el contenido en la bitácora: la CLABE es un dato bancario
    # y no tiene por qué quedar duplicado en los registros.
    audit(db, request, "payments.methods_updated", actor=user, object_type="settings")
    request.session["pay_saved"] = True
    return RedirectResponse(url="/admin/pagos/metodos", status_code=302)


@router.get("/admin/pagos/requisitos", response_class=HTMLResponse)
def payment_requirements(request: Request, db: Session = Depends(get_db)):
    """Lista de lo que falta antes de poder cobrar de verdad.

    Es una pantalla informativa a propósito: sirve para que el CEO vea de un
    vistazo por qué el cobro sigue apagado y qué falta para encenderlo.
    """
    user, resp = _require_admin_page(request, db)
    if resp:
        return resp

    legal_ref = os.environ.get("LEGAL_CLEARANCE_REF", "").strip()
    payments_on = os.environ.get("PAYMENTS_MODULE_ENABLED", "false").lower() in {"1", "true", "yes"}
    clabe_set = bool(_get_setting(db, "pago_clabe"))

    requisitos = [
        {"titulo": "Visto bueno de Legal (LFPDPPP)",
         "detalle": "Registrar pagos implica datos financieros de personas. Legal debe "
                    "aprobar el aviso de privacidad y la conservación de comprobantes.",
         "listo": bool(legal_ref)},
        {"titulo": "Definir el método de cobro",
         "detalle": "Datos bancarios y formato de referencia para que el inquilino "
                    "pueda depositar e identificar su pago.",
         "listo": clabe_set},
        {"titulo": "Decidir el alcance: ¿registrar o procesar?",
         "detalle": "Registrar pagos hechos por fuera es muy distinto, en riesgo y "
                    "en obligaciones, a cobrar dentro de la plataforma. Sin esta "
                    "decisión del CEO no se puede elegir proveedor.",
         "listo": False},
        {"titulo": "Facturación (CFDI)",
         "detalle": "Si se emiten comprobantes fiscales hace falta un PAC y los datos "
                    "fiscales del arrendador.",
         "listo": False},
        {"titulo": "Política de conservación de comprobantes",
         "detalle": "Cuánto tiempo se guardan los recibos y quién puede verlos.",
         "listo": False},
    ]
    return templates.TemplateResponse(
        request=request, name="admin_payment_requirements.html",
        context={"user": user, "active": "pay-reqs", "requisitos": requisitos,
                 "payments_on": payments_on, "legal_ref": legal_ref,
                 "pendientes": sum(1 for r in requisitos if not r["listo"]),
                 **template_context()},
    )


# --- API de cobro: sigue cerrada --------------------------------------------


@router.api_route("/api/payments", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@router.api_route("/api/payments/{full_path:path}",
                  methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def payments_not_available(full_path: str = ""):
    """Todo cobro sigue devolviendo 501 hasta que Legal firme."""
    return JSONResponse(status_code=501, content=NOT_AVAILABLE)
