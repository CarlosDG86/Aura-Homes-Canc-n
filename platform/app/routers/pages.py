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

from .. import identity
from ..auth import hash_password, verify_password
from ..db import get_db
from ..email_utils import send_temp_password_email
from ..mockmode import validate_mock_email, validate_mock_phone
from ..models import Property, PropertyStatusEnum, RoleEnum, User
from ..security import (
    account_locked_until,
    audit,
    client_ip,
    ip_is_rate_limited,
    create_server_session,
    mark_session_start,
    register_failed_login,
    register_successful_login,
    register_template_globals,
    resolve_server_session,
    revoke_all_sessions,
    revoke_session,
    rotate_csrf_token,
)

router = APIRouter(tags=["pages"], include_in_schema=False)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../app
REPO_ROOT = os.path.dirname(os.path.dirname(APP_DIR))  # .../platform/app -> platform -> repo root
SITE_PROPERTIES_JSON = os.path.join(REPO_ROOT, "data", "properties.json")
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))
register_template_globals(templates)  # expone csrf_input(request) a las plantillas


def _flash(request: Request, kind: str, message: str) -> None:
    """Stash a one-shot message for the next page render (PRG pattern)."""
    request.session["flash"] = {"kind": kind, "message": message}


def _pop_flash(request: Request) -> Optional[dict]:
    return request.session.pop("flash", None)


