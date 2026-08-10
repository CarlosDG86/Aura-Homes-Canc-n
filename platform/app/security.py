"""Cimientos de seguridad de la plataforma (etapa E1 de docs/phase2/handoffs/DEV.md).

Reúne en un solo lugar los controles que `docs/phase2/SECURITY.md` marca como
requisito y que hasta ahora no existían:

- §3  Guardia de SECRET_KEY: la app se niega a arrancar en producción con el
      valor por defecto (con esa llave cualquiera falsifica cookies de sesión).
- §4  CSRF por middleware. Se aplica a TODO método que cambia estado, así que
      una ruta nueva queda protegida sin que nadie tenga que acordarse de
      añadir nada. Deny-by-default: si el token falta o no coincide, 403.
- §5  Límite de intentos de acceso, por IP y por cuenta, contra fuerza bruta.
- §8  Cabeceras de seguridad (CSP, HSTS, nosniff, frame-ancestors...).

Todo lo que hay aquí es defensa en profundidad: ninguno de estos controles
sustituye al filtrado por pertenencia de `scoping.py`, que sigue siendo la
protección principal contra fugas entre propietarios.
"""
from __future__ import annotations

import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from markupsafe import Markup
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

# --- Configuración ----------------------------------------------------------

INSECURE_DEFAULT_SECRET = "dev-insecure-secret-key-change-me"

#: Métodos que pueden cambiar estado y por tanto exigen token CSRF.
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Rutas exentas de CSRF. Deliberadamente casi vacío: cada excepción es un
#: agujero, así que se justifica una por una.
CSRF_EXEMPT_PATHS = frozenset({
    "/api/health",  # sondeo de salud, sin efectos ni sesión
})

SESSION_CSRF_KEY = "_csrf"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER = "x-csrf-token"

# Caducidad de sesión (SECURITY.md §3). Admin más corto que el resto.
IDLE_TIMEOUT_MIN = int(os.environ.get("SESSION_IDLE_MINUTES", "30"))
IDLE_TIMEOUT_ADMIN_MIN = int(os.environ.get("SESSION_IDLE_ADMIN_MINUTES", "15"))
ABSOLUTE_TIMEOUT_HOURS = int(os.environ.get("SESSION_ABSOLUTE_HOURS", "12"))

# Límite de intentos (SECURITY.md §5).
MAX_FAILS_PER_ACCOUNT = int(os.environ.get("LOGIN_MAX_FAILS", "5"))
ACCOUNT_LOCK_MINUTES = int(os.environ.get("LOGIN_LOCK_MINUTES", "15"))
MAX_FAILS_PER_IP = int(os.environ.get("LOGIN_MAX_FAILS_IP", "10"))
IP_WINDOW_MINUTES = int(os.environ.get("LOGIN_IP_WINDOW_MINUTES", "1"))


def is_production() -> bool:
    """Producción salvo que se diga explícitamente lo contrario.

    El valor por defecto es deliberado: si alguien despliega sin configurar
    APP_ENV, queremos los controles ESTRICTOS, no los laxos. Un error de
    configuración debe fallar del lado seguro.
    """
    return os.environ.get("APP_ENV", "production").lower() not in {"dev", "development", "local", "test"}


def require_secure_secret_key(secret_key: str) -> None:
    """Aborta el arranque si en producción se usa la llave de ejemplo.

    Con la llave por defecto (que está escrita en el repositorio) cualquiera
    puede firmar una cookie de sesión y entrar como administrador. Fallar al
    arrancar es ruidoso y molesto a propósito: es preferible a un despliegue
    silenciosamente vulnerable.
    """
    if not is_production():
        return
    if secret_key == INSECURE_DEFAULT_SECRET or not secret_key.strip():
        raise RuntimeError(
            "SECRET_KEY no configurada. La aplicación no arranca en producción con la "
            "llave de ejemplo, porque permite falsificar sesiones de administrador.\n"
            "Genera una y expórtala antes de arrancar:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(64))"\n'
            "  SECRET_KEY=<valor generado>\n"
            "Para desarrollo local: APP_ENV=dev"
        )
    if len(secret_key) < 32:
        raise RuntimeError(
            "SECRET_KEY demasiado corta (mínimo 32 caracteres). "
            'Genera una con: python -c "import secrets; print(secrets.token_urlsafe(64))"'
        )


INSECURE_DEFAULT_ADMIN_PASSWORD = "ChangeMe123!"


