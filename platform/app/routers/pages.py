"""Server-rendered HTML pages: login form + role dashboards.

This is the human-usable front door for the platform. The JSON API
(`auth.py`, `routers/admin.py`, `routers/owner.py`) already existed and
still exists unchanged; these routes just give a browser something to
render and a form to submit.

Deliberately queries the DB directly with the same models/session pattern
used by `routers/admin.py` and `routers/owner.py` (rather than having the
server make an HTTP call back to its own JSON API) so there is exactly one
place the owner-scoping filter (`Property.owner_id == current_user.id`)
lives, instead of two copies that could drift apart.
"""
import json
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import hash_password, verify_password
from ..db import get_db
from ..email_utils import send_temp_password_email
from ..models import Property, PropertyStatusEnum, RoleEnum, User

router = APIRouter(tags=["pages"], include_in_schema=False)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../app
REPO_ROOT = os.path.dirname(os.path.dirname(APP_DIR))  # .../platform/app -> platform -> repo root
SITE_PROPERTIES_JSON = os.path.join(REPO_ROOT, "data", "properties.json")
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))


def _flash(request: Request, kind: str, message: str) -> None:
    """Stash a one-shot message for the next page render (PRG pattern)."""
    request.session["flash"] = {"kind": kind, "message": message}


def _pop_flash(request: Request) -> Optional[dict]:
    return request.session.pop("flash", None)


