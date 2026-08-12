"""Menu lateral, CSP endurecida, asignacion de tickets y submenu de pagos."""
import os, sys, re, tempfile, pathlib

TMP = tempfile.mkdtemp(prefix="aura_ui_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(TMP,'t.db')}"
os.environ["UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["APP_ENV"] = "dev"; os.environ["DATA_MODE"] = "mock"
os.environ["TENANT_MODULE_ENABLED"] = "true"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.auth import hash_password
from app.models import (User, Property, Lease, RoleEnum, LeaseStatusEnum,
                        MaintenanceTicket, TicketStatusEnum, PlatformSetting)

ok = fail = 0
def check(n, c, e=""):
    global ok, fail
    if c: ok += 1; print(f"  PASS  {n}")
    else: fail += 1; print(f"  FAIL  {n} {e}")

def tok(cl, url):
    r = cl.get(url)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    return m.group(1) if m else None

def login(cl, email, pw="Pass123456!"):
    """Inicio de sesion completo: incluye el segundo factor del admin (E2)."""
    return login_completo(cl, email, pw)


# --- E2: el admin ahora exige segundo factor -------------------------------
import pyotp as _pyotp

def _totp_secret_for(email):
    """Secreto del segundo factor: de la pantalla de alta o de la base."""
    from app.db import SessionLocal as _SL
    from app.models import User as _U
    _db = _SL(); _u = _db.query(_U).filter(_U.email == email).first()
    _s = _u.totp_secret if _u else None; _db.close(); return _s

def completar_2fa(cl, email):
    """Completa el paso del codigo. Idempotente: sirve para el alta y despues."""
    r = cl.get("/2fa")
    m = re.search(r'<code>([A-Z2-7]{16,})</code>', r.text)
    secret = m.group(1) if m else _totp_secret_for(email)
    t = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
    return cl.post("/2fa", data={"code": _pyotp.TOTP(secret).now(), "csrf_token": t},
                   follow_redirects=False)

def login_completo(cl, email, password="Pass123456!"):
    """Inicio de sesion de punta a punta, con segundo factor si hace falta."""
    rr = cl.get("/login")
    t = re.search(r'name="csrf_token" value="([^"]+)"', rr.text).group(1)
    r = cl.post("/login", data={"email": email, "password": password, "csrf_token": t},
                follow_redirects=False)
    if r.headers.get("location") == "/2fa":
        r = completar_2fa(cl, email)
    return r

with TestClient(app) as c:
    db = SessionLocal()
    def mk(n, e, r):
        u = User(name=n, email=e, password_hash=hash_password("Pass123456!"), role=r)
        db.add(u); db.commit(); db.refresh(u); return u
    adm = db.query(User).filter(User.role == RoleEnum.admin).first()
    adm.email = "adm@example.com"; adm.password_hash = hash_password("Pass123456!")
    db.commit()
    ow = mk("Owner A", "oa@example.com", RoleEnum.owner)
    te = mk("Inq A", "ia@example.com", RoleEnum.tenant)
    pr = Property(owner_id=ow.id, title="Casa A"); db.add(pr); db.commit(); db.refresh(pr)
    db.add(Lease(property_id=pr.id, tenant_id=te.id, status=LeaseStatusEnum.active)); db.commit()
    tk = MaintenanceTicket(property_id=pr.id, reported_by_user_id=te.id, title="Fuga",
                           status=TicketStatusEnum.open)
    db.add(tk); db.commit(); db.refresh(tk)
    TKID, TEID = tk.id, te.id
    db.close()

    print("== 1. CSP endurecida ==")
    r = c.get("/login")
    csp = r.headers.get("content-security-policy", "")
    check("script-src sin unsafe-inline", "script-src 'self'" in csp and "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0])
    check("style-src sin unsafe-inline", "'unsafe-inline'" not in csp)
    check("platform.js se sirve", c.get("/static/platform.js").status_code == 200)

    print("\n== 2. Sin codigo en linea en el HTML servido ==")
    ca = TestClient(app); login(ca, "oa@example.com")
    for url in ["/owner", "/owner/tickets", "/owner/inquilinos", "/sesiones"]:
        body = ca.get(url).text
        bad = "onsubmit=" in body or "onclick=" in body or 'style="' in body
        check(f"{url} sin inline", not bad, "(tiene inline)")

    print("\n== 3. Confirmacion destructiva via data-confirm ==")
    body = ca.get("/owner/inquilinos").text
    check("formulario de terminar lleva data-confirm", 'data-confirm=' in body)
    body = ca.get("/sesiones").text
    check("cerrar sesiones lleva data-confirm", 'data-confirm=' in body)

    print("\n== 4. Menu lateral ==")
    body = ca.get("/owner").text
    check("hay barra lateral", 'class="sidebar"' in body)
    check("agrupado por secciones", body.count('nav-group-title') >= 3,
          f"({body.count('nav-group-title')} grupos)")
    check("opcion activa marcada", 'is-active' in body)
    check("ya no hay fila de botones de navegacion", 'class="actions">' not in body.split('<main')[1][:600])
    ct = TestClient(app); login(ct, "ia@example.com")
    tbody = ct.get("/inquilino").text
    check("inquilino ve SU menu", 'href="/inquilino/mensajes"' in tbody)
    check("inquilino NO ve opciones de owner", 'href="/owner/inquilinos"' not in tbody)
    cadm = TestClient(app); login(cadm, "adm@example.com")
    abody = cadm.get("/admin").text
    check("admin ve submenu de pagos", '/admin/pagos/metodos' in abody)
    check("owner NO ve submenu de pagos", '/admin/pagos/metodos' not in body)

    print("\n== 5. Asignacion de tickets ==")
    body = ca.get(f"/owner/tickets/{TKID}").text
    check("hay selector de responsable", 'name="accion" value="asignar"' in body)
    t = tok(ca, f"/owner/tickets/{TKID}")
    r = ca.post(f"/owner/tickets/{TKID}/actualizar",
                data={"accion": "asignar", "body": str(TEID), "csrf_token": t},
                follow_redirects=False)
    check("asignar -> 302", r.status_code == 302, f"({r.status_code})")
    db = SessionLocal()
    check("responsable guardado",
          db.query(MaintenanceTicket).filter(MaintenanceTicket.id == TKID).first().assigned_to_user_id == TEID)
    db.close()
    # asignar a alguien fuera de su alcance
    t = tok(ca, f"/owner/tickets/{TKID}")
    r = ca.post(f"/owner/tickets/{TKID}/actualizar",
                data={"accion": "asignar", "body": "99999", "csrf_token": t},
                follow_redirects=False)
    check("asignar a persona ajena -> 404", r.status_code == 404, f"({r.status_code})")

    print("\n== 6. Submenu de pagos (2c) ==")
    r = cadm.get("/admin/pagos/metodos")
    check("metodos de pago carga", r.status_code == 200, f"({r.status_code})")
    r = cadm.get("/admin/pagos/requisitos")
    check("requisitos carga", r.status_code == 200, f"({r.status_code})")
    check("dice que el cobro esta apagado", "desactivado" in r.text)
    t = tok(cadm, "/admin/pagos/metodos")
    r = cadm.post("/admin/pagos/metodos",
                  data={"pago_titular": "Aura SA", "pago_clabe": "012180001234567890",
                        "csrf_token": t}, follow_redirects=False)
    check("guardar -> 302", r.status_code == 302, f"({r.status_code})")
    db = SessionLocal()
    v = db.query(PlatformSetting).filter(PlatformSetting.key == "pago_clabe").first()
    check("guardado en la base interna", v and v.value == "012180001234567890")
    db.close()
    # el owner no entra
    check("owner NO accede a pagos",
          ca.get("/admin/pagos/metodos", follow_redirects=False).status_code == 302)
    # la CLABE no acaba en el sitio publico
    import pathlib
    site = pathlib.Path(r"C:\Aura\claude-code\data\site.json").read_text(encoding="utf-8")
    check("CLABE NO esta en data/site.json (sitio publico)", "012180001234567890" not in site)
    check("API de cobro sigue en 501", c.get("/api/payments/x").status_code == 501)

    print("\n== 7. Rutas de acceso del sitio publico ==")
    for url in ["/acceso/propietarios", "/acceso/inquilinos"]:
        r = c.get(url)
        check(f"{url} -> 200", r.status_code == 200, f"({r.status_code})")
    check("titulo propio de propietarios", "propietarios" in c.get("/acceso/propietarios").text.lower())
    check("titulo propio de inquilinos", "inquilinos" in c.get("/acceso/inquilinos").text.lower())


    print("== 8. Enrutamiento por rol: sin bucles de redireccion ==")

    # Regresion de ERR_TOO_MANY_REDIRECTS: un inquilino recien creado entraba en
    # bucle /owner -> /login -> /owner, porque _home_for() mandaba a todo el que
    # no fuera admin al panel del propietario, y ese panel rebotaba al formulario
    # de acceso a quien no fuera owner.
    def sigue(cl, url, limite=8):
        vistos, cur = [], url
        for _ in range(limite):
            r = cl.get(cur, follow_redirects=False)
            if r.status_code not in (301, 302, 303, 307, 308):
                return cur, r.status_code, False
            loc = r.headers.get("location", "")
            if loc in vistos:
                return loc, r.status_code, True
            vistos.append(loc); cur = loc
        return cur, 0, True

    for correo, destino in [("ia@example.com", "/inquilino"),
                            ("oa@example.com", "/owner"),
                            ("adm@example.com", "/admin")]:
        cl = TestClient(app)
        t = tok(cl, "/login")
        r = login_completo(cl, correo)
        check(f"{correo} aterriza en {destino}", r.headers.get("location") == destino,
              f"(fue {r.headers.get('location')})")
        final, code, bucle = sigue(cl, r.headers.get("location", "/"))
        check(f"{correo} sin bucle de redirecciones", not bucle and code == 200,
              f"(bucle={bucle}, final={final} {code})")

    ctn = TestClient(app); login(ctn, "ia@example.com")
    r = ctn.get("/owner", follow_redirects=False)
    check("inquilino en /owner -> a SU panel, no a /login",
          r.headers.get("location") == "/inquilino", f"(fue {r.headers.get('location')})")
    r = ca.get("/inquilino", follow_redirects=False)
    check("owner en /inquilino -> a SU panel, no a /login",
          r.headers.get("location") == "/owner", f"(fue {r.headers.get('location')})")

print(f"\n{'='*46}\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)