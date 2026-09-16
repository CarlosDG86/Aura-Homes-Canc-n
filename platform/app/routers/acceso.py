"""Recuperación de contraseña y cambio de contraseña (E10 · punto 3.2 del CEO).

Router aparte porque `pages.py` ya pasa de 900 líneas y mezcla acceso, 2FA,
alta de propietarios, administración de usuarios y sincronización del sitio.

## La regla que ordena todo el flujo

**El enlace no concede sesión. Solo permite ESCRIBIR una contraseña nueva.**
Nunca inicia sesión automáticamente, nunca sirve para el administrador y nunca
salta el segundo factor. Quien controle un buzón obtiene, como mucho, tener
que volver a pasar por `/login` con todos sus frenos.

## Por qué todas las respuestas son idénticas

`POST /recuperar` responde **siempre** lo mismo: 302 a `/recuperar/enviado`.
Los seis casos —correo inexistente, cuenta inactiva, cuenta bloqueada, cuenta
de administrador, límite por hora superado y éxito— devuelven el mismo código,
el mismo `Location` y la misma página. Solo se distinguen en la bitácora.

En particular **nunca se devuelve un 429 con cuerpo distinto**: el propio
límite sería el oráculo de enumeración de cuentas que este flujo intenta
cerrar. Si un 429 delatara «esta dirección existe», habríamos cambiado un
agujero por otro.

Por el mismo motivo el envío va en `BackgroundTasks` y no en línea: `smtplib`
es síncrono con 15 s de espera, así que enviar dentro de la petición haría que
un correo existente tardara ~1 s y uno inexistente nada. Eso es un oráculo
cronometrable, y anularía todo el cuidado anterior.

## El administrador queda fuera (D-022)

Es lo que pidió el CEO («send a reset to owner and user role») y es lo
correcto: publicar un formulario que acepte el correo del administrador
reduciría toda la cadena de URL oculta más segundo factor a «quien controle el
buzón». Su vía de rescate es `scripts/restablecer_admin.py`, en la consola del
servidor.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import hash_password, verify_password
from ..db import SessionLocal, get_db
from ..email_utils import send_password_reset_email
from ..mockmode import is_mock, template_context
from ..models import LoginAttempt, OutboxEmail, PasswordResetToken, RoleEnum, User
from ..security import (
    audit,
    client_ip,
    register_template_globals,
    revoke_all_sessions,
    rotate_csrf_token,
    validar_fuerza_contrasena,
)
from .pages import _current_user_or_none, _flash, _pop_flash

router = APIRouter(tags=["acceso"], include_in_schema=False)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))
register_template_globals(templates)

#: Vigencia del enlace. `docs/phase2/SECURITY.md` §1.2.
TOKEN_VIGENCIA_MIN = 60

#: Límites por hora. Van por USUARIO y por IP, no por cuenta: una
#: administradora con diez empleados no debe agotarle el cupo a sus compañeros.
MAX_SOLICITUDES_POR_CORREO = 3
MAX_SOLICITUDES_POR_IP = 10
VENTANA_MIN = 60

#: Clave de sesión donde vive el token validado entre el GET y el POST.
SESSION_RESET_HASH = "_reset_hash"


def _ahora() -> datetime:
    return datetime.utcnow()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _sin_cache(resp):
    """El enlace de recuperación no puede quedarse en ninguna caché ni índice."""
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return resp


def _cuenta_solicitudes(db, *, email: str = None, ip: str = None) -> int:
    desde = _ahora() - timedelta(minutes=VENTANA_MIN)
    q = db.query(LoginAttempt).filter(LoginAttempt.kind == "reset",
                                      LoginAttempt.created_at >= desde)
    if email is not None:
        q = q.filter(LoginAttempt.email == email)
    if ip is not None:
        q = q.filter(LoginAttempt.ip == ip[:64])
    return q.count()


# --- Solicitar el enlace -----------------------------------------------------


@router.get("/recuperar", response_class=HTMLResponse)
def recuperar_form(request: Request, db: Session = Depends(get_db)):
    if _current_user_or_none(request, db):
        return RedirectResponse(url="/", status_code=302)
    return _sin_cache(templates.TemplateResponse(
        request=request, name="recuperar.html",
        context={"flash": _pop_flash(request), **template_context()},
    ))


def _enviar_en_segundo_plano(user_id: int, to_email: str, nombre: str,
                             reset_url: str) -> None:
    """Envía fuera de la petición, con su propia sesión de base de datos.

    La sesión de `Depends(get_db)` ya está cerrada cuando esto corre, así que
    la tarea recibe solo cadenas y abre la suya.
    """
    db = SessionLocal()
    try:
        send_password_reset_email(to_email, nombre, reset_url,
                                  minutos=TOKEN_VIGENCIA_MIN, db=db,
                                  user_id=user_id)
    except Exception:  # noqa: BLE001 — nunca debe tumbar el proceso
        pass
    finally:
        db.close()


@router.post("/recuperar")
def recuperar_submit(request: Request, tareas: BackgroundTasks,
                     db: Session = Depends(get_db),
                     email: str = Form(""), csrf_token: str = Form("")):
    correo = (email or "").lower().strip()[:255]
    ip = client_ip(request)

    # Se anota SIEMPRE, exista o no la cuenta: sin eso no hay forma de ver a
    # alguien recorriendo una lista de correos. `kind='reset'` mantiene estas
    # filas fuera del freno de /login.
    db.add(LoginAttempt(email=correo, ip=ip[:64], success=True, kind="reset"))
    db.commit()

    destino = RedirectResponse(url="/recuperar/enviado", status_code=302)

    usuario = db.query(User).filter(User.email == correo).first() if correo else None

    # Los seis motivos de no emitir token terminan aquí, con la MISMA
    # respuesta. La diferencia solo existe en la bitácora.
    motivo = None
    if not usuario:
        motivo = "password_reset.suppressed_unknown"
    elif usuario.role == RoleEnum.admin:
        # D-022: el administrador se rescata por consola, no por correo.
        motivo = "password_reset.suppressed_admin"
    elif not getattr(usuario, "is_active", True):
        motivo = "password_reset.suppressed_inactive"
    elif _cuenta_solicitudes(db, email=correo) > MAX_SOLICITUDES_POR_CORREO:
        motivo = "password_reset.rate_limited"
    elif _cuenta_solicitudes(db, ip=ip) > MAX_SOLICITUDES_POR_IP:
        motivo = "password_reset.rate_limited"

    if motivo:
        audit(db, request, motivo, actor=None, object_type="email", meta=correo[:200])
        return destino

    # Los enlaces vivos anteriores del mismo usuario se invalidan: dos enlaces
    # válidos a la vez multiplican la superficie sin ganar nada.
    for viejo in db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == usuario.id,
            PasswordResetToken.used_at.is_(None)).all():
        viejo.used_at = _ahora()
        viejo.consumed_reason = "reemplazado"

    token = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(
        user_id=usuario.id,
        token_hash=_hash_token(token),
        user_email_at_issue=usuario.email,
        expires_at=_ahora() + timedelta(minutes=TOKEN_VIGENCIA_MIN),
        requested_ip=ip[:64],
        requested_user_agent=(request.headers.get("user-agent") or "")[:300],
    ))
    db.commit()
    audit(db, request, "password_reset.requested", actor=usuario,
          object_type="user", object_id=usuario.id)

    base = str(request.base_url).rstrip("/")
    tareas.add_task(_enviar_en_segundo_plano, usuario.id, usuario.email,
                    usuario.name or "", f"{base}/recuperar/{token}")
    return destino


@router.get("/recuperar/enviado", response_class=HTMLResponse)
def recuperar_enviado(request: Request):
    """Mensaje genérico. Idéntico exista o no la cuenta."""
    return _sin_cache(templates.TemplateResponse(
        request=request, name="recuperar_enviado.html",
        context={"minutos": TOKEN_VIGENCIA_MIN, **template_context()},
    ))


@router.get("/recuperar/caducado", response_class=HTMLResponse)
def recuperar_caducado(request: Request):
    """Destino único de todo enlace que no vale, sin decir por qué."""
    return _sin_cache(templates.TemplateResponse(
        request=request, name="recuperar_caducado.html",
        context={**template_context()},
    ))


# --- Canjear el enlace -------------------------------------------------------


def _token_valido(db, token_hash: str) -> Optional[PasswordResetToken]:
    fila = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash).first()
    if fila is None:
        return None
    if fila.used_at is not None or fila.expires_at <= _ahora():
        return None
    usuario = db.get(User, fila.user_id)
    if usuario is None or not getattr(usuario, "is_active", True):
        return None
    # Cierra el caso de un id reutilizado tras borrar al titular: SQLite
    # reutiliza el rowid máximo y `PRAGMA foreign_keys` está a 0.
    if not hmac.compare_digest(fila.user_email_at_issue or "", usuario.email or ""):
        return None
    if usuario.role == RoleEnum.admin:
        return None
    return fila


@router.get("/recuperar/nueva", response_class=HTMLResponse)
def recuperar_nueva_form(request: Request, db: Session = Depends(get_db)):
    token_hash = request.session.get(SESSION_RESET_HASH)
    if not token_hash or _token_valido(db, token_hash) is None:
        return _sin_cache(RedirectResponse(url="/recuperar/caducado", status_code=302))
    return _sin_cache(templates.TemplateResponse(
        request=request, name="recuperar_nueva.html",
        context={"flash": _pop_flash(request), **template_context()},
    ))


@router.post("/recuperar/nueva")
def recuperar_nueva_submit(request: Request, db: Session = Depends(get_db),
                           password: str = Form(""), password2: str = Form(""),
                           csrf_token: str = Form("")):
    token_hash = request.session.get(SESSION_RESET_HASH)
    # Se revalida entero: pudo caducar mientras se escribía. No se confía en
    # que el GET anterior lo comprobara.
    fila = _token_valido(db, token_hash) if token_hash else None
    if fila is None:
        request.session.pop(SESSION_RESET_HASH, None)
        return _sin_cache(RedirectResponse(url="/recuperar/caducado", status_code=302))

    problema = validar_fuerza_contrasena(password, password2)
    if problema:
        _flash(request, "error", problema)
        return RedirectResponse(url="/recuperar/nueva", status_code=302)

    usuario = db.get(User, fila.user_id)
    usuario.password_hash = hash_password(password)
    usuario.password_changed_at = _ahora()
    # Recuperar el acceso también levanta el bloqueo: si no, alguien que acaba
    # de demostrar que controla su buzón seguiría sin poder entrar.
    usuario.failed_login_count = 0
    usuario.locked_until = None
    usuario.must_change_password = False

    fila.used_at = _ahora()
    fila.used_ip = client_ip(request)[:64]
    fila.consumed_reason = "usado"
    # Cualquier OTRO enlace vivo deja de valer: si la recuperación fue por un
    # compromiso, dejar otro enlace activo anularía el cambio.
    #
    # El `id != fila.id` no es decorativo. La sesión va con `autoflush=False`
    # (db.py:45), así que el `used_at` que se acaba de escribir arriba sigue
    # pendiente y esta consulta todavía ve el token actual como sin usar. Sin
    # excluirlo, el bucle lo volvería a marcar y le pisaría el motivo 'usado'
    # con 'cambio_de_contrasena'.
    for otro in db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == usuario.id,
            PasswordResetToken.id != fila.id,
            PasswordResetToken.used_at.is_(None)).all():
        otro.used_at = _ahora()
        otro.consumed_reason = "cambio_de_contrasena"
    db.commit()

    cerradas = revoke_all_sessions(db, usuario.id, "password_reset")
    audit(db, request, "password_reset.completed", actor=usuario,
          object_type="user", object_id=usuario.id, meta=f"sesiones_cerradas={cerradas}")

    request.session.clear()
    rotate_csrf_token(request)
    _flash(request, "success",
           "Tu contraseña se cambió. Ya puedes entrar con la nueva.")
    return RedirectResponse(url="/login", status_code=302)


@router.get("/recuperar/{token}")
def recuperar_canjear(token: str, request: Request, db: Session = Depends(get_db)):
    """Valida el enlace y lo saca de la URL. **No lo consume.**

    Los previsualizadores de enlaces y los antivirus de correo siguen las URL
    que reciben. Si este GET marcara el token como usado, el enlace estaría
    quemado antes de que la persona llegara a abrirlo.

    Al redirigir, el token desaparece de la barra de direcciones, del
    historial, de la cabecera `Referer` y del registro del proxy.

    > **Va declarada la última del bloque `/recuperar` a propósito.** Es un
    > comodín: si se declarara antes, se tragaría `/recuperar/enviado`,
    > `/recuperar/nueva` y `/recuperar/caducado`, porque FastAPI resuelve por
    > orden de registro. No mover de sitio.
    """
    fila = _token_valido(db, _hash_token(token))
    if fila is None:
        audit(db, request, "password_reset.token_invalid", object_type="token")
        return _sin_cache(RedirectResponse(url="/recuperar/caducado", status_code=302))

    # Se limpia por si alguien abre el enlace con otra sesión abierta: no
    # queremos mezclar identidades a mitad de un cambio de credencial.
    request.session.clear()
    request.session[SESSION_RESET_HASH] = fila.token_hash
    rotate_csrf_token(request)
    return _sin_cache(RedirectResponse(url="/recuperar/nueva", status_code=302))


# --- Cambio de contraseña con sesión abierta ---------------------------------


@router.get("/cambiar-contrasena", response_class=HTMLResponse)
def cambiar_form(request: Request, db: Session = Depends(get_db)):
    user = _current_user_or_none(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        request=request, name="cambiar_contrasena.html",
        context={
            "user": user,
            "forzado": bool(getattr(user, "must_change_password", False)),
            "flash": _pop_flash(request),
            "active": "perfil",
            **template_context(),
        },
    )


@router.post("/cambiar-contrasena")
def cambiar_submit(request: Request, db: Session = Depends(get_db),
                   actual: str = Form(""), password: str = Form(""),
                   password2: str = Form(""), csrf_token: str = Form("")):
    user = _current_user_or_none(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # Se exige la contraseña actual aunque haya sesión: si alguien deja el
    # equipo abierto, no debe bastar con sentarse para quedarse con la cuenta.
    if not verify_password(actual, user.password_hash):
        audit(db, request, "password.change_denied", actor=user,
              object_type="user", object_id=user.id)
        _flash(request, "error", "La contraseña actual no es correcta.")
        return RedirectResponse(url="/cambiar-contrasena", status_code=302)

    problema = validar_fuerza_contrasena(password, password2, actual=actual)
    if problema:
        _flash(request, "error", problema)
        return RedirectResponse(url="/cambiar-contrasena", status_code=302)

    user.password_hash = hash_password(password)
    user.password_changed_at = _ahora()
    user.must_change_password = False
    db.commit()

    # Se conserva la sesión actual y se cierran las demás: cerrar también la
    # propia obligaría a volver a entrar justo después de cambiarla, que es
    # molesto sin ganar nada.
    sid = request.session.get("sid")
    cerradas = revoke_all_sessions(db, user.id, "password_change", except_sid=sid)
    audit(db, request, "password.changed", actor=user, object_type="user",
          object_id=user.id, meta=f"sesiones_cerradas={cerradas}")
    _flash(request, "success",
           f"Contraseña actualizada. Se cerraron {cerradas} sesión(es) en otros dispositivos.")
    return RedirectResponse(url="/cambiar-contrasena", status_code=302)


# --- Buzón de salida (solo admin y solo en simulación) -----------------------


@router.get("/admin/correos", response_class=HTMLResponse)
def buzon_salida(request: Request, db: Session = Depends(get_db)):
    """Lo que la plataforma habría enviado. Doble puerta: admin **y** simulación.

    Permite probar el flujo de recuperación de punta a punta sin buzón y sin
    que salga un solo correo. En modo real devuelve 404: ahí el cuerpo ni
    siquiera se guarda, porque lleva el enlace con el token en claro.
    """
    user = _current_user_or_none(request, db)
    if not user or user.role != RoleEnum.admin or not is_mock():
        return RedirectResponse(url="/login", status_code=302)
    correos = (db.query(OutboxEmail)
               .order_by(OutboxEmail.created_at.desc())
               .limit(100).all())
    return templates.TemplateResponse(
        request=request, name="admin_correos.html",
        context={"user": user, "correos": correos, "active": "correos",
                 **template_context()},
    )
