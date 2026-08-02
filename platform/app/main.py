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
from .routers import admin, owner, pages, payments, site_content, tenant


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

app = FastAPI(title="Aura Homes Cancún — Platform API", version="2a")

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="aura_platform_session",
    same_site="lax",
)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(APP_DIR))  # .../platform/app -> platform -> repo root

app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")

# Read-only preview of the live site's property photos, for the admin
# properties CRUD (thumbnails only — this does not expose write access).
_site_img_dir = os.path.join(REPO_ROOT, "dist", "assets", "img")
os.makedirs(_site_img_dir, exist_ok=True)
app.mount("/site-images", StaticFiles(directory=_site_img_dir), name="site-images")

app.include_router(auth_router, prefix="/api/auth")
app.include_router(admin.router)
app.include_router(owner.router)
app.include_router(tenant.router)
app.include_router(payments.router)
app.include_router(pages.router)
app.include_router(site_content.router)


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


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_property_site_ref()

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
        print("=" * 72)
        print("SEEDED ADMIN USER (Phase 2a) — CHANGE THIS PASSWORD BEFORE ANY REAL DEPLOYMENT")
        print(f"  email:    {SEED_ADMIN_EMAIL}")
        print(f"  password: {SEED_ADMIN_PASSWORD}")
        print("=" * 72)
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}
