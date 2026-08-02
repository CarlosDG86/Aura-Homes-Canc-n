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
) -> MailResult:
    """Send the temporary-password onboarding email. Returns a MailResult;
    never raises, so a mail failure can be surfaced to the admin without
    breaking the user-creation flow."""
    cfg = _config()
    subject, body = _compose_temp_password(name, to_email, temp_password, login_url)

    # Not fully configured yet: no host, or a host+user but the app-password
    # line in .env is still blank. Stay in dev mode (send nothing) so a
    # half-filled config never spams failed auth attempts.
    if not cfg["host"] or (cfg["user"] and not cfg["password"]):
        reason = "SMTP_HOST no está definido" if not cfg["host"] else "falta la contraseña (SMTP_PASSWORD vacío)"
        log.warning("SMTP not fully configured (%s); email to %s NOT sent.", reason, to_email)
        print(
            f"[MAILER dev-mode — {reason}, nothing was sent]\n"
            f"To: {to_email}\nSubject: {subject}\n{body}\n"
        )
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
        log.info("Temp-password email sent to %s", to_email)
        return MailResult(sent=True, configured=True)
    except Exception as exc:  # noqa: BLE001 - report any SMTP failure to the admin
        log.exception("Failed sending temp-password email to %s", to_email)
        return MailResult(sent=False, configured=True, error=str(exc))