def _current_user_or_none(request: Request, db: Session) -> Optional[User]:
    """Same resolution as auth.get_current_user, but returns None instead
    of raising, since these are page routes that redirect instead of 401.

    E1: además aplica la caducidad de sesión (inactividad y límite absoluto)
    y expulsa a las cuentas desactivadas, para que dar de baja a alguien surta
    efecto de inmediato en vez de esperar a que cierre sesión.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, user_id)
    if not user:
        request.session.clear()
        return None
    if not getattr(user, "is_active", True):
        request.session.clear()
        return None

    # La cookie dice quién dice ser; la tabla `sessions` decide si sigue
    # teniendo derecho a entrar. Esto es lo que permite revocar de verdad:
    # sin fila viva, la cookie no vale aunque esté firmada y sin caducar.
    is_admin = user.role == RoleEnum.admin
    if resolve_server_session(db, request, is_admin=is_admin) is None:
        request.session.clear()
        return None
    # Última comprobación: una sesión de administrador sin segundo factor
    # verificado no vale, aunque la cookie y la fila de sesión sean correctas.
    if not identity.totp_satisfied(request, user):
        request.session.clear()
        return None
    return user


def _home_for(user: User) -> str:
    """Panel que le corresponde a cada rol.

    Los tres roles deben estar contemplados. Cuando esta función devolvía
    `/owner` para todo lo que no fuera admin, un inquilino recién creado
    entraba en un bucle de redirecciones: iniciaba sesión, se le enviaba a
    `/owner`, `/owner` lo rebotaba a `/login`, y `/login` —viendo que ya tenía
    sesión— lo devolvía a `/owner`. El navegador cortaba con
    ERR_TOO_MANY_REDIRECTS.
    """
    if user.role == RoleEnum.admin:
        return "/admin"
    if user.role == RoleEnum.tenant:
        return "/inquilino"
    return "/owner"


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


@router.get("/acceso/propietarios", response_class=HTMLResponse)
def login_owners(request: Request, db: Session = Depends(get_db)):
    """Acceso para propietarios, enlazado desde el sitio público.

    Es la misma pantalla de acceso con un encabezado distinto: separar las dos
    entradas ayuda a la persona a saber que está en el sitio correcto, pero el
    rol real sale de la base, nunca de la URL. Entrar por aquí con una cuenta
    de inquilino funciona y lleva a su propio panel — sería confuso rechazar a
    alguien por usar la puerta de al lado.
    """
    return _login_page_for(request, db, audience="owner")


@router.get("/acceso/inquilinos", response_class=HTMLResponse)
def login_tenants(request: Request, db: Session = Depends(get_db)):
    """Acceso para inquilinos, enlazado desde el sitio público."""
    return _login_page_for(request, db, audience="tenant")


def _login_page_for(request: Request, db: Session, audience: str):
    user = _current_user_or_none(request, db)
    if user:
        return RedirectResponse(url=_home_for(user), status_code=302)
    titles = {
        "owner": ("Acceso para propietarios", "Administra tus propiedades, inquilinos y reportes."),
        "tenant": ("Acceso para inquilinos", "Reporta problemas y comunícate con tu propietario."),
    }
    title, subtitle = titles.get(audience, ("Iniciar sesión", ""))
    return templates.TemplateResponse(
        request=request, name="login.html",
        context={"error": None, "email": "", "page_title": title, "page_subtitle": subtitle},
    )


#: Un único mensaje para credenciales malas, cuenta inexistente, cuenta
#: desactivada y cuenta bloqueada. Distinguirlos le confirmaría a un atacante
#: qué correos existen (enumeración de usuarios, SECURITY.md §1.2).
_LOGIN_GENERIC_ERROR = "Correo o contraseña incorrectos."


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(""),  # lo valida CSRFMiddleware; se declara para que FastAPI no lo rechace
):
    ip = client_ip(request)

    def _fail(message: str = _LOGIN_GENERIC_ERROR, status_code: int = 401):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": message, "email": email},
            status_code=status_code,
        )

    # Freno por IP antes de tocar la base: corta el barrido de correos.
    if ip_is_rate_limited(db, ip):
        audit(db, request, "login.rate_limited", meta=f"ip={ip}")
        return _fail(
            "Demasiados intentos desde esta conexión. Espera un minuto e inténtalo de nuevo.",
            status_code=429,
        )

    user = db.query(User).filter(User.email == email.lower().strip()).first()

    # Cuenta bloqueada: no se comprueba la contraseña siquiera.
    if user is not None and account_locked_until(user):
        register_failed_login(db, None, email, ip)
        audit(db, request, "login.locked", actor=user, object_type="user", object_id=user.id)
        return _fail()

    if user is None or not verify_password(password, user.password_hash):
        register_failed_login(db, user, email, ip)
        audit(db, request, "login.failed", meta=f"email={email[:120]}")
        return _fail()

    # Un administrador solo puede entrar por su puerta. Mensaje genérico a
    # propósito: si dijéramos "usa la otra URL" estaríamos revelando que ese
    # correo es de administrador y que existe otra puerta.
    if (identity.admin_gate_enabled()
            and user.role == RoleEnum.admin
            and not request.session.get(identity.ADMIN_GATE_KEY)):
        register_failed_login(db, None, email, ip)
        audit(db, request, "login.admin_wrong_door", meta=f"email={email[:120]}")
        return _fail()

    # Cuenta desactivada (baja lógica): mismo mensaje genérico.
    if not getattr(user, "is_active", True):
        register_failed_login(db, None, email, ip)
        audit(db, request, "login.inactive", actor=user, object_type="user", object_id=user.id)
        return _fail()

    # Éxito. clear() descarta el identificador de sesión anterior — es lo que
    # evita la fijación de sesión (SECURITY.md §3): un atacante que plantó una
    # cookie antes del acceso no obtiene una sesión autenticada con ella.
    # Contraseña correcta. Si la cuenta exige segundo factor, la sesión NO se
    # autentica todavía: solo se recuerda quién está a medio entrar. Sin el
    # código, esta sesión no abre ninguna pantalla.
    gate = request.session.get(identity.ADMIN_GATE_KEY)
    request.session.clear()
    if gate:
        request.session[identity.ADMIN_GATE_KEY] = True
    rotate_csrf_token(request)

    if identity.totp_required_for(user):
        identity.start_pending_login(request, user)
        audit(db, request, "login.password_ok_awaiting_totp", actor=user,
              object_type="user", object_id=user.id)
        return RedirectResponse(url="/2fa", status_code=302)

    request.session["user_id"] = user.id
    mark_session_start(request)
    create_server_session(db, request, user)
    register_successful_login(db, user, email, ip)
    audit(db, request, "login.success", actor=user, object_type="user", object_id=user.id)
    return RedirectResponse(url=_home_for(user), status_code=302)


@router.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    # Limpiar la cookie no basta: si alguien tiene una copia, seguiría valiendo.
    # Revocar la fila la invalida para todo el mundo, de inmediato.
    sid = request.session.get("sid")
    if sid:
        revoke_session(db, sid, "logout")
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)




# --- Segundo factor y puerta de administración (E2) -------------------------


@router.get(identity.admin_login_path(), response_class=HTMLResponse,
            include_in_schema=False)
def admin_login_page(request: Request, db: Session = Depends(get_db)):
    """Acceso de administrador por una URL no enlazada.

    Marca la sesión como "entró por la puerta correcta". Sin esa marca, una
    cuenta de administrador no puede iniciar sesión por `/login`: así el
    formulario público no sirve para atacar la cuenta que lo ve todo.
    """
    user = _current_user_or_none(request, db)
    if user:
        return RedirectResponse(url=_home_for(user), status_code=302)
    request.session[identity.ADMIN_GATE_KEY] = True
    resp = templates.TemplateResponse(
        request=request, name="login.html",
        context={"error": None, "email": "",
                 "page_title": "Acceso interno",
                 "page_subtitle": "Uso exclusivo del administrador."},
    )
    # Fuera de los buscadores: la ofuscación no sirve de nada si Google la indexa.
    resp.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return resp


@router.get("/2fa", response_class=HTMLResponse)
def totp_page(request: Request, db: Session = Depends(get_db)):
    """Pide el código, o guía la configuración inicial si aún no lo tiene."""
    uid = identity.pending_user_id(request)
    if not uid:
        return RedirectResponse(url="/login", status_code=302)
    user = db.get(User, uid)
    if not user:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=302)

    if not user.totp_enabled:
        # Alta del segundo factor. El secreto vive en la sesión hasta que la
        # persona demuestra que su app lo guardó bien: si se escribiera antes
        # en la base y cerrara la ventana, quedaría bloqueada fuera.
        secret = request.session.get("_totp_setup_secret")
        if not secret:
            secret = identity.new_secret()
            request.session["_totp_setup_secret"] = secret
        uri = identity.provisioning_uri(user, secret)
        return templates.TemplateResponse(
            request=request, name="totp_setup.html",
            context={"error": None, "secret": secret,
                     "qr": identity.qr_data_uri(uri), "user_email": user.email},
        )

    return templates.TemplateResponse(
        request=request, name="totp_verify.html", context={"error": None}
    )


@router.post("/2fa", response_class=HTMLResponse)
def totp_submit(request: Request, db: Session = Depends(get_db),
                code: str = Form(...), csrf_token: str = Form("")):
    uid = identity.pending_user_id(request)
    if not uid:
        return RedirectResponse(url="/login", status_code=302)
    user = db.get(User, uid)
    if not user:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=302)

    ip = client_ip(request)
    setup_secret = request.session.get("_totp_setup_secret")
    secret = user.totp_secret if user.totp_enabled else setup_secret

    if not identity.verify_code(secret, code):
        # Un código equivocado cuenta como intento fallido: sin esto, el
        # segundo factor sería adivinable a fuerza bruta (solo un millón de
        # combinaciones) sin ninguna traba.
        register_failed_login(db, user, user.email, ip)
        audit(db, request, "login.totp_failed", actor=user,
              object_type="user", object_id=user.id)
        name = "totp_setup.html" if not user.totp_enabled else "totp_verify.html"
        ctx = {"error": "Código incorrecto. Revisa que sea el actual de tu app."}
        if not user.totp_enabled:
            uri = identity.provisioning_uri(user, setup_secret)
            ctx.update({"secret": setup_secret, "qr": identity.qr_data_uri(uri),
                        "user_email": user.email})
        return templates.TemplateResponse(request=request, name=name,
                                          context=ctx, status_code=401)

    if not user.totp_enabled:
        identity.enable_totp(db, user, setup_secret)
        audit(db, request, "user.totp_enabled", actor=user,
              object_type="user", object_id=user.id)
    request.session.pop("_totp_setup_secret", None)

    # Segundo factor superado: recién aquí la sesión queda autenticada.
    identity.clear_pending_login(request)
    identity.mark_totp_verified(request)
    request.session["user_id"] = user.id
    rotate_csrf_token(request)
    mark_session_start(request)
    create_server_session(db, request, user)
    register_successful_login(db, user, user.email, ip)
    audit(db, request, "login.success", actor=user, object_type="user", object_id=user.id)
    return RedirectResponse(url=_home_for(user), status_code=302)

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
            "active": "admin",
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
    # En modo simulación esta alta también debe rechazar datos reales. Faltaba
    # aquí: solo se validaba en el alta de inquilinos, así que por esta puerta
    # entraban correos de personas reales a la base de pruebas.
    validate_mock_email(email)
    validate_mock_phone(phone)
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
        # Tiene sesión válida, solo no le toca esta pantalla: se le manda a la
        # suya, NO al formulario de acceso. Rebotar a `/login` a alguien que ya
        # inició sesión es lo que cerraba el bucle de redirecciones, porque
        # `/login` devuelve a los usuarios con sesión a su panel.
        return RedirectResponse(url=_home_for(user), status_code=302)

    # El filtrado por pertenencia vive en scoping.py: `owned_properties` acota
    # por `owner_id == user.id` incluso para un admin, igual que routers/owner.py.
    from ..mockmode import template_context
    from ..models import MaintenanceTicket, Message, TicketStatusEnum
    from ..scoping import owned_properties, scoped_tickets

    properties = owned_properties(db, user).order_by(Property.id).all()

    tickets = scoped_tickets(db, user).all()
    open_tickets = sum(1 for t in tickets if t.status != TicketStatusEnum.resolved)
    urgent_tickets = sum(
        1 for t in tickets
        if t.priority and getattr(t.priority, "value", None) == "emergencia"
        and t.status != TicketStatusEnum.resolved
    )

    unread_messages = (
        db.query(Message)
        .filter(Message.recipient_user_id == user.id, Message.read_at.is_(None))
        .count()
    )

    return templates.TemplateResponse(
        request=request,
        name="owner.html",
        context={
            "active": "owner",
            "user": user,
            "properties": properties,
            "open_tickets": open_tickets,
            "urgent_tickets": urgent_tickets,
            "unread_messages": unread_messages,
            **template_context(),
        },
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

    # Una contraseña restablecida no puede seguir dando acceso donde ya había
    # sesión abierta: si se restablece porque la anterior se comprometió,
    # dejar vivas las sesiones existentes anula el propósito del cambio.
    closed = revoke_all_sessions(db, target.id, "password_reset")
    audit(db, request, "user.password_reset", actor=_current_user_or_none(request, db),
          object_type="user", object_id=target.id, meta=f"sesiones_cerradas={closed}")

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


# --- Sesiones activas (SECURITY.md §3) --------------------------------------


@router.get("/sesiones", response_class=HTMLResponse)
def sessions_page(request: Request, db: Session = Depends(get_db)):
    """Dispositivos donde la cuenta tiene sesión abierta."""
    user = _current_user_or_none(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from ..mockmode import template_context
    from ..security import active_sessions

    return templates.TemplateResponse(
        request=request,
        name="sessions.html",
        context={
            "active": "sessions",
            "user": user,
            "sessions": active_sessions(db, user.id),
            "current_sid": request.session.get("sid"),
            "closed": request.session.pop("sessions_closed", None),
            **template_context(),
        },
    )


@router.post("/sesiones/cerrar-otras")
def close_other_sessions(request: Request, db: Session = Depends(get_db),
                         csrf_token: str = Form("")):
    """Cierra las demás sesiones y conserva la actual.

    Es la acción que sirve cuando sospechas que alguien más entró: cierras
    todo lo demás sin quedarte fuera tú.
    """
    user = _current_user_or_none(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    sid = request.session.get("sid")
    closed = revoke_all_sessions(db, user.id, "user_closed_others", except_sid=sid)
    audit(db, request, "session.closed_others", actor=user, object_type="user",
          object_id=user.id, meta=f"cerradas={closed}")
    request.session["sessions_closed"] = closed
    return RedirectResponse(url="/sesiones", status_code=302)
