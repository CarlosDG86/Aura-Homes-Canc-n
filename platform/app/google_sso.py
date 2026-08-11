"""Acceso con Google (OpenID Connect) — SECURITY.md §1.1.

Decisión del CEO (2026-08-08): propietarios e inquilinos entran con su cuenta
de Google, o con contraseña como respaldo.

La ventaja no es la comodidad, es la responsabilidad: **nosotros dejamos de
guardar su contraseña**. Si algún día se filtrara nuestra base de datos, no
habría contraseñas que robar para esas cuentas.

Cuatro reglas que sostienen la seguridad de este archivo:

1. **Sin auto-registro.** Si el correo de Google no corresponde a un usuario ya
   existente y activo, se rechaza el acceso. Sin esta regla, cualquier persona
   del mundo con una cuenta de Gmail entraría a la plataforma. Es el error más
   grave que se puede cometer al implementar "entrar con Google".

2. **Vinculación por `sub`, no por correo.** El `sub` es el identificador
   permanente que Google asigna a una cuenta; el correo puede cambiar de dueño
   (una empresa libera una dirección y se la da a otra persona). Solo en el
   primer acceso se busca por correo verificado, y a partir de ahí se guarda el
   `sub` y se usa ese.

3. **`state`, `nonce` y PKCE, todos de un solo uso.** `state` impide que otro
   sitio provoque un inicio de sesión; `nonce` impide reutilizar un token
   capturado; PKCE impide que alguien que intercepte el código lo canjee.

4. **La firma del token se verifica** contra las llaves públicas de Google. Sin
   eso, cualquiera podría fabricar un token diciendo ser quien quisiera.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from typing import Optional, Tuple
from urllib.parse import urlencode

import httpx
import jwt

# Los extremos son configurables para poder probarlos contra un proveedor
# simulado; en producción quedan los de Google.
ISSUER = os.environ.get("GOOGLE_ISSUER", "https://accounts.google.com")
AUTH_ENDPOINT = os.environ.get("GOOGLE_AUTH_ENDPOINT", "https://accounts.google.com/o/oauth2/v2/auth")
TOKEN_ENDPOINT = os.environ.get("GOOGLE_TOKEN_ENDPOINT", "https://oauth2.googleapis.com/token")
JWKS_URI = os.environ.get("GOOGLE_JWKS_URI", "https://www.googleapis.com/oauth2/v3/certs")

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()

#: Solo lo mínimo. Pedir más permisos de los necesarios es mala práctica y
#: además hace que Google muestre una pantalla de consentimiento más alarmante.
SCOPES = "openid email profile"

STATE_KEY = "_oidc_state"
NONCE_KEY = "_oidc_nonce"
VERIFIER_KEY = "_oidc_verifier"


class SSOError(Exception):
    """Fallo del acceso con Google. El mensaje es apto para mostrar al usuario."""


def is_configured() -> bool:
    """¿Están las credenciales de Google definidas?

    Si no lo están, el botón no se muestra y las rutas responden que no está
    disponible: la plataforma sigue funcionando con contraseña.
    """
    return bool(CLIENT_ID and CLIENT_SECRET and REDIRECT_URI)


# --- Inicio del flujo --------------------------------------------------------


def _pkce_pair() -> Tuple[str, str]:
    """Verificador y su reto (PKCE, RFC 7636).

    El navegador envía solo el reto (un hash); el verificador viaja al final,
    desde el servidor. Quien intercepte el código de autorización no puede
    canjearlo sin el verificador.
    """
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def build_authorize_url(request) -> str:
    """URL a la que se manda al usuario, guardando los secretos en su sesión."""
    if not is_configured():
        raise SSOError("El acceso con Google no está configurado.")

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier, challenge = _pkce_pair()

    request.session[STATE_KEY] = state
    request.session[NONCE_KEY] = nonce
    request.session[VERIFIER_KEY] = verifier

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        # Pide elegir cuenta en vez de reutilizar la última en silencio: en un
        # equipo compartido, entrar sin querer con otra cuenta es confuso.
        "prompt": "select_account",
    }
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


# --- Retorno -----------------------------------------------------------------


def _consume(request, key: str) -> Optional[str]:
    """Lee y borra un valor de la sesión: todos son de un solo uso."""
    return request.session.pop(key, None)


def exchange_and_verify(request, code: str, state: str) -> dict:
    """Canjea el código y devuelve los datos verificados del usuario.

    Lanza `SSOError` con un mensaje entendible ante cualquier problema.
    """
    if not is_configured():
        raise SSOError("El acceso con Google no está configurado.")

    expected_state = _consume(request, STATE_KEY)
    nonce = _consume(request, NONCE_KEY)
    verifier = _consume(request, VERIFIER_KEY)

    # `compare_digest` evita filtrar información por el tiempo de comparación.
    if not expected_state or not state or not secrets.compare_digest(expected_state, state):
        raise SSOError("La solicitud de acceso no es válida o expiró. Inténtalo de nuevo.")
    if not verifier:
        raise SSOError("La solicitud de acceso expiró. Inténtalo de nuevo.")

    try:
        response = httpx.post(
            TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
            timeout=15,
        )
    except httpx.HTTPError:
        raise SSOError("No se pudo contactar a Google. Inténtalo de nuevo.")

    if response.status_code != 200:
        raise SSOError("Google rechazó la solicitud de acceso.")

    id_token = (response.json() or {}).get("id_token")
    if not id_token:
        raise SSOError("Google no devolvió la identidad del usuario.")

    return verify_id_token(id_token, nonce)


def verify_id_token(id_token: str, nonce: Optional[str]) -> dict:
    """Valida firma, emisor, destinatario, caducidad y `nonce`.

    Se separa de `exchange_and_verify` para poder probarla de forma aislada:
    es la parte donde un error abre la puerta a que alguien fabrique tokens.
    """
    try:
        signing_key = jwt.PyJWKClient(JWKS_URI).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=CLIENT_ID,     # el token debe ser PARA nuestra aplicación
            issuer=ISSUER,          # y venir de Google
        )
    except jwt.ExpiredSignatureError:
        raise SSOError("La sesión de Google expiró. Inténtalo de nuevo.")
    except jwt.InvalidTokenError:
        raise SSOError("La identidad recibida de Google no es válida.")
    except Exception:
        raise SSOError("No se pudo verificar la identidad con Google.")

    if nonce and claims.get("nonce") != nonce:
        # Token válido pero de OTRA solicitud: alguien está reutilizando uno
        # capturado.
        raise SSOError("La identidad recibida no corresponde a esta solicitud.")

    if not claims.get("email"):
        raise SSOError("Google no compartió un correo electrónico.")
    if not claims.get("email_verified"):
        # Sin esto, alguien podría crear una cuenta de Google con el correo de
        # otra persona sin demostrar que le pertenece.
        raise SSOError("Tu correo de Google no está verificado.")

    return {
        "sub": claims["sub"],
        "email": claims["email"].lower().strip(),
        "name": claims.get("name") or "",
    }


# --- Vinculación con un usuario existente ------------------------------------


def find_user(db, info: dict):
    """Usuario de la plataforma que corresponde a esta identidad de Google.

    Devuelve `None` si no hay ninguno: **no se crea nada**. Es la regla que
    impide que cualquier persona con una cuenta de Gmail entre.
    """
    from .models import User

    # 1) Por `sub`: el vínculo permanente, una vez establecido.
    user = db.query(User).filter(User.google_sub == info["sub"]).first()
    if user:
        return user

    # 2) Primer acceso: se busca por el correo verificado y se guarda el `sub`.
    user = db.query(User).filter(User.email == info["email"]).first()
    if user and not user.google_sub:
        user.google_sub = info["sub"]
        db.commit()
        return user

    # El correo existe pero ya está vinculado a OTRA cuenta de Google: se
    # rechaza en vez de reasignar, que sería una forma de secuestro.
    return None
