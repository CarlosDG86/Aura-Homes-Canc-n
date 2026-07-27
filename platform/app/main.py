"""FastAPI entrypoint for the Phase 2 platform (2a live, 2b/2c scaffolded).

Run from platform/ with: uvicorn app.main:app --reload
See platform/README.md for setup and seed admin credentials.
"""
import os

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import models
from .auth import hash_password
from .auth import router as auth_router
from .db import Base, SessionLocal, engine
from .routers import admin, owner, pages, payments, site_content, tenant

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


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)

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