def _current_user_or_none(request: Request, db: Session) -> Optional[User]:
    """Same resolution as auth.get_current_user, but returns None instead
    of raising, since these are page routes that redirect instead of 401."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, user_id)
    if not user:
        request.session.clear()
        return None
    return user


def _home_for(user: User) -> str:
    return "/admin" if user.role == RoleEnum.admin else "/owner"


def _load_site_properties() -> list:
    """Read the public site's properties (data/properties.json). Returns [] on
    any read/parse error — callers treat that as 'no site properties'."""
    try:
        with open(SITE_PROPERTIES_JSON, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


# --- Login / logout ---------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    user = _current_user_or_none(request, db)
    if user:
        return RedirectResponse(url=_home_for(user), status_code=302)
    return templates.TemplateResponse(
        request=request, name="login.html", context={"error": None, "email": ""}
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...),
):
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Correo o contraseña incorrectos.", "email": email},
            status_code=401,
        )
    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse(url=_home_for(user), status_code=302)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


# --- Dashboards ---------------------------------------------------------


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = _current_user_or_none(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.role != RoleEnum.admin:
        # Logged in, just not allowed here — send them to their own home
        # rather than bouncing an authenticated user back to the login form.
        return RedirectResponse(url=_home_for(user), status_code=302)

    properties = db.query(Property).order_by(Property.id).all()
    owners = db.query(User).filter(User.role == RoleEnum.owner).order_by(User.id).all()
    users = db.query(User).order_by(User.id).all()
    users_by_id = {u.id: u for u in users}
    owners_by_id = {o.id: o for o in owners}

    # Build the selectable site-property rows for the sync control: every entry
    # in data/properties.json, annotated with whether it is already mirrored in
    # the platform DB and to which owner.
    synced_by_ref = {p.site_ref: p for p in properties if p.site_ref}
    site_rows = []
    for entry in _load_site_properties():
        ref = entry.get("id")
        if not ref:
            continue
        mirror = synced_by_ref.get(ref)
        owner_name = None
        if mirror:
            owner = users_by_id.get(mirror.owner_id)
            owner_name = owner.name if owner else f"#{mirror.owner_id}"
        site_rows.append(
            {
                "id": ref,
                "title": (entry.get("title") or {}).get("es") or ref,
                "zone": entry.get("zone"),
                "status": entry.get("status") or "available",
                "synced": mirror is not None,
                "owner_name": owner_name,
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "user": user,
            "properties": properties,
            "owners": owners,
            "users": users,
            "owners_by_id": owners_by_id,
            "site_rows": site_rows,
            "flash": _pop_flash(request),
        },
    )


# --- Admin actions: create owner + sync site properties ---------------------


def _require_admin(request: Request, db: Session) -> Optional[User]:
    """Resolve the current user and confirm role=admin, else None."""
    user = _current_user_or_none(request, db)
    if not user or user.role != RoleEnum.admin:
        return None
    return user


@router.post("/admin/owners")
def create_owner_submit(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    password: str = Form(...),
):
    """Server-rendered "alta de propietario". Mirrors POST /api/admin/users
    (admin.py) but fixes role=owner and redirects back to the dashboard."""
    if not _require_admin(request, db):
        return RedirectResponse(url="/login", status_code=302)

    name = name.strip()
    email = email.lower().strip()
    if not name or not email or not password:
        _flash(request, "error", "Nombre, correo y contraseña son obligatorios.")
        return RedirectResponse(url="/admin", status_code=302)
    if db.query(User).filter(User.email == email).first():
        _flash(request, "error", f"El correo {email} ya está registrado.")
        return RedirectResponse(url="/admin", status_code=302)

    owner = User(
        name=name,
        email=email,
        phone=phone.strip() or None,
        password_hash=hash_password(password),
        role=RoleEnum.owner,
    )
    db.add(owner)
    db.commit()

    # Email the temporary password to the new owner, advising them to change
    # it. In dev (no SMTP configured) nothing is sent; the flash says so.
    mail = send_temp_password_email(email, name, password)
    if mail.sent:
        _flash(request, "success", f"Propietario «{name}» dado de alta. Clave temporal enviada a {email}.")
    elif not mail.configured:
        _flash(request, "success", f"Propietario «{name}» dado de alta. (Correo NO enviado: SMTP no está configurado — configura las variables SMTP_* para enviar la clave por correo.)")
    else:
        _flash(request, "error", f"Propietario «{name}» dado de alta, pero el correo falló: {mail.error}")
    return RedirectResponse(url="/admin", status_code=302)


def _mirror_fields_from_site(entry: dict) -> dict:
    """Map a data/properties.json entry to the internal Property mirror fields.
    Spanish is the primary language for the single-value mirror columns."""
    status = PropertyStatusEnum.rented if entry.get("status") == "rented" else PropertyStatusEnum.available
    title = entry.get("title") or {}
    desc = entry.get("desc") or {}
    return {
        "title": title.get("es") or title.get("en") or entry.get("id", "—"),
        "zone": entry.get("zone"),
        "city": "Cancún",
        "price_amount": entry.get("priceMXN"),
        "price_currency": "MXN",
        "status": status,
        "bedrooms": entry.get("beds"),
        "bathrooms": entry.get("baths"),
        "area_m2": entry.get("area"),
        "description": desc.get("es") or desc.get("en"),
    }


@router.post("/admin/sync-site-properties")
def sync_site_properties(
    request: Request,
    db: Session = Depends(get_db),
    owner_id: int = Form(...),
    site_refs: List[str] = Form(default=[]),
):
    """Mirror the SELECTED public-site properties (data/properties.json) into
    the internal DB, linked by site_ref, and assign them to the chosen owner.

    The site stays the source of truth for content: for each selected ref we
    refresh the mirrored fields from the JSON. Ownership follows the explicit
    selection — a selected ref is (re)assigned to the chosen owner, so the
    admin can spread different houses across different owners. Unselected refs
    are left untouched."""
    if not _require_admin(request, db):
        return RedirectResponse(url="/login", status_code=302)

    owner = db.query(User).filter(User.id == owner_id, User.role == RoleEnum.owner).first()
    if not owner:
        _flash(request, "error", "Selecciona un propietario válido antes de sincronizar.")
        return RedirectResponse(url="/admin", status_code=302)

    selected = {ref for ref in site_refs if ref}
    if not selected:
        _flash(request, "error", "Marca al menos una casa para sincronizar.")
        return RedirectResponse(url="/admin", status_code=302)

    by_id = {e.get("id"): e for e in _load_site_properties() if e.get("id")}

    created = 0
    updated = 0
    reassigned = 0
    skipped = 0
    for ref in selected:
        entry = by_id.get(ref)
        if not entry:
            skipped += 1
            continue
        fields = _mirror_fields_from_site(entry)
        existing = db.query(Property).filter(Property.site_ref == ref).first()
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            if existing.owner_id != owner.id:
                existing.owner_id = owner.id
                reassigned += 1
            else:
                updated += 1
        else:
            db.add(Property(site_ref=ref, owner_id=owner.id, **fields))
            created += 1
    db.commit()

    parts = [f"{created} creada(s)", f"{updated} actualizada(s)", f"{reassigned} reasignada(s)"]
    if skipped:
        parts.append(f"{skipped} sin coincidencia en el sitio")
    _flash(request, "success", f"Sincronización con «{owner.name}»: " + ", ".join(parts) + ".")
    return RedirectResponse(url="/admin", status_code=302)


@router.get("/owner", response_class=HTMLResponse)
def owner_dashboard(request: Request, db: Session = Depends(get_db)):
    user = _current_user_or_none(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.role not in (RoleEnum.owner, RoleEnum.admin):
        return RedirectResponse(url="/login", status_code=302)

    # Same scoping rule as routers/owner.py: always filter by the logged-in
    # user's own id, admin included — this is what prevents cross-owner
    # data leakage, not the role check above.
    properties = (
        db.query(Property)
        .filter(Property.owner_id == user.id)
        .order_by(Property.id)
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="owner.html",
        context={"user": user, "properties": properties},
    )


# --- User administration submodule -----------------------------------------


def _admins_count(db: Session) -> int:
    return db.query(User).filter(User.role == RoleEnum.admin).count()


@router.get("/admin/users/{user_id}", response_class=HTMLResponse)
def user_edit_page(user_id: int, request: Request, db: Session = Depends(get_db)):
    if not _require_admin(request, db):
        return RedirectResponse(url="/login", status_code=302)
    target = db.get(User, user_id)
    if not target:
        _flash(request, "error", f"Usuario #{user_id} no existe.")
        return RedirectResponse(url="/admin", status_code=302)

    owned = db.query(Property).filter(Property.owner_id == user_id).order_by(Property.id).all()
    others_q = db.query(Property).filter(Property.owner_id != user_id).order_by(Property.id).all()
    users_by_id = {u.id: u for u in db.query(User).all()}
    others = [
        {
            "id": p.id,
            "site_ref": p.site_ref,
            "title": p.title,
            "owner_name": (users_by_id.get(p.owner_id).name if users_by_id.get(p.owner_id) else f"#{p.owner_id}"),
        }
        for p in others_q
    ]

    return templates.TemplateResponse(
        request=request,
        name="admin_user_form.html",
        context={
            "user": db.get(User, request.session.get("user_id")),
            "target": target,
            "owned": owned,
            "others": others,
            "flash": _pop_flash(request),
        },
    )


@router.post("/admin/users/{user_id}")
def user_update_submit(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    role: str = Form(...),
):
    """Update a user's basic data and role."""
    if not _require_admin(request, db):
        return RedirectResponse(url="/login", status_code=302)
    target = db.get(User, user_id)
    if not target:
        _flash(request, "error", f"Usuario #{user_id} no existe.")
        return RedirectResponse(url="/admin", status_code=302)

    name = name.strip()
    email = email.lower().strip()
    if not name or not email:
        _flash(request, "error", "Nombre y correo son obligatorios.")
        return RedirectResponse(url=f"/admin/users/{user_id}", status_code=302)
    try:
        new_role = RoleEnum(role)
    except ValueError:
        _flash(request, "error", "Rol inválido.")
        return RedirectResponse(url=f"/admin/users/{user_id}", status_code=302)

    clash = db.query(User).filter(User.email == email, User.id != user_id).first()
    if clash:
        _flash(request, "error", f"El correo {email} ya lo usa otro usuario.")
        return RedirectResponse(url=f"/admin/users/{user_id}", status_code=302)

    # Don't let the last admin be demoted — that would lock everyone out.
    if target.role == RoleEnum.admin and new_role != RoleEnum.admin and _admins_count(db) <= 1:
        _flash(request, "error", "No puedes quitar el rol admin al único administrador.")
        return RedirectResponse(url=f"/admin/users/{user_id}", status_code=302)

    target.name = name
    target.email = email
    target.phone = phone.strip() or None
    target.role = new_role
    db.commit()
    _flash(request, "success", f"Datos de «{name}» actualizados.")
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=302)


