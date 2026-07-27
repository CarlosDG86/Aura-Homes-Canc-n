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
import os
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..auth import verify_password
from ..db import get_db
from ..models import Property, RoleEnum, User

router = APIRouter(tags=["pages"], include_in_schema=False)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../app
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))


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
    owners_by_id = {o.id: o for o in owners}

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "user": user,
            "properties": properties,
            "owners": owners,
            "users": users,
            "owners_by_id": owners_by_id,
        },
    )


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
