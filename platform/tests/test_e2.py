"""E2: segundo factor obligatorio para admin + puerta oculta. Base desechable."""
import os, sys, re, tempfile
import pathlib

TMP = tempfile.mkdtemp(prefix="aura_e2_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(TMP,'t.db')}"
os.environ["APP_ENV"] = "dev"; os.environ["DATA_MODE"] = "mock"
os.environ["ADMIN_LOGIN_PATH"] = "/gestion-interna-a7f3c1"
os.environ["SEED_ADMIN_EMAIL"] = "adm@example.com"
os.environ["SEED_ADMIN_PASSWORD"] = "ClaveDePruebaLarga2026"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
import pyotp
from app.main import app
from app.db import SessionLocal
from app.auth import hash_password
from app.models import User, RoleEnum
from app import identity

ok = fail = 0
def check(n, c, e=""):
    global ok, fail
    if c: ok += 1; print(f"  PASS  {n}")
    else: fail += 1; print(f"  FAIL  {n} {e}")

def tok(cl, url):
    r = cl.get(url)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    return m.group(1) if m else None

GATE = "/gestion-interna-a7f3c1"

with TestClient(app) as c:
    db = SessionLocal()
    ow = User(name="Owner", email="ow@example.com",
              password_hash=hash_password("Pass123456!"), role=RoleEnum.owner)
    db.add(ow); db.commit(); db.close()

    print("== 1. Puerta oculta de administrador ==")
    ca = TestClient(app)
    r = ca.get(GATE)
    check("la URL secreta responde", r.status_code == 200, f"({r.status_code})")
    check("marcada noindex", "noindex" in r.headers.get("x-robots-tag", ""),
          f"({r.headers.get('x-robots-tag')})")
    check("dice 'Acceso interno'", "Acceso interno" in r.text)

    print("\n== 2. El admin NO entra por la puerta publica ==")
    cpub = TestClient(app)
    t = tok(cpub, "/login")
    r = cpub.post("/login", data={"email": "adm@example.com",
                  "password": "ClaveDePruebaLarga2026", "csrf_token": t},
                  follow_redirects=False)
    check("rechazado en /login", r.status_code == 401, f"({r.status_code})")
    check("mensaje generico (no revela que es admin)",
          "incorrectos" in r.text and "admin" not in r.text.lower().split("<title>")[0])

    print("\n== 3. Contrasena correcta NO basta: pide segundo factor ==")
    t = tok(ca, GATE)
    r = ca.post("/login", data={"email": "adm@example.com",
                "password": "ClaveDePruebaLarga2026", "csrf_token": t},
                follow_redirects=False)
    check("redirige a /2fa", r.status_code == 302 and r.headers.get("location") == "/2fa",
          f"({r.status_code} -> {r.headers.get('location')})")
    # con la contrasena correcta pero SIN codigo, no se entra a ningun lado
    r = ca.get("/admin", follow_redirects=False)
    check("aun NO puede abrir /admin", r.status_code == 302, f"({r.status_code})")
    db = SessionLocal()
    u = db.query(User).filter(User.email == "adm@example.com").first()
    check("aun no hay sesion server-side", u.last_login_at is None)
    db.close()

    print("\n== 4. Alta del segundo factor ==")
    r = ca.get("/2fa")
    check("muestra la pantalla de configuracion", r.status_code == 200 and "QR" in r.text or "qr" in r.text.lower())
    m = re.search(r'<code>([A-Z2-7]{16,})</code>', r.text)
    check("entrega la clave para la app", bool(m))
    SECRET = m.group(1) if m else None
    check("incluye el QR embebido", "data:image/png;base64," in r.text)

    print("\n== 5. Codigo incorrecto -> rechazado ==")
    t = tok(ca, "/2fa")
    r = ca.post("/2fa", data={"code": "000000", "csrf_token": t}, follow_redirects=False)
    check("codigo falso rechazado", r.status_code == 401, f"({r.status_code})")
    r = ca.get("/admin", follow_redirects=False)
    check("sigue sin entrar", r.status_code == 302)

    print("\n== 6. Codigo correcto -> entra ==")
    t = tok(ca, "/2fa")
    codigo = pyotp.TOTP(SECRET).now()
    r = ca.post("/2fa", data={"code": codigo, "csrf_token": t}, follow_redirects=False)
    check("acepta el codigo -> 302", r.status_code == 302, f"({r.status_code})")
    check("destino /admin", r.headers.get("location") == "/admin", f"({r.headers.get('location')})")
    r = ca.get("/admin")
    check("panel accesible", r.status_code == 200, f"({r.status_code})")
    db = SessionLocal()
    u = db.query(User).filter(User.email == "adm@example.com").first()
    check("segundo factor queda activado", u.totp_enabled is True)
    check("secreto guardado", bool(u.totp_secret))
    check("sesion registrada", u.last_login_at is not None)
    db.close()

    print("\n== 7. Segundo inicio: ya pide solo el codigo ==")
    cb = TestClient(app)
    cb.get(GATE)
    t = tok(cb, GATE)
    r = cb.post("/login", data={"email": "adm@example.com",
                "password": "ClaveDePruebaLarga2026", "csrf_token": t},
                follow_redirects=False)
    check("vuelve a pedir 2FA", r.headers.get("location") == "/2fa")
    r = cb.get("/2fa")
    check("ya no muestra el QR (solo pide codigo)", "data:image/png" not in r.text)
    t = tok(cb, "/2fa")
    r = cb.post("/2fa", data={"code": pyotp.TOTP(SECRET).now(), "csrf_token": t},
                follow_redirects=False)
    check("entra con el codigo", r.status_code == 302 and r.headers.get("location") == "/admin")

    print("\n== 8. Los owners NO necesitan segundo factor ==")
    co = TestClient(app)
    t = tok(co, "/login")
    r = co.post("/login", data={"email": "ow@example.com", "password": "Pass123456!",
                "csrf_token": t}, follow_redirects=False)
    check("owner entra directo a /owner",
          r.status_code == 302 and r.headers.get("location") == "/owner",
          f"({r.headers.get('location')})")
    check("owner ve su panel", co.get("/owner").status_code == 200)

    print("\n== 9. Robo de contrasena: no alcanza ==")
    # Un atacante con la contrasena correcta, entrando por la puerta correcta,
    # pero sin el telefono.
    catk = TestClient(app)
    catk.get(GATE)
    t = tok(catk, GATE)
    catk.post("/login", data={"email": "adm@example.com",
              "password": "ClaveDePruebaLarga2026", "csrf_token": t},
              follow_redirects=False)
    for intento in ["123456", "000000", "999999"]:
        t = tok(catk, "/2fa")
        catk.post("/2fa", data={"code": intento, "csrf_token": t}, follow_redirects=False)
    r = catk.get("/admin", follow_redirects=False)
    check("con contrasena pero sin codigo: NO entra", r.status_code == 302, f"({r.status_code})")

print(f"\n{'='*46}\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
