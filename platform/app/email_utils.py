"""Outbound email for the platform (owner onboarding, password resets).

Uses the Python stdlib (smtplib) only — no new dependency, per the free-tier
constraint. Configuration is read from environment variables so no credentials
live in the repo:

    SMTP_HOST      e.g. smtp.gmail.com   (REQUIRED to actually send)
    SMTP_PORT      default 587
    SMTP_USER      login user (also the default From)
    SMTP_PASSWORD  login password / app password
    SMTP_FROM      From address (defaults to SMTP_USER)
    SMTP_STARTTLS  "false" to disable STARTTLS (default enabled)

When SMTP_HOST is not set the mailer runs in **dev mode**: it does NOT send
anything, it logs/prints the message that WOULD have been sent, and reports
back `configured=False` so the caller can tell the admin to configure SMTP.
This keeps local development (and automated tests) from emailing real people.

## E10 — la guarda del modo simulación vive AQUÍ, no en quien llama

Hasta E10, `send_temp_password_email` no consultaba el modo simulación: solo
miraba si el SMTP estaba configurado. `mockmode.emails_are_sent()` existía,
pero solo la respetaban dos llamadas de `owner_portal.py`; el restablecimiento
de contraseña del administrador (`pages.py`) llamaba directo.

Medido el 2026-09-08 interceptando el envío: con `DATA_MODE=mock` y SMTP
configurado, la plataforma **intentaba enviar un correo real con la contraseña
en claro** a una dirección real, mientras `emails_are_sent()` devolvía False.
Lo único que lo detenía era que `SMTP_PASSWORD` estuviera vacío — y llenarlo
es precisamente lo que exige construir la recuperación de contraseña.

Con la guarda dentro del emisor, «en simulación no sale un correo» pasa de ser
una promesa a ser código, y no puede olvidarse en la siguiente ruta que envíe.
"""
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

log = logging.getLogger("aura.mailer")


@dataclass
class MailResult:
    sent: bool
    configured: bool
    error: Optional[str] = None
    #: True cuando no salió porque el modo simulación lo impidió, no por falta
    #: de configuración. Deja distinguir «no se pudo» de «no se debía».
    suppressed: bool = False


def enviar(to_email: str, subject: str, body: str, kind: str = None,
           user_id: int = None, db=None) -> MailResult:
    """Emisor de bajo nivel. Todo correo de la plataforma pasa por aquí.

    Escribe la fila en `outbox_emails`, intenta el envío y actualiza `sent_at`
    o `error`. **Nunca lanza**: un fallo de correo no puede tumbar la operación
    del usuario.

    Dos reglas duras:

    1. En modo simulación **no sale nada**, pase lo que pase con el SMTP.
    2. El cuerpo solo se guarda en modo simulación. Lleva el enlace con el
       token en claro; guardarlo con datos reales anularía el sentido de
       hashear el token en la base.
    """
    from .mockmode import emails_are_sent, is_mock

    fila = None
    if db is not None:
        try:
            from .models import OutboxEmail

            fila = OutboxEmail(
                to_email=to_email, subject=subject,
                body=body if is_mock() else None,
                kind=kind, user_id=user_id,
            )
            db.add(fila)
            db.commit()
        except Exception:  # noqa: BLE001 — el buzón no puede romper el flujo
            db.rollback()
            fila = None

    if not emails_are_sent():
        log.info("Modo simulación: correo a %s NO enviado (asunto: %s)", to_email, subject)
        print(f"[MAILER simulación — no se envía nada]\nTo: {to_email}\n"
              f"Subject: {subject}\n{body}\n")
        return MailResult(sent=False, configured=False, suppressed=True)

    resultado = _enviar_smtp(to_email, subject, body)

    if fila is not None and db is not None:
        try:
            from datetime import datetime

            if resultado.sent:
                fila.sent_at = datetime.utcnow()
            else:
                fila.error = (resultado.error or "no enviado")[:300]
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
    return resultado


