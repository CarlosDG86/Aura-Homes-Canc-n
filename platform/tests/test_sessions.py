"""Tabla sessions: revocacion del lado del servidor. Base desechable."""
import os, sys, re, tempfile
import pathlib
from datetime import datetime, timedelta, timezone

TMP = tempfile.mkdtemp(prefix="aura_ses_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(TMP,'t.db')}"
os.environ["APP_ENV"] = "dev"; os.environ["DATA_MODE"] = "mock"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pyotp
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.auth import hash_password
from app.identity import new_secret
from app.models import User, RoleEnum, UserSession

ok = fail = 0
def check(n, c, e=""):
    global ok, fail
    if c: ok += 1; print(f"  PASS  {n}")
    else: fail += 1; print(f"  FAIL  {n} {e}")

def tok(cl, url):
    r = cl.get(url)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    return m.group(1) if m else None

def login(cl, email="oa@example.com", password="Pass123456!"):
    t = tok(cl, "/login")
    return cl.post("/login", data={"email": email, "password": password, "csrf_token": t},
                   follow_redirects=False)

with TestClient(app) as c:
    db = SessionLocal()
    u = User(name="Owner A", email="oa@example.com",
             password_hash=hash_password("Pass123456!"), role=RoleEnum.owner)
    db.add(u); db.commit(); db.refresh(u); UID = u.id; db.close()

    print("== 1. Iniciar sesion crea fila ==")
    c1 = TestClient(app); login(c1)
    db = SessionLocal()
    rows = db.query(UserSession).filter(UserSession.user_id == UID).all()
    check("fila creada", len(rows) == 1, f"({len(rows)})")
    check("sin revocar", rows[0].revoked_at is None)
    check("sid largo y aleatorio", len(rows[0].sid) >= 32, f"(len={len(rows[0].sid)})")
    check("guarda user agent", rows[0].user_agent is not None)
    SID1 = rows[0].sid
    db.close()
    check("panel accesible", c1.get("/owner").status_code == 200)

    print("\n== 2. Revocar desde el servidor expulsa de inmediato ==")
    db = SessionLocal()
    from app.security import revoke_session
    revoke_session(db, SID1, "prueba")
    db.close()
    r = c1.get("/owner", follow_redirects=False)
    check("misma cookie -> ya NO entra", r.status_code == 302, f"({r.status_code})")
    check("redirige a login", r.headers.get("location") == "/login")

    print("\n== 3. Cerrar sesion revoca la fila ==")
    c2 = TestClient(app); login(c2)
    db = SessionLocal()
    sid2 = db.query(UserSession).filter(UserSession.user_id == UID,
                                        UserSession.revoked_at.is_(None)).first().sid
    db.close()
    c2.get("/logout")
    db = SessionLocal()
    s = db.query(UserSession).filter(UserSession.sid == sid2).first()
    check("marcada revocada", s.revoked_at is not None)
    check("motivo registrado", s.revoked_reason == "logout", f"({s.revoked_reason})")
    db.close()

    print("\n== 4. Varias sesiones a la vez ==")
    ca = TestClient(app); login(ca)
    cb = TestClient(app); login(cb)
    cc = TestClient(app); login(cc)
    db = SessionLocal()
    live = db.query(UserSession).filter(UserSession.user_id == UID,
                                        UserSession.revoked_at.is_(None)).count()
    check("3 sesiones vivas", live == 3, f"({live})")
    db.close()
    check("las tres funcionan",
          all(x.get("/owner").status_code == 200 for x in (ca, cb, cc)))

    print("\n== 5. Cerrar las demas, conservando la actual ==")
    t = tok(ca, "/sesiones")
    r = ca.post("/sesiones/cerrar-otras", data={"csrf_token": t}, follow_redirects=False)
    check("accion -> 302", r.status_code == 302, f"({r.status_code})")
    check("la mia sigue viva", ca.get("/owner").status_code == 200)
    check("las otras dos, fuera",
          cb.get("/owner", follow_redirects=False).status_code == 302
          and cc.get("/owner", follow_redirects=False).status_code == 302)
    db = SessionLocal()
    live = db.query(UserSession).filter(UserSession.user_id == UID,
                                        UserSession.revoked_at.is_(None)).count()
    check("solo queda 1 viva", live == 1, f"({live})")
    db.close()

    print("\n== 6. Cambio de contrasena cierra todo ==")
    db = SessionLocal()
    # Desde E2 el segundo factor es obligatorio para administrador: sin el, la
    # sesion queda a medias y /admin/... redirige a /login. Esta suite es
    # anterior a E2 y solo hacia el paso de contrasena, asi que las cuatro
    # comprobaciones de abajo fallaban por una sesion incompleta, no porque el
    # producto hubiera dejado de revocar.
    SEC_ADM = new_secret()
    adm = User(name="Admin2", email="adm2@example.com",
               password_hash=hash_password("Pass123456!"), role=RoleEnum.admin,
               totp_secret=SEC_ADM, totp_enabled=True)
    db.add(adm); db.commit(); db.refresh(adm); db.close()
    cadm = TestClient(app); login(cadm, "adm2@example.com")
    cadm.post("/2fa", data={"code": pyotp.TOTP(SEC_ADM).now(), "csrf_token": tok(cadm, "/2fa")},
              follow_redirects=False)
    check("admin con 2FA completo", cadm.get("/admin").status_code == 200)
    cown = TestClient(app); login(cown)  # owner con sesion abierta
    check("owner dentro antes del cambio", cown.get("/owner").status_code == 200)
    t = tok(cadm, f"/admin/users/{UID}")
    r = cadm.post(f"/admin/users/{UID}/password",
                  data={"new_password": "NuevaClave123", "csrf_token": t}, follow_redirects=False)
    # Ojo: la ruta tambien devuelve 302 cuando rechaza la peticion (sin permiso,
    # contrasena corta). El 302 por si solo NO prueba que restablecio; lo que lo
    # prueba son las tres comprobaciones siguientes.
    check("admin restablece -> 302", r.status_code == 302, f"({r.status_code})")
    check("owner EXPULSADO tras el cambio",
          cown.get("/owner", follow_redirects=False).status_code == 302)
    db = SessionLocal()
    live = db.query(UserSession).filter(UserSession.user_id == UID,
                                        UserSession.revoked_at.is_(None)).count()
    check("ninguna sesion viva del owner", live == 0, f"({live})")
    reason = db.query(UserSession).filter(UserSession.user_id == UID).order_by(
        UserSession.created_at.desc()).first().revoked_reason
    check("motivo password_reset", reason == "password_reset", f"({reason})")
    db.close()

    print("\n== 7. Caducidad por inactividad ==")
    # La contrasena del owner cambio en el paso 6.
    cidle = TestClient(app); login(cidle, password="NuevaClave123")
    db = SessionLocal()
    s = db.query(UserSession).filter(UserSession.user_id == UID,
                                     UserSession.revoked_at.is_(None)).first()
    # Simular 40 min sin actividad (limite owner = 30)
    s.last_seen_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=40)
    db.commit(); SID_IDLE = s.sid; db.close()
    r = cidle.get("/owner", follow_redirects=False)
    check("sesion inactiva expulsada", r.status_code == 302, f"({r.status_code})")
    db = SessionLocal()
    s = db.query(UserSession).filter(UserSession.sid == SID_IDLE).first()
    check("revocada por idle_timeout", s.revoked_at is not None and s.revoked_reason == "idle_timeout",
          f"({s.revoked_reason})")
    db.close()

    print("\n== 8. Cookie sin sid no autentica ==")
    cfake = TestClient(app)
    cfake.get("/login")   # obtiene cookie de sesion, pero sin iniciar sesion
    r = cfake.get("/owner", follow_redirects=False)
    check("cookie sin sesion -> login", r.status_code == 302, f"({r.status_code})")

print(f"\n{'='*46}\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
