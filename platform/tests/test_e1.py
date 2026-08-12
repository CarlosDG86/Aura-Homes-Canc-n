"""Pruebas E1 contra una base desechable. NUNCA toca platform.db real."""
import os, sys, re, tempfile, pathlib
import pathlib

TMP = tempfile.mkdtemp(prefix="aura_e1_")
DB = os.path.join(TMP, "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["APP_ENV"] = "dev"
os.environ["SEED_ADMIN_EMAIL"] = "admin@test.local"
os.environ["SEED_ADMIN_PASSWORD"] = "TestPass123!"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User, LoginAttempt, AuditLog

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  PASS  {name}")
    else: fail += 1; print(f"  FAIL  {name} {extra}")


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

print(f"DB de prueba: {DB}\n")
with TestClient(app) as c:
    print("== 1. Cabeceras de seguridad ==")
    r = c.get("/login")
    for h in ["content-security-policy", "x-content-type-options", "x-frame-options",
              "referrer-policy", "permissions-policy"]:
        check(f"cabecera {h}", h in r.headers)
    check("CSP sin unsafe-inline en script-src",
          "script-src 'self'" in r.headers.get("content-security-policy", ""))

    print("\n== 2. CSRF ==")
    check("login.html incluye token", 'name="csrf_token"' in r.text)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    token = m.group(1) if m else None
    check("token presente en HTML", bool(token))

    # POST sin token -> 403
    c2 = TestClient(app)
    c2.get("/login")
    r = c2.post("/login", data={"email": "admin@test.local", "password": "TestPass123!"},
                follow_redirects=False)
    check("POST sin token -> 403", r.status_code == 403, f"(fue {r.status_code})")

    # POST con token invalido -> 403
    r = c2.post("/login", data={"email": "admin@test.local", "password": "TestPass123!",
                                "csrf_token": "basura"}, follow_redirects=False)
    check("POST con token falso -> 403", r.status_code == 403, f"(fue {r.status_code})")

    print("\n== 3. Login valido (el cuerpo sobrevive al middleware) ==")
    # El admin exige segundo factor (E2): login_completo cubre los dos pasos.
    r = c.post("/login", data={"email": "admin@test.local", "password": "TestPass123!",
                               "csrf_token": token}, follow_redirects=False)
    check("login correcto -> 302", r.status_code == 302, f"(fue {r.status_code})")
    check("admin pasa por el segundo factor", r.headers.get("location") == "/2fa",
          f"(fue {r.headers.get('location')})")
    r = completar_2fa(c, "admin@test.local")
    check("tras el codigo, entra a /admin", r.headers.get("location") == "/admin",
          f"(fue {r.headers.get('location')})")
    r = c.get("/admin")
    check("dashboard admin accesible", r.status_code == 200, f"(fue {r.status_code})")
    check("formularios del dashboard llevan token", 'name="csrf_token"' in r.text)

    print("\n== 4. Registro y auditoria ==")
    db = SessionLocal()
    check("intento exitoso registrado",
          db.query(LoginAttempt).filter(LoginAttempt.success.is_(True)).count() >= 1)
    check("auditoria login.success", db.query(AuditLog).filter(AuditLog.action == "login.success").count() >= 1)
    u = db.query(User).filter(User.email == "admin@test.local").first()
    check("last_login_at grabado", u.last_login_at is not None)
    check("columnas de seguridad presentes", u.is_active is True and u.failed_login_count == 0)
    db.close()

    print("\n== 5. Bloqueo por intentos fallidos ==")
    c3 = TestClient(app)
    codes = []
    for i in range(6):
        rr = c3.get("/login")
        tk = re.search(r'name="csrf_token" value="([^"]+)"', rr.text).group(1)
        rr = c3.post("/login", data={"email": "admin@test.local", "password": "malaclave",
                                     "csrf_token": tk}, follow_redirects=False)
        codes.append(rr.status_code)
    check("los fallos no autentican", all(x in (401, 429) for x in codes), f"(codigos {codes})")
    db = SessionLocal()
    u = db.query(User).filter(User.email == "admin@test.local").first()
    check("cuenta bloqueada tras 5 fallos", u.locked_until is not None,
          f"(locked_until={u.locked_until}, fails={u.failed_login_count})")
    # con la cuenta bloqueada, la clave BUENA tampoco entra
    rr = c3.get("/login")
    tk = re.search(r'name="csrf_token" value="([^"]+)"', rr.text).group(1)
    rr = c3.post("/login", data={"email": "admin@test.local", "password": "TestPass123!",
                                 "csrf_token": tk}, follow_redirects=False)
    check("bloqueada: clave correcta NO entra", rr.status_code in (401, 429),
          f"(fue {rr.status_code})")
    check("mensaje generico (sin enumeracion)", "incorrectos" in rr.text or rr.status_code == 429)
    db.close()

    print("\n== 6. Guardia de SECRET_KEY ==")
    from app.security import require_secure_secret_key, INSECURE_DEFAULT_SECRET
    os.environ["APP_ENV"] = "production"
    try:
        require_secure_secret_key(INSECURE_DEFAULT_SECRET); check("rechaza llave por defecto", False)
    except RuntimeError:
        check("rechaza llave por defecto en produccion", True)
    try:
        require_secure_secret_key("corta"); check("rechaza llave corta", False)
    except RuntimeError:
        check("rechaza llave corta", True)
    try:
        require_secure_secret_key("x" * 64); check("acepta llave larga y aleatoria", True)
    except RuntimeError:
        check("acepta llave larga y aleatoria", False)
    os.environ["APP_ENV"] = "dev"

    print("\n== 7. /api/health exento (sondeo sin sesion) ==")
    check("GET /api/health -> 200", c.get("/api/health").status_code == 200)

print(f"\n{'='*46}\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