def require_secure_seed_password(seed_password: str) -> None:
    """Aborta el arranque si en producción se sembraría el admin con la clave de ejemplo.

    Al desplegar, el contenedor arranca con una base vacía y crea el usuario
    administrador a partir de `SEED_ADMIN_PASSWORD`. Si esa variable no se
    define, se usa `ChangeMe123!`, que está escrita en `platform/README.md` y
    por tanto es pública en el repositorio: cualquiera que encuentre el login
    entraría como administrador.

    Es el mismo criterio que con `SECRET_KEY`: fallar ruidosamente al arrancar
    es preferible a quedar expuesto en silencio. En desarrollo no aplica.
    """
    if not is_production():
        return
    if seed_password == INSECURE_DEFAULT_ADMIN_PASSWORD or len(seed_password.strip()) < 12:
        raise RuntimeError(
            "SEED_ADMIN_PASSWORD no configurada (o demasiado corta).\n"
            "Al desplegar se crea el administrador con esta contraseña. El valor por "
            "defecto está publicado en el repositorio, así que la aplicación no arranca "
            "con él en producción.\n"
            "Define una contraseña larga y única (mínimo 12 caracteres):\n"
            '  fly secrets set SEED_ADMIN_PASSWORD="<contraseña larga y única>"'
        )


# --- CSRF -------------------------------------------------------------------