def _enviar_smtp(to_email: str, subject: str, body: str) -> MailResult:
    """Envío real. Presupone que el modo simulación ya se comprobó."""
    cfg = _config()
    if not cfg["host"] or (cfg["user"] and not cfg["password"]):
        razon = ("SMTP_HOST no está definido" if not cfg["host"]
                 else "falta la contraseña (SMTP_PASSWORD vacío)")
        log.warning("SMTP sin configurar (%s); correo a %s NO enviado.", razon, to_email)
        print(f"[MAILER dev-mode — {razon}, no se envió nada]\n"
              f"To: {to_email}\nSubject: {subject}\n{body}\n")
        return MailResult(sent=False, configured=False)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from"]
    msg["To"] = to_email
    msg.set_content(body)
    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
            if cfg["starttls"]:
                server.starttls(context=ssl.create_default_context())
            if cfg["user"]:
                server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
        log.info("Correo enviado a %s", to_email)
        return MailResult(sent=True, configured=True)
    except Exception as exc:  # noqa: BLE001 — se reporta, no se propaga
        log.exception("Falló el envío a %s", to_email)
        return MailResult(sent=False, configured=True, error=str(exc))


def _config() -> dict:
    return {
        "host": os.environ.get("SMTP_HOST"),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USER"),
        "password": os.environ.get("SMTP_PASSWORD"),
        "from": os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "no-reply@aura-homes-cancun.local",
        "starttls": os.environ.get("SMTP_STARTTLS", "true").lower() != "false",
    }


def _compose_temp_password(name: str, to_email: str, temp_password: str, login_url: str) -> tuple:
    subject = "Tu acceso a la plataforma — Aura Homes Cancún"
    body = (
        f"Hola {name},\n\n"
        "Se creó tu cuenta en la plataforma de Aura Homes Cancún.\n\n"
        f"Usuario: {to_email}\n"
        f"Clave temporal: {temp_password}\n\n"
        "Por tu seguridad, cambia esta contraseña en cuanto inicies sesión por primera vez.\n"
        f"Ingresa aquí: {login_url}\n\n"
        "— Aura Homes Cancún"
    )
    return subject, body


def send_temp_password_email(
    to_email: str,
    name: str,
    temp_password: str,
    login_url: str = "http://127.0.0.1:8010/login",
    db=None,
    user_id: int = None,
) -> MailResult:
    """Correo de alta con la clave temporal.

    Pasa por `enviar()`, así que en modo simulación **no sale** aunque el SMTP
    esté configurado. Antes de E10 este era el camino por el que una clave en
    claro podía salir a una dirección real desde el modo de pruebas.
    """
    subject, body = _compose_temp_password(name, to_email, temp_password, login_url)
    return enviar(to_email, subject, body, kind="temp_password",
                  user_id=user_id, db=db)


def _compose_password_reset(name: str, reset_url: str, minutos: int) -> tuple:
    subject = "Restablece tu contraseña — Aura Homes Cancún"
    body = (
        f"Hola {name},\n\n"
        "Recibimos una solicitud para restablecer la contraseña de tu cuenta.\n\n"
        f"Abre este enlace para elegir una nueva:\n{reset_url}\n\n"
        f"El enlace caduca en {minutos} minutos y solo se puede usar una vez.\n\n"
        "Si no fuiste tú, puedes ignorar este mensaje: tu contraseña no ha\n"
        "cambiado y nadie ha entrado a tu cuenta.\n\n"
        "— Aura Homes Cancún"
    )
    return subject, body


def send_password_reset_email(to_email: str, name: str, reset_url: str,
                              minutos: int = 60, db=None,
                              user_id: int = None) -> MailResult:
    """Correo con el enlace de recuperación (E10 · punto 3.2 del CEO).

    El texto está redactado para que un correo recibido por error **no alarme**
    y no delate nada: no dice si la cuenta existe ni quién la pidió.
    """
    subject, body = _compose_password_reset(name, reset_url, minutos)
    return enviar(to_email, subject, body, kind="reset", user_id=user_id, db=db)
