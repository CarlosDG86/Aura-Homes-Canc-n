"""Hash de contraseñas y control de rol para la API JSON.

Per docs/phase2/INFRA_STACK.md §3: passlib/bcrypt para el hash, cookie de
sesión firmada del lado del servidor (SessionMiddleware, añadido en main.py)
y una dependencia `require_role()` para el control por ruta.

**Etapa E8 — cierre del acceso por la API.** Este módulo tenía su propio
camino de autenticación (`POST /api/auth/login`) que verificaba correo y
contraseña y nada más. No pasaba por el freno por IP, ni por el bloqueo de
cuenta, ni comprobaba `is_active`, ni exigía el segundo factor del
administrador, ni creaba fila en `sessions` — así que revocar sesiones no lo
cerraba — ni dejaba rastro en `login_attempts` ni en `audit_log`.

Medido antes del cierre: 20 intentos fallidos por esa ruta devolvieron 401
veinte veces sin un solo 429, mientras el mismo ataque por el formulario HTML
frenaba al quinto; y una cuenta de administrador desactivada, bloqueada una
hora y con 99 fallos acumulados entraba por ahí y leía `/api/admin/users`.

Dos cambios lo cierran:

1. Las tres rutas JSON de autenticación quedan retiradas tras
   `LEGACY_JSON_AUTH_ENABLED` (por omisión `false`), devolviendo **404**. Se
   verificó antes de retirarlas que nada las consume: ni una plantilla, ni
   `platform.js`, ni ninguna de las diez suites de prueba — solo el montaje
   en `main.py` y documentación. La bandera es el botón de marcha atrás; el
   registro en la bitácora dice quién las llama todavía.
2. `get_current_user` deja de resolver la sesión por su cuenta y pasa a ser
   un envoltorio de `security.resolve_session_user`, la misma función que
   usan las páginas HTML. Dos implementaciones de un control de acceso son
   una implementación y un agujero.

Se conservan `hash_password`, `verify_password` y `require_role`, que usan
`routers/admin.py` y `routers/owner.py`.
"""
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .schemas import UserOut
from .security import audit, resolve_session_user

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def legacy_json_auth_enabled() -> bool:
    """¿Siguen vivas las rutas JSON de autenticación? Por omisión, no.

    Existe solo como marcha atrás de un despliegue. Se borra el código en
    cuanto pasen dos semanas sin ninguna llamada registrada en la bitácora.
    """
    return os.environ.get("LEGACY_JSON_AUTH_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resuelve el usuario de la petición, o 401.

    Envoltorio de `security.resolve_session_user`: cuenta activa, fila viva
    en `sessions` (revocación y caducidad) y segundo factor del administrador
    se comprueban ahí, en un solo sitio, igual que para las páginas HTML.
    """
    user = resolve_session_user(request, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def require_role(*allowed_roles: str):
    """FastAPI dependency factory: 401 if not logged in, 403 if wrong role.

    Usage: current_user: User = Depends(require_role("admin", "owner"))
    """
    allowed = {r.value if hasattr(r, "value") else r for r in allowed_roles}

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        role_value = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
        if role_value not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: insufficient role")
        return current_user

    return dependency


router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


def _retirada(request: Request, db: Session, ruta: str) -> None:
    """Corta una ruta JSON retirada con 404 y deja constancia de la llamada.

    404 y no 401 a propósito: un 401 confirmaría que la ruta existe. Lo que
    importa aquí es lo otro — que alguien la esté llamando todavía es un dato
    que solo se descubre si queda escrito.
    """
    audit(db, request, "api.auth_legacy_blocked", meta=f"ruta={ruta}")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """RETIRADA en E8. El acceso es por el formulario HTML `POST /login`.

    Esa ruta sí aplica freno por IP, bloqueo de cuenta, `is_active`, la puerta
    del administrador, el segundo factor y la tabla `sessions`.
    """
    if not legacy_json_auth_enabled():
        _retirada(request, db, "/api/auth/login")

    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    request.session.clear()
    request.session["user_id"] = user.id
    return user


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """RETIRADA en E8. El cierre de sesión es `GET /logout`."""
    if not legacy_json_auth_enabled():
        _retirada(request, db, "/api/auth/logout")

    request.session.clear()
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserOut)
def me(request: Request, db: Session = Depends(get_db)):
    """RETIRADA en E8."""
    if not legacy_json_auth_enabled():
        _retirada(request, db, "/api/auth/me")

    return get_current_user(request, db)