def get_csrf_token(request: Request) -> str:
    """Token CSRF de la sesión, creándolo la primera vez que se pide.

    Vive en la sesión (cookie firmada), así que un sitio externo no puede
    leerlo: puede provocar que el navegador envíe la cookie, pero no conoce
    su contenido, que es justo lo que rompe el ataque.
    """
    token = request.session.get(SESSION_CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[SESSION_CSRF_KEY] = token
    return token


def rotate_csrf_token(request: Request) -> str:
    """Genera un token nuevo. Llamar al iniciar y cerrar sesión."""
    token = secrets.token_urlsafe(32)
    request.session[SESSION_CSRF_KEY] = token
    return token


def csrf_input(request: Request) -> Markup:
    """Campo oculto listo para insertar en un formulario: {{ csrf_input(request) }}."""
    return Markup(
        f'<input type="hidden" name="{CSRF_FORM_FIELD}" value="{get_csrf_token(request)}">'
    )


def register_template_globals(templates) -> None:
    """Expone csrf_input/csrf_token a las plantillas Jinja2."""
    templates.env.globals["csrf_input"] = csrf_input
    templates.env.globals["csrf_token"] = get_csrf_token


class CSRFMiddleware(BaseHTTPMiddleware):
    """Valida el token CSRF en todo método que cambia estado.

    Se hace por middleware y no con una dependencia por ruta a propósito: una
    dependencia hay que recordar añadirla en cada ruta nueva, y tarde o
    temprano se olvida. Aquí la protección es por omisión y las excepciones
    son explícitas.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method not in UNSAFE_METHODS or request.url.path in CSRF_EXEMPT_PATHS:
            return await call_next(request)

        expected = request.session.get(SESSION_CSRF_KEY)
        submitted = request.headers.get(CSRF_HEADER)

        if not submitted:
            ctype = request.headers.get("content-type", "")
            if ctype.startswith(("application/x-www-form-urlencoded", "multipart/form-data")):
                # Leer el formulario aquí consume el cuerpo de la petición, y la
                # ruta de destino se quedaría sin datos (o colgada esperándolos).
                # Por eso se guarda el cuerpo y se reinyecta con un `receive`
                # propio, que es lo que `call_next` entrega aguas abajo.
                body = await request.body()

                async def _replay() -> dict:
                    return {"type": "http.request", "body": body, "more_body": False}

                request._receive = _replay  # noqa: SLF001 — no hay API pública para esto
                try:
                    form = await request.form()
                    submitted = form.get(CSRF_FORM_FIELD)
                except Exception:
                    submitted = None
                # Vuelve a dejar el cuerpo intacto para la ruta de destino:
                # `request.form()` lo consumió otra vez.
                request._receive = _replay  # noqa: SLF001

        if not expected or not submitted or not hmac.compare_digest(str(expected), str(submitted)):
            return PlainTextResponse(
                "Sesión expirada o solicitud no válida. Vuelve a cargar la página e inténtalo de nuevo.",
                status_code=403,
            )
        return await call_next(request)


# --- Cabeceras de seguridad -------------------------------------------------


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Cabeceras de SECURITY.md §8.

    La CSP ya no admite nada en línea, ni scripts ni estilos: todo el JS vive
    en `static/platform.js` y todo el CSS en `static/platform.css`.

    Esto importa más de lo que parece. Mientras `script-src 'self'` convivía
    con manejadores `onsubmit="return confirm(...)"` en las plantillas, esos
    manejadores **no se ejecutaban**: las acciones destructivas (eliminar una
    propiedad, terminar un arrendamiento) se realizaban sin preguntar. Una CSP
    estricta y HTML con código en línea no pueden coexistir; o se relaja la
    política, o el código sale a archivos. Se eligió lo segundo.
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        h = response.headers
        h.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; script-src 'self'; "
            "style-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'",
        )
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        if is_production():
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


# --- Caducidad de sesión ----------------------------------------------------

SESSION_STARTED_AT = "_started_at"
SESSION_SEEN_AT = "_seen_at"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def mark_session_start(request: Request) -> None:
    """Sella la sesión recién iniciada para poder caducarla después."""
    now = _now().isoformat()
    request.session[SESSION_STARTED_AT] = now
    request.session[SESSION_SEEN_AT] = now


def session_expired(request: Request, is_admin: bool = False) -> bool:
    """True si la sesión superó el límite por inactividad o el absoluto.

    Refresca la marca de actividad como efecto secundario cuando sigue viva.
    """
    started = request.session.get(SESSION_STARTED_AT)
    seen = request.session.get(SESSION_SEEN_AT)
    if not started or not seen:
        # Sesión anterior a este control: la sellamos ahora en vez de expulsar
        # al usuario, para no invalidar sesiones válidas al desplegar.
        mark_session_start(request)
        return False
    try:
        started_dt = datetime.fromisoformat(started)
        seen_dt = datetime.fromisoformat(seen)
    except ValueError:
        return True

    now = _now()
    idle_limit = IDLE_TIMEOUT_ADMIN_MIN if is_admin else IDLE_TIMEOUT_MIN
    if now - seen_dt > timedelta(minutes=idle_limit):
        return True
    if now - started_dt > timedelta(hours=ABSOLUTE_TIMEOUT_HOURS):
        return True

    request.session[SESSION_SEEN_AT] = now.isoformat()
    return False


# --- Sesiones con revocación server-side ------------------------------------

SESSION_SID_KEY = "sid"


def create_server_session(db, request: Request, user) -> str:
    """Abre una sesión en la base y devuelve su `sid`.

    Se llama al iniciar sesión, después de `request.session.clear()`. El `sid`
    va en la cookie; el `user_id` ya no, para que la cookie por sí sola no
    autentique a nadie: sin fila viva en `sessions`, no hay sesión.
    """
    from .models import UserSession

    sid = secrets.token_urlsafe(32)
    db.add(UserSession(
        sid=sid,
        user_id=user.id,
        ip=client_ip(request)[:64],
        user_agent=(request.headers.get("user-agent") or "")[:300] or None,
    ))
    db.commit()
    request.session[SESSION_SID_KEY] = sid
    return sid


def _naive_utc(dt: datetime) -> datetime:
    """SQLite devuelve fechas sin zona; se normaliza para poder compararlas."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def resolve_server_session(db, request: Request, is_admin: bool = False):
    """Devuelve la sesión viva de esta petición, o None.

    Comprueba, en este orden: que exista, que no esté revocada, que no haya
    superado el límite absoluto y que no lleve demasiado tiempo inactiva.
    Si sigue viva, refresca `last_seen_at`.
    """
    from .models import UserSession

    sid = request.session.get(SESSION_SID_KEY)
    if not sid:
        return None
    sess = db.query(UserSession).filter(UserSession.sid == sid).first()
    if sess is None or sess.revoked_at is not None:
        return None

    now = _now()
    created = _naive_utc(sess.created_at) if sess.created_at else now
    seen = _naive_utc(sess.last_seen_at) if sess.last_seen_at else now

    if now - created > timedelta(hours=ABSOLUTE_TIMEOUT_HOURS):
        revoke_session(db, sid, "absolute_timeout")
        return None
    idle_limit = IDLE_TIMEOUT_ADMIN_MIN if is_admin else IDLE_TIMEOUT_MIN
    if now - seen > timedelta(minutes=idle_limit):
        revoke_session(db, sid, "idle_timeout")
        return None

    # Se refresca como mucho una vez por minuto: escribir en cada petición
    # castigaría a SQLite sin aportar precisión útil.
    if now - seen > timedelta(seconds=60):
        sess.last_seen_at = now
        db.commit()
    return sess


def revoke_session(db, sid: str, reason: str = "logout") -> None:
    from .models import UserSession

    sess = db.query(UserSession).filter(UserSession.sid == sid).first()
    if sess is not None and sess.revoked_at is None:
        sess.revoked_at = _now()
        sess.revoked_reason = reason[:60]
        db.commit()


def revoke_all_sessions(db, user_id: int, reason: str = "revoke_all",
                        except_sid: Optional[str] = None) -> int:
    """Cierra todas las sesiones de un usuario. Devuelve cuántas cerró.

    Se usa en tres momentos que importan: "cerrar sesión en todos los
    dispositivos", cambio de contraseña (una contraseña comprometida no debe
    seguir dando acceso en otro lado) y baja de la cuenta.
    """
    from .models import UserSession

    q = db.query(UserSession).filter(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
    )
    if except_sid:
        q = q.filter(UserSession.sid != except_sid)
    rows = q.all()
    now = _now()
    for s in rows:
        s.revoked_at = now
        s.revoked_reason = reason[:60]
    if rows:
        db.commit()
    return len(rows)


def active_sessions(db, user_id: int):
    """Sesiones vivas del usuario, para poder mostrárselas."""
    from .models import UserSession

    return (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.last_seen_at.desc())
        .all()
    )