@router.post("/admin/users/{user_id}/password")
def user_password_submit(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    new_password: str = Form(...),
    send_email: Optional[str] = Form(None),
):
    """Reset a user's password to a new temporary value, optionally emailing it."""
    if not _require_admin(request, db):
        return RedirectResponse(url="/login", status_code=302)
    target = db.get(User, user_id)
    if not target:
        _flash(request, "error", f"Usuario #{user_id} no existe.")
        return RedirectResponse(url="/admin", status_code=302)

    if len(new_password) < 8:
        _flash(request, "error", "La nueva contraseña debe tener al menos 8 caracteres.")
        return RedirectResponse(url=f"/admin/users/{user_id}", status_code=302)

    target.password_hash = hash_password(new_password)
    db.commit()

    if send_email:
        mail = send_temp_password_email(target.email, target.name, new_password)
        if mail.sent:
            _flash(request, "success", f"Contraseña restablecida y enviada a {target.email}.")
        elif not mail.configured:
            _flash(request, "success", "Contraseña restablecida. (Correo NO enviado: SMTP no está configurado.)")
        else:
            _flash(request, "error", f"Contraseña restablecida, pero el correo falló: {mail.error}")
    else:
        _flash(request, "success", "Contraseña restablecida.")
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=302)


@router.post("/admin/users/{user_id}/properties")
def user_assign_properties(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    property_ids: List[int] = Form(default=[]),
):
    """Reassign the selected properties (currently owned by others) to this user."""
    if not _require_admin(request, db):
        return RedirectResponse(url="/login", status_code=302)
    target = db.get(User, user_id)
    if not target:
        _flash(request, "error", f"Usuario #{user_id} no existe.")
        return RedirectResponse(url="/admin", status_code=302)

    moved = 0
    for pid in property_ids:
        prop = db.get(Property, pid)
        if prop and prop.owner_id != user_id:
            prop.owner_id = user_id
            moved += 1
    db.commit()
    _flash(request, "success", f"{moved} casa(s) reasignada(s) a «{target.name}».")
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=302)
