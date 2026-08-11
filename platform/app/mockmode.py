"""Modo simulación (`DATA_MODE=mock`) — DESIGN.md §9.1.

Decisión del CEO (2026-08-08): el módulo de inquilinos se enciende **ya** para
poder probarlo, con datos ficticios, y Legal se incorpora después.

"Solo datos de prueba" no puede ser una promesa ni una nota en un documento:
basta un descuido para capturar a una persona real y, a partir de ahí, la
plataforma está tratando datos personales sin la base legal para hacerlo. Por
eso aquí se hace cumplir por código.

Los siete candados:
1. Base de datos aparte (`platform-mock.db`) — se resuelve en `db.py`.
2. Solo correos de dominios de prueba.
3. Solo teléfonos del rango reservado.
4. Banda visible en toda la interfaz.
5. Correo saliente desactivado.
6. Enlaces de WhatsApp desactivados.
7. `DATA_MODE=live` exige `LEGAL_CLEARANCE_REF` o la app no arranca.
"""
from __future__ import annotations

import os
import re

from fastapi import HTTPException

#: Dominios aceptados para cuentas de prueba. Reservados por RFC 2606 / 6761
#: justamente para esto: no existen ni pueden registrarse, así que un correo
#: aquí no puede pertenecer a una persona real.
MOCK_EMAIL_DOMAINS = ("example.com", "example.org", "example.net", "test.local", "invalid")

#: Rango de teléfono reservado para pruebas. Igual que arriba: no corresponde
#: a ninguna línea real, así que un mensaje mal enviado no llega a nadie.
MOCK_PHONE_RE = re.compile(r"^\+?52\s*555\s*01\d{2}\s*\d{4}$")

MOCK_BANNER_TEXT = "MODO PRUEBAS — datos ficticios. No captures información de personas reales."


def data_mode() -> str:
    """`mock` o `live`. Por defecto `mock`: si falta la variable, el modo seguro."""
    return os.environ.get("DATA_MODE", "mock").strip().lower()


def is_mock() -> bool:
    return data_mode() != "live"


def tenant_module_enabled() -> bool:
    return os.environ.get("TENANT_MODULE_ENABLED", "true").strip().lower() in {"1", "true", "yes"}


def owner_property_manage_enabled() -> bool:
    """Bandera del CEO: ¿el propietario administra sus propias propiedades?

    Se consulta también en el servidor, no solo al pintar el menú: ocultar un
    botón no impide que alguien construya la petición a mano (DESIGN.md §4).
    """
    return os.environ.get("OWNER_PROPERTY_MANAGE_ENABLED", "true").strip().lower() in {"1", "true", "yes"}


def require_legal_clearance_for_live() -> None:
    """Impide arrancar en modo real sin la referencia del visto bueno de Legal.

    Se llama al arrancar. Mientras no exista ese documento, la plataforma es
    incapaz de guardar datos personales reales de inquilinos: no es disciplina,
    es una negativa a arrancar.
    """
    if is_mock():
        return
    ref = os.environ.get("LEGAL_CLEARANCE_REF", "").strip()
    if not ref:
        raise RuntimeError(
            "DATA_MODE=live sin LEGAL_CLEARANCE_REF.\n"
            "El módulo de inquilinos trata datos personales (nombre, teléfono, fotos de su "
            "vivienda) y los envía a terceros. Antes de operar con datos reales hace falta el "
            "visto bueno de Legal (LFPDPPP).\n"
            "Define LEGAL_CLEARANCE_REF con la referencia del documento, o vuelve a DATA_MODE=mock."
        )


# --- Validación de altas -----------------------------------------------------


def validate_mock_email(email: str) -> None:
    """Rechaza correos reales mientras se está en modo simulación."""
    if not is_mock():
        return
    addr = (email or "").strip().lower()
    domain = addr.rsplit("@", 1)[-1] if "@" in addr else ""
    if domain not in MOCK_EMAIL_DOMAINS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Modo pruebas: solo se aceptan correos de dominios de prueba "
                f"({', '.join(MOCK_EMAIL_DOMAINS)}). "
                "Para dar de alta personas reales hace falta el visto bueno de Legal."
            ),
        )


def validate_mock_phone(phone: str) -> None:
    """Rechaza teléfonos reales mientras se está en modo simulación."""
    if not is_mock() or not (phone or "").strip():
        return
    if not MOCK_PHONE_RE.match(phone.strip()):
        raise HTTPException(
            status_code=400,
            detail="Modo pruebas: usa un teléfono del rango reservado +52 555 01XX XXXX.",
        )


def emails_are_sent() -> bool:
    """En simulación nunca sale un correo: un inquilino ficticio no recibe nada."""
    return not is_mock()


def whatsapp_links_enabled() -> bool:
    """En simulación los enlaces de WhatsApp se muestran desactivados."""
    return not is_mock()


def template_context() -> dict:
    """Contexto que las plantillas necesitan para pintar el estado del modo."""
    return {
        "mock_mode": is_mock(),
        "mock_banner": MOCK_BANNER_TEXT,
        "whatsapp_enabled": whatsapp_links_enabled(),
    }
