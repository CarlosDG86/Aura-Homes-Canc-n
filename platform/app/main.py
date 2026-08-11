"""FastAPI entrypoint for the Phase 2 platform (2a live, 2b/2c scaffolded).

Run from platform/ with: uvicorn app.main:app --reload
See platform/README.md for setup and seed admin credentials.
"""
import os

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from . import models
from .auth import hash_password
from .auth import router as auth_router
from .db import Base, SessionLocal, engine
from .routers import admin, owner, owner_portal, pages, payments, site_content, tenant
from .mockmode import is_mock, require_legal_clearance_for_live
from .security import (
    ABSOLUTE_TIMEOUT_HOURS,
    CSRFMiddleware,
    SecurityHeadersMiddleware,
    is_production,
    require_secure_secret_key,
    require_secure_seed_password,
)


def _load_dotenv() -> None:
    """Minimal .env loader (no python-dotenv dependency, per INFRA_STACK.md).

    Reads platform/.env if present and sets any KEY=VALUE that is not already
    defined in the real environment — so a shell-exported variable always
    wins over the file. Lets SMTP_* and the other settings live in one
    gitignored file instead of being exported by hand on every run.
    """
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
    )
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except OSError:
        pass


_load_dotenv()

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-secret-key-change-me")
SEED_ADMIN_EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "admin@aura-homes-cancun.local")
SEED_ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "ChangeMe123!")

# E1: aborta el arranque en producción si SECRET_KEY sigue siendo la de ejemplo
# (con ella se pueden falsificar sesiones de administrador). Ver security.py.
require_secure_secret_key(SECRET_KEY)
# Misma lógica para la contraseña con la que se siembra el administrador:
# el valor por defecto es público en el repositorio.
require_secure_seed_password(SEED_ADMIN_PASSWORD)

app = FastAPI(title="Aura Homes Cancún — Platform API", version="2a")

# El orden importa: Starlette ejecuta los middlewares en orden inverso al de
# registro, así que SessionMiddleware debe añadirse DESPUÉS de CSRFMiddleware
# para quedar por fuera y tener la sesión ya cargada cuando CSRF la consulta.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="aura_platform_session",
    same_site="lax",
    https_only=is_production(),  # cookie solo por HTTPS fuera de desarrollo
    max_age=ABSOLUTE_TIMEOUT_HOURS * 3600,
)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(APP_DIR))  # .../platform/app -> platform -> repo root

app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")

# Vista previa (solo lectura) de las fotos del sitio público, para el CRUD de
# propiedades del admin.
#
# Este montaje solo tiene sentido cuando la plataforma corre DENTRO del
# repositorio, con el sitio estático al lado. En el contenedor la plataforma
# viaja sola: `REPO_ROOT` se calcula subiendo dos niveles desde `app/`, que ahí
# llega a la raíz del sistema, y el intento de crear `/dist` mataba el arranque
# con PermissionError — la máquina reiniciaba en bucle y Fly devolvía 502.
#
# Ahora, si la ruta no está disponible, se omite el montaje y la aplicación
# arranca igual: las miniaturas son una comodidad del panel, no algo por lo que
# valga la pena dejar el servicio caído.
_site_img_dir = os.environ.get("SITE_IMAGES_DIR") or os.path.join(
    REPO_ROOT, "dist", "assets", "img"
)
try:
    os.makedirs(_site_img_dir, exist_ok=True)
    app.mount("/site-images", StaticFiles(directory=_site_img_dir), name="site-images")
except OSError as exc:
    print(
        f"[aviso] No se monta /site-images ({_site_img_dir}): {exc}\n"
        "        Las miniaturas del sitio público no estarán disponibles. "
        "Es lo esperado cuando la plataforma corre sola en un contenedor."
    )

app.include_router(auth_router, prefix="/api/auth")
app.include_router(admin.router)
app.include_router(owner.router)
app.include_router(tenant.router)
app.include_router(payments.router)
app.include_router(pages.router)
app.include_router(site_content.router)
app.include_router(owner_portal.router)


@app.get("/")
def root():
    return RedirectResponse(url="/login")


def _ensure_property_site_ref() -> None:
    """Tiny forward migration: add properties.site_ref to an existing DB.

    There is no Alembic in this MVP and Base.metadata.create_all() does not
    alter tables that already exist, so a DB created before this column was
    added needs the column patched in by hand. Idempotent: checks PRAGMA
    table_info first and only ALTERs when the column is missing.
    """
    if not engine.url.get_backend_name().startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(properties)"))}
        # cols is empty only if the table does not exist; create_all ran first,
        # so a non-empty set that lacks site_ref means a pre-existing table.
        if cols and "site_ref" not in cols:
            conn.execute(text("ALTER TABLE properties ADD COLUMN site_ref VARCHAR"))