# --- Límite de intentos de acceso -------------------------------------------


def client_ip(request: Request) -> str:
    """IP del cliente, mirando X-Forwarded-For cuando hay proxy delante.

    Solo se confía en la cabecera si TRUST_PROXY está activo: si no, cualquiera
    podría falsificar su IP y esquivar el bloqueo por IP.
    """
    if os.environ.get("TRUST_PROXY", "").lower() in {"1", "true", "yes"}:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def account_locked_until(user) -> Optional[datetime]:
    """Devuelve el momento hasta el que la cuenta está bloqueada, o None."""
    locked = getattr(user, "locked_until", None)
    if not locked:
        return None
    if locked.tzinfo is None:
        locked = locked.replace(tzinfo=timezone.utc)
    return locked if locked > _now() else None


def register_failed_login(db, user, email: str, ip: str) -> None:
    """Anota el fallo y bloquea la cuenta al llegar al umbral.

    El bloqueo es por cuenta Y por IP (ver `ip_is_rate_limited`): solo por
    cuenta permitiría a un atacante dejar fuera a un usuario legítimo a
    propósito, que es negación de servicio disfrazada de seguridad.
    """
    from .models import LoginAttempt  # import diferido: evita ciclo de importación

    db.add(LoginAttempt(email=(email or "").lower().strip()[:255], ip=ip[:64], success=False))
    if user is not None:
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= MAX_FAILS_PER_ACCOUNT:
            user.locked_until = _now() + timedelta(minutes=ACCOUNT_LOCK_MINUTES)
            user.failed_login_count = 0
    db.commit()


def register_successful_login(db, user, email: str, ip: str) -> None:
    from .models import LoginAttempt

    db.add(LoginAttempt(email=(email or "").lower().strip()[:255], ip=ip[:64], success=True))
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = _now()
    db.commit()


def ip_is_rate_limited(db, ip: str) -> bool:
    """True si esta IP acumuló demasiados fallos en la ventana reciente."""
    from .models import LoginAttempt

    since = _now() - timedelta(minutes=IP_WINDOW_MINUTES)
    fails = (
        db.query(LoginAttempt)
        .filter(
            LoginAttempt.ip == ip[:64],
            LoginAttempt.success.is_(False),
            LoginAttempt.created_at >= since,
        )
        .count()
    )
    return fails >= MAX_FAILS_PER_IP


# --- Bitácora de auditoría --------------------------------------------------


def audit(db, request: Request, action: str, actor=None, object_type: str = None,
          object_id: int = None, meta: str = None) -> None:
    """Registra una acción sensible. Nunca hace fallar la petición.

    Si la auditoría falla no se puede tumbar la operación del usuario, pero
    tampoco puede pasar inadvertida: se revierte y se sigue.
    """
    from .models import AuditLog

    try:
        db.add(AuditLog(
            actor_user_id=getattr(actor, "id", None),
            actor_role=getattr(getattr(actor, "role", None), "value", None),
            actor_ip=client_ip(request)[:64],
            action=action[:80],
            object_type=(object_type or "")[:40] or None,
            object_id=object_id,
            meta=(meta or "")[:500] or None,
        ))
        db.commit()
    except Exception:
        db.rollback()
