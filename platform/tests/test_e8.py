"""Pruebas E8 — cierre del acceso por la API JSON.

Base desechable, NUNCA toca platform.db real.

Fija el defecto que se midió el 2026-09-08 (docs/phase2.1/HALLAZGOS_SEGURIDAD.md,
H-1): `POST /api/auth/login` verificaba correo y contraseña y nada más, así que
era un oráculo de adivinación sin freno, sin bloqueo y sin rastro, y la sesión
que emitía abría `/api/admin/*` y `/api/owner/*` saltándose `is_active`, el
segundo factor y la revocación de sesiones.

Estas comprobaciones existen para que ese camino no pueda volver a abrirse sin
que alguien lo note.
"""
import os, sys, re, tempfile, pathlib

TMP = tempfile.mkdtemp(prefix="aura_e8_")
DB = os.path.join(TMP, "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["APP_ENV"] = "dev"
os.environ["DATA_MODE"] = "mock"
os.environ["UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["SEED_ADMIN_EMAIL"] = "admin@test.local"
os.environ["SEED_ADMIN_PASSWORD"] = "TestPass123!"
os.environ.pop("LEGACY_JSON_AUTH_ENABLED", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from app.main import app
from app.auth import hash_password
from app.db import SessionLocal
from app.models import AuditLog, LoginAttempt, Property, RoleEnum, User, UserSession

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  PASS  {name}")
    else: fail += 1; print(f"  FAIL  {name} {extra}")


def csrf(cl, ruta="/login"):
    return re.search(r'name="csrf_token" value="([^"]+)"', cl.get(ruta).text).group(1)


def login_html(cl, email, password):
    """Acceso por el formulario, que es el único camino que queda."""
    t = csrf(cl)
    return cl.post("/login", data={"email": email, "password": password, "csrf_token": t},
                   follow_redirects=False)


print(f"DB de prueba: {DB}\n")

with TestClient(app) as c:
    db = SessionLocal()
    # Un propietario normal, y un administrador desactivado + bloqueado.
    duenio = User(name="Propietario E8", email="owner-e8@test.local",
                  password_hash=hash_password("Pass123456!"), role=RoleEnum.owner)
    malo = User(name="Admin Bloqueado", email="bloqueado-e8@test.local",
                password_hash=hash_password("Pass123456!"), role=RoleEnum.admin,
                is_active=False, failed_login_count=99,
                locked_until=datetime.utcnow() + timedelta(hours=1))
    db.add_all([duenio, malo]); db.commit()
    duenio_id = duenio.id
    db.add(Property(owner_id=duenio_id, title="Casa E8", city="Cancún"))
    db.commit(); db.close()

    print("== 1. Las tres rutas JSON de autenticación están retiradas ==")
    tok = csrf(c)
    for ruta, metodo in (("/api/auth/login", "post"), ("/api/auth/logout", "post"),
                         ("/api/auth/me", "get")):
        if metodo == "post":
            r = c.post(ruta, json={"email": "owner-e8@test.local", "password": "Pass123456!"},
                       headers={"x-csrf-token": tok})
        else:
            r = c.get(ruta)
        # 404 y no 401: un 401 confirmaría que la ruta existe.
        check(f"{ruta} devuelve 404", r.status_code == 404, f"-> {r.status_code}")

    print("\n== 2. Ya no es un oráculo de adivinación de contraseñas ==")
    antes = SessionLocal(); n_antes = antes.query(LoginAttempt).count(); antes.close()
    codigos = []
    for i in range(20):
        r = c.post("/api/auth/login",
                   json={"email": "owner-e8@test.local", "password": f"mala{i}"},
                   headers={"x-csrf-token": tok})
        codigos.append(r.status_code)
    check("20 intentos devuelven siempre 404", set(codigos) == {404}, f"-> {sorted(set(codigos))}")
    check("ninguno devuelve 401 (no distingue clave buena de mala)", 401 not in codigos)

    d = SessionLocal()
    usuario = d.query(User).filter(User.email == "owner-e8@test.local").first()
    check("la cuenta atacada no queda bloqueada por esta vía",
          usuario.locked_until is None and (usuario.failed_login_count or 0) == 0,
          f"-> locked={usuario.locked_until} fallos={usuario.failed_login_count}")
    check("la contraseña correcta tampoco entra por la API",
          c.post("/api/auth/login",
                 json={"email": "owner-e8@test.local", "password": "Pass123456!"},
                 headers={"x-csrf-token": tok}).status_code == 404)
    check("cada llamada queda registrada en la bitácora",
          d.query(AuditLog).filter(AuditLog.action == "api.auth_legacy_blocked").count() >= 20)
    d.close()

    print("\n== 3. La cuenta desactivada y bloqueada no llega a /api/admin ==")
    atacante = TestClient(app)
    t3 = csrf(atacante)
    r = atacante.post("/api/auth/login",
                      json={"email": "bloqueado-e8@test.local", "password": "Pass123456!"},
                      headers={"x-csrf-token": t3})
    check("no puede autenticarse por la API", r.status_code == 404, f"-> {r.status_code}")
    for ruta in ("/api/admin/users", "/api/admin/owners", "/api/admin/properties"):
        rr = atacante.get(ruta)
        check(f"{ruta} niega el acceso", rr.status_code != 200, f"-> {rr.status_code}")

    print("\n== 4. Revocar la sesión ahora SÍ cierra la API ==")
    nav = TestClient(app)
    r = login_html(nav, "owner-e8@test.local", "Pass123456!")
    check("el propietario entra por el formulario", r.status_code == 302, f"-> {r.status_code}")
    r = nav.get("/api/owner/properties")
    check("y su sesión abre la API JSON", r.status_code == 200, f"-> {r.status_code}")

    d = SessionLocal()
    viva = d.query(UserSession).filter(UserSession.user_id == duenio_id,
                                       UserSession.revoked_at.is_(None)).first()
    check("existe fila de sesión en la tabla", viva is not None)
    if viva:
        viva.revoked_at = datetime.utcnow(); viva.revoked_reason = "prueba_e8"; d.commit()
    d.close()

    r = nav.get("/api/owner/properties")
    # Antes de E8 esto seguía devolviendo 200: la API no miraba la tabla `sessions`.
    check("tras revocar, la API JSON deja de responder", r.status_code == 401, f"-> {r.status_code}")

    print("\n== 5. Una cuenta desactivada en caliente pierde la API ==")
    nav2 = TestClient(app)
    login_html(nav2, "owner-e8@test.local", "Pass123456!")
    check("entra de nuevo", nav2.get("/api/owner/properties").status_code == 200)
    d = SessionLocal()
    u = d.query(User).filter(User.id == duenio_id).first(); u.is_active = False; d.commit(); d.close()
    check("al desactivarlo, la API lo expulsa en la siguiente petición",
          nav2.get("/api/owner/properties").status_code == 401)

    print("\n== 6. La bandera de marcha atrás existe y está apagada ==")
    from app.auth import legacy_json_auth_enabled
    check("LEGACY_JSON_AUTH_ENABLED apagada por omisión", legacy_json_auth_enabled() is False)
    os.environ["LEGACY_JSON_AUTH_ENABLED"] = "true"
    check("y se puede encender para un despliegue de emergencia",
          legacy_json_auth_enabled() is True)
    os.environ.pop("LEGACY_JSON_AUTH_ENABLED", None)

    # Va AL FINAL a propósito: agota el freno por IP (10 fallos/minuto), así
    # que cualquier acceso posterior desde este mismo cliente recibiría 429.
    print("\n== 7. El formulario HTML sí frena (contraste con la sección 2) ==")
    web = TestClient(app)
    t2 = csrf(web)
    html = [web.post("/login", data={"email": "owner-e8@test.local", "password": f"mala{i}",
                                     "csrf_token": t2}, follow_redirects=False).status_code
            for i in range(12)]
    check("el formulario acaba devolviendo 429", 429 in html, f"-> {sorted(set(html))}")
    d = SessionLocal()
    check("y sí escribe en login_attempts", d.query(LoginAttempt).count() > n_antes)
    d.close()

print(f"\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
