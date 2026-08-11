"""Identidad reforzada (etapa E2) — SECURITY.md §1.3.

Dos controles que protegen la cuenta que lo ve todo:

1. **Segundo factor obligatorio para administradores.** En un equipo local una
   contraseña basta; expuesto a internet, no. Un código de 6 dígitos que cambia
   cada 30 segundos significa que robar la contraseña ya no alcanza: hace falta
   además el teléfono.

2. **Puerta de admin en una URL no enlazada.** Esto es ofuscación, no
   seguridad: sirve para que los rastreadores y los ataques automatizados no
   encuentren el formulario de administración, no para detener a alguien que ya
   sabe dónde está. Lo que protege de verdad es el punto 1.

Los propietarios e inquilinos siguen entrando con contraseña por las puertas
normales: obligarles un segundo factor añadiría fricción donde el riesgo es
mucho menor, y una plataforma que nadie usa no protege nada.
"""
from __future__ import annotations

import base64
import io
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

import pyotp
import qrcode

APP_NAME = "Aura Homes Cancún"

#: Ruta secreta del acceso de administrador. Si no se define, se usa `/login`
#: como antes: así el sistema sigue funcionando en local sin configurar nada.
ADMIN_LOGIN_PATH = os.environ.get("ADMIN_LOGIN_PATH", "").strip()

#: Marca de sesión que indica que se entró por la puerta correcta.
ADMIN_GATE_KEY = "_admin_gate"
#: Marca de sesión que indica que el segundo factor ya se verificó.
TOTP_OK_KEY = "_totp_ok"
#: Usuario que superó la contraseña y está pendiente del segundo factor.
PENDING_USER_KEY = "_totp_pending_user"


def admin_login_path() -> str:
    """Ruta por la que entra el administrador."""
    return ADMIN_LOGIN_PATH or "/login"


def admin_gate_enabled() -> bool:
    """¿Está configurada una puerta separada para el administrador?"""
    return bool(ADMIN_LOGIN_PATH)


# --- Segundo factor (TOTP) ---------------------------------------------------


def totp_required_for(user) -> bool:
    """¿Esta cuenta necesita segundo factor?

    Solo los administradores. Se puede exigir a todos con
    `REQUIRE_TOTP_FOR_ALL=true`, pero por defecto no: la fricción para un
    inquilino que solo reporta una fuga de agua no compensa.
    """
    role = getattr(getattr(user, "role", None), "value", None)
    if os.environ.get("REQUIRE_TOTP_FOR_ALL", "").lower() in {"1", "true", "yes"}:
        return True
    return role == "admin"


def new_secret() -> str:
    """Secreto nuevo en base32, el formato que entienden las apps de códigos."""
    return pyotp.random_base32()


def provisioning_uri(user, secret: str) -> str:
    """URI `otpauth://` que la app de autenticación lee del código QR."""
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=APP_NAME)


def qr_data_uri(uri: str) -> str:
    """Código QR como imagen embebida (data URI).

    Se devuelve embebido y no como archivo para no dejar en disco una imagen
    que contiene el secreto del segundo factor. La CSP permite `img-src data:`.
    """
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def verify_code(secret: str, code: str) -> bool:
    """Comprueba un código de 6 dígitos.

    `valid_window=1` acepta también el código inmediatamente anterior: los
    relojes del teléfono y del servidor rara vez coinciden al segundo, y sin
    ese margen la gente ve rechazos aparentemente aleatorios.
    """
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit():
        return False
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=1)
    except Exception:
        return False


def enable_totp(db, user, secret: str) -> None:
    user.totp_secret = secret
    user.totp_enabled = True
    user.totp_confirmed_at = datetime.now(timezone.utc)
    db.commit()


def disable_totp(db, user) -> None:
    user.totp_secret = None
    user.totp_enabled = False
    user.totp_confirmed_at = None
    db.commit()


# --- Estado del acceso en dos pasos -----------------------------------------


def start_pending_login(request, user) -> None:
    """Guarda quién superó la contraseña, a la espera del segundo factor.

    Deliberadamente NO se marca la sesión como autenticada todavía: mientras
    falte el código, esa sesión no puede abrir ninguna pantalla.
    """
    request.session[PENDING_USER_KEY] = user.id


def pending_user_id(request) -> Optional[int]:
    return request.session.get(PENDING_USER_KEY)


def clear_pending_login(request) -> None:
    request.session.pop(PENDING_USER_KEY, None)


def mark_totp_verified(request) -> None:
    request.session[TOTP_OK_KEY] = True


def totp_satisfied(request, user) -> bool:
    """¿Esta sesión cumple el requisito de segundo factor?"""
    if not totp_required_for(user):
        return True
    if not getattr(user, "totp_enabled", False):
        # Aún no lo ha configurado: se le obligará a hacerlo al entrar.
        return False
    return bool(request.session.get(TOTP_OK_KEY))