def _ensure_user_security_columns() -> None:
    """Añade a `users` las columnas de seguridad de E1 en una base ya existente.

    Mismo patrón idempotente que `_ensure_property_site_ref()`: no hay Alembic
    en el MVP y `create_all()` no altera tablas que ya existen, así que las
    bases creadas antes de E1 necesitan estas columnas añadidas a mano.
    Comprueba PRAGMA table_info y solo hace ALTER de lo que falte, así que
    ejecutarlo muchas veces es inofensivo.
    """
    if not engine.url.get_backend_name().startswith("sqlite"):
        return
    wanted = {
        "is_active": "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1",
        "failed_login_count": "ALTER TABLE users ADD COLUMN failed_login_count INTEGER NOT NULL DEFAULT 0",
        "locked_until": "ALTER TABLE users ADD COLUMN locked_until DATETIME",
        "last_login_at": "ALTER TABLE users ADD COLUMN last_login_at DATETIME",
        "contact_phone": "ALTER TABLE users ADD COLUMN contact_phone VARCHAR",
        "must_change_password": "ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0",
        "created_by_user_id": "ALTER TABLE users ADD COLUMN created_by_user_id INTEGER",
        "totp_secret": "ALTER TABLE users ADD COLUMN totp_secret VARCHAR",
        "totp_enabled": "ALTER TABLE users ADD COLUMN totp_enabled BOOLEAN NOT NULL DEFAULT 0",
        "totp_confirmed_at": "ALTER TABLE users ADD COLUMN totp_confirmed_at DATETIME",
        "google_sub": "ALTER TABLE users ADD COLUMN google_sub VARCHAR",
    }
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
        if not cols:
            return  # la tabla no existe todavía; create_all se encarga
        for name, ddl in wanted.items():
            if name not in cols:
                conn.execute(text(ddl))


def _ensure_ticket_columns() -> None:
    """Columnas 2b de `maintenance_tickets` en una base ya existente.

    Mismo patrón idempotente que las otras dos migraciones.
    """
    if not engine.url.get_backend_name().startswith("sqlite"):
        return
    wanted = {
        "public_ref": "ALTER TABLE maintenance_tickets ADD COLUMN public_ref VARCHAR",
        "lease_id": "ALTER TABLE maintenance_tickets ADD COLUMN lease_id INTEGER",
        "category": "ALTER TABLE maintenance_tickets ADD COLUMN category VARCHAR",
        "priority": "ALTER TABLE maintenance_tickets ADD COLUMN priority VARCHAR",
        "location_in_unit": "ALTER TABLE maintenance_tickets ADD COLUMN location_in_unit VARCHAR",
        "created_via": "ALTER TABLE maintenance_tickets ADD COLUMN created_via VARCHAR",
        "assigned_to_user_id": "ALTER TABLE maintenance_tickets ADD COLUMN assigned_to_user_id INTEGER",
        "resolved_at": "ALTER TABLE maintenance_tickets ADD COLUMN resolved_at DATETIME",
        "resolution_notes": "ALTER TABLE maintenance_tickets ADD COLUMN resolution_notes TEXT",
        "ai_summary": "ALTER TABLE maintenance_tickets ADD COLUMN ai_summary TEXT",
        "ai_confidence": "ALTER TABLE maintenance_tickets ADD COLUMN ai_confidence NUMERIC",
    }
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(maintenance_tickets)"))}
        if not cols:
            return
        for name, ddl in wanted.items():
            if name not in cols:
                conn.execute(text(ddl))
        # `leases` gana una columna en E4: quién dio de alta el arrendamiento.
        lease_cols = {
            "created_by_user_id": "ALTER TABLE leases ADD COLUMN created_by_user_id INTEGER",
        }
        lcols = {row[1] for row in conn.execute(text("PRAGMA table_info(leases)"))}
        if lcols:
            for name, ddl in lease_cols.items():
                if name not in lcols:
                    conn.execute(text(ddl))


@app.on_event("startup")
def on_startup() -> None:
    # Candado legal: en modo real exige la referencia del visto bueno de Legal.
    # Mientras no exista, la app no puede guardar datos personales reales.
    require_legal_clearance_for_live()

    Base.metadata.create_all(bind=engine)
    _ensure_property_site_ref()
    _ensure_user_security_columns()
    _ensure_ticket_columns()

    if is_mock():
        print("=" * 72)
        print("MODO PRUEBAS (DATA_MODE=mock)")
        print(f"  Base de datos: {engine.url}")
        print("  Solo se aceptan correos de dominios de prueba y teléfonos +52 555 01XX XXXX.")
        print("  No se envían correos. Los datos reales de platform.db NO se tocan.")
        print("=" * 72)

    db = SessionLocal()
    try:
        existing_admin = db.query(models.User).filter(models.User.role == models.RoleEnum.admin).first()
        if existing_admin:
            return
        admin_user = models.User(
            name="Aura Admin",
            email=SEED_ADMIN_EMAIL.lower().strip(),
            password_hash=hash_password(SEED_ADMIN_PASSWORD),
            role=models.RoleEnum.admin,
        )
        db.add(admin_user)
        db.commit()
        # La contraseña NUNCA se imprime en producción. Los registros de un
        # servidor se conservan, se consultan desde el panel del proveedor y a
        # menudo se reenvían a otros servicios: escribir ahí la clave del
        # administrador equivale a guardarla en texto plano en un sitio que no
        # controlamos. En desarrollo sí se muestra, porque ahí la comodidad de
        # verla al arrancar pesa más y no hay registros persistentes.
        print("=" * 72)
        print("USUARIO ADMINISTRADOR CREADO")
        print(f"  correo: {SEED_ADMIN_EMAIL}")
        if is_production():
            print("  contraseña: la definida en SEED_ADMIN_PASSWORD (no se muestra aquí)")
        else:
            print(f"  contraseña: {SEED_ADMIN_PASSWORD}")
        print("=" * 72)
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}
