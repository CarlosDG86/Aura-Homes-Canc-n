"""Google SSO contra un proveedor SIMULADO.

Se generan llaves RSA propias y se firman tokens como lo haria Google, para
poder verificar la logica de seguridad sin credenciales reales: firma, emisor,
destinatario, caducidad, nonce, state, PKCE y la regla de no auto-registro.
Lo unico que no se cubre aqui es la llamada de red real a Google.
"""
import os, sys, re, json, time, base64, tempfile
import pathlib

TMP = tempfile.mkdtemp(prefix="aura_sso_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(TMP,'t.db')}"
os.environ["APP_ENV"] = "dev"; os.environ["DATA_MODE"] = "mock"
os.environ["GOOGLE_CLIENT_ID"] = "cliente-de-prueba.apps.googleusercontent.com"
os.environ["GOOGLE_CLIENT_SECRET"] = "secreto-de-prueba"
os.environ["GOOGLE_REDIRECT_URI"] = "http://testserver/auth/google/callback"
os.environ["GOOGLE_ISSUER"] = "https://proveedor-simulado.local"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.auth import hash_password
from app.models import User, RoleEnum
from app import google_sso

ok = fail = 0
def check(n, c, e=""):
    global ok, fail
    if c: ok += 1; print(f"  PASS  {n}")
    else: fail += 1; print(f"  FAIL  {n} {e}")

# --- proveedor simulado ------------------------------------------------------
LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUB = LLAVE.public_key()

def firmar(claims, key=None, alg="RS256"):
    base = {
        "iss": os.environ["GOOGLE_ISSUER"],
        "aud": os.environ["GOOGLE_CLIENT_ID"],
        "sub": "google-sub-12345",
        "email": "ow@example.com",
        "email_verified": True,
        "name": "Owner A",
        "iat": int(time.time()), "exp": int(time.time()) + 600,
    }
    base.update(claims)
    return jwt.encode(base, key or LLAVE, algorithm=alg)

class LlaveFalsa:
    def __init__(self, k): self.key = k
class ClienteJWKFalso:
    def __init__(self, *a, **k): pass
    def get_signing_key_from_jwt(self, token): return LlaveFalsa(PUB)

jwt.PyJWKClient = ClienteJWKFalso   # sustituye la descarga de llaves de Google

TOKEN_ACTUAL = {"id_token": None, "status": 200}
class RespuestaFalsa:
    def __init__(self, d, s): self._d, self.status_code = d, s
    def json(self): return self._d
def post_falso(url, data=None, timeout=None):
    return RespuestaFalsa({"id_token": TOKEN_ACTUAL["id_token"]}, TOKEN_ACTUAL["status"])
google_sso.httpx.post = post_falso

with TestClient(app) as c:
    db = SessionLocal()
    ow = User(name="Owner A", email="ow@example.com",
              password_hash=hash_password("Pass123456!"), role=RoleEnum.owner)
    db.add(ow); db.commit(); db.refresh(ow); OWID = ow.id; db.close()

    def iniciar(cl):
        """Arranca el flujo y devuelve el state que quedo en la sesion."""
        r = cl.get("/auth/google/start", follow_redirects=False)
        loc = r.headers.get("location", "")
        m = re.search(r"[?&]state=([^&]+)", loc)
        return loc, (m.group(1) if m else None)

    print("== 1. Inicio del flujo ==")
    ca = TestClient(app)
    loc, state = iniciar(ca)
    check("redirige a Google", loc.startswith(os.environ.get("GOOGLE_AUTH_ENDPOINT",
          "https://accounts.google.com/o/oauth2/v2/auth")), f"({loc[:60]})")
    check("lleva state", bool(state))
    check("lleva nonce", "nonce=" in loc)
    check("usa PKCE S256", "code_challenge=" in loc and "code_challenge_method=S256" in loc)
    check("pide solo permisos minimos", "openid+email+profile" in loc or "openid%20email%20profile" in loc)
    check("NO expone el secreto del cliente", "secreto-de-prueba" not in loc)

    print("\n== 2. Acceso valido ==")
    # el nonce lo generó el servidor: se lee de la URL para firmarlo igual
    nonce = re.search(r"[?&]nonce=([^&]+)", loc).group(1)
    TOKEN_ACTUAL["id_token"] = firmar({"nonce": nonce})
    r = ca.get(f"/auth/google/callback?code=abc&state={state}", follow_redirects=False)
    check("entra -> 302", r.status_code == 302, f"({r.status_code})")
    check("va a su panel", r.headers.get("location") == "/owner", f"({r.headers.get('location')})")
    db = SessionLocal()
    u = db.query(User).filter(User.id == OWID).first()
    check("vinculo guardado por sub", u.google_sub == "google-sub-12345", f"({u.google_sub})")
    check("sesion registrada", u.last_login_at is not None)
    db.close()

    print("\n== 3. state incorrecto (ataque desde otro sitio) ==")
    cb = TestClient(app); loc2, _ = iniciar(cb)
    n2 = re.search(r"[?&]nonce=([^&]+)", loc2).group(1)
    TOKEN_ACTUAL["id_token"] = firmar({"nonce": n2})
    r = cb.get("/auth/google/callback?code=abc&state=state-inventado", follow_redirects=False)
    check("state falso rechazado", r.status_code == 401, f"({r.status_code})")

    print("\n== 4. state reutilizado (un solo uso) ==")
    cc = TestClient(app); loc3, s3 = iniciar(cc)
    n3 = re.search(r"[?&]nonce=([^&]+)", loc3).group(1)
    TOKEN_ACTUAL["id_token"] = firmar({"nonce": n3})
    cc.get(f"/auth/google/callback?code=abc&state={s3}", follow_redirects=False)
    r = cc.get(f"/auth/google/callback?code=abc&state={s3}", follow_redirects=False)
    check("no se puede repetir el mismo state", r.status_code == 401, f"({r.status_code})")

    print("\n== 5. Token firmado por OTRA llave (falsificado) ==")
    otra = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cd = TestClient(app); loc4, s4 = iniciar(cd)
    n4 = re.search(r"[?&]nonce=([^&]+)", loc4).group(1)
    TOKEN_ACTUAL["id_token"] = firmar({"nonce": n4}, key=otra)
    r = cd.get(f"/auth/google/callback?code=abc&state={s4}", follow_redirects=False)
    check("firma invalida rechazada", r.status_code == 401, f"({r.status_code})")

    print("\n== 6. Token para OTRA aplicacion ==")
    ce = TestClient(app); loc5, s5 = iniciar(ce)
    n5 = re.search(r"[?&]nonce=([^&]+)", loc5).group(1)
    TOKEN_ACTUAL["id_token"] = firmar({"nonce": n5, "aud": "otra-app.googleusercontent.com"})
    r = ce.get(f"/auth/google/callback?code=abc&state={s5}", follow_redirects=False)
    check("destinatario incorrecto rechazado", r.status_code == 401, f"({r.status_code})")

    print("\n== 7. Token caducado ==")
    cf = TestClient(app); loc6, s6 = iniciar(cf)
    n6 = re.search(r"[?&]nonce=([^&]+)", loc6).group(1)
    TOKEN_ACTUAL["id_token"] = firmar({"nonce": n6, "exp": int(time.time()) - 60})
    r = cf.get(f"/auth/google/callback?code=abc&state={s6}", follow_redirects=False)
    check("token caducado rechazado", r.status_code == 401, f"({r.status_code})")

    print("\n== 8. nonce de otra solicitud (token capturado) ==")
    cg = TestClient(app); loc7, s7 = iniciar(cg)
    TOKEN_ACTUAL["id_token"] = firmar({"nonce": "nonce-de-otra-sesion"})
    r = cg.get(f"/auth/google/callback?code=abc&state={s7}", follow_redirects=False)
    check("nonce ajeno rechazado", r.status_code == 401, f"({r.status_code})")

    print("\n== 9. Correo de Google SIN verificar ==")
    ch = TestClient(app); loc8, s8 = iniciar(ch)
    n8 = re.search(r"[?&]nonce=([^&]+)", loc8).group(1)
    TOKEN_ACTUAL["id_token"] = firmar({"nonce": n8, "email_verified": False})
    r = ch.get(f"/auth/google/callback?code=abc&state={s8}", follow_redirects=False)
    check("correo no verificado rechazado", r.status_code == 401, f"({r.status_code})")

    print("\n== 10. SIN AUTO-REGISTRO (la regla mas importante) ==")
    ci = TestClient(app); loc9, s9 = iniciar(ci)
    n9 = re.search(r"[?&]nonce=([^&]+)", loc9).group(1)
    TOKEN_ACTUAL["id_token"] = firmar({"nonce": n9, "sub": "sub-desconocido-999",
                                       "email": "cualquiera@gmail.com"})
    r = ci.get(f"/auth/google/callback?code=abc&state={s9}", follow_redirects=False)
    check("cuenta desconocida rechazada", r.status_code == 401, f"({r.status_code})")
    check("explica que hay que darla de alta", "no está registrada" in r.text or "registrada" in r.text)
    db = SessionLocal()
    check("NO se creo ningun usuario",
          db.query(User).filter(User.email == "cualquiera@gmail.com").count() == 0)
    db.close()

    print("\n== 11. Cuenta desactivada ==")
    db = SessionLocal()
    db.query(User).filter(User.id == OWID).first().is_active = False; db.commit(); db.close()
    cj = TestClient(app); loc10, s10 = iniciar(cj)
    n10 = re.search(r"[?&]nonce=([^&]+)", loc10).group(1)
    TOKEN_ACTUAL["id_token"] = firmar({"nonce": n10})
    r = cj.get(f"/auth/google/callback?code=abc&state={s10}", follow_redirects=False)
    check("cuenta desactivada rechazada", r.status_code == 401, f"({r.status_code})")
    db = SessionLocal()
    db.query(User).filter(User.id == OWID).first().is_active = True; db.commit(); db.close()

    print("\n== 12. Sub ya vinculado a otra cuenta (anti-secuestro) ==")
    db = SessionLocal()
    otro = User(name="Otro", email="otro@example.com", password_hash=hash_password("x"*12),
                role=RoleEnum.owner, google_sub="sub-de-otro")
    db.add(otro); db.commit(); db.close()
    ck = TestClient(app); loc11, s11 = iniciar(ck)
    n11 = re.search(r"[?&]nonce=([^&]+)", loc11).group(1)
    # mismo correo que 'otro', pero un sub distinto
    TOKEN_ACTUAL["id_token"] = firmar({"nonce": n11, "sub": "sub-atacante",
                                       "email": "otro@example.com"})
    r = ck.get(f"/auth/google/callback?code=abc&state={s11}", follow_redirects=False)
    check("no reasigna una cuenta ya vinculada", r.status_code == 401, f"({r.status_code})")
    db = SessionLocal()
    check("el vinculo original se conserva",
          db.query(User).filter(User.email == "otro@example.com").first().google_sub == "sub-de-otro")
    db.close()

    print("\n== 13. Sin credenciales: no rompe, solo se desactiva ==")
    google_sso.CLIENT_ID = ""
    check("is_configured() False", not google_sso.is_configured())
    cl2 = TestClient(app)
    r = cl2.get("/auth/google/start", follow_redirects=False)
    check("redirige al login normal", r.status_code == 302 and r.headers.get("location") == "/login",
          f"({r.status_code} {r.headers.get('location')})")
    google_sso.CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]

print(f"\n{'='*46}\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
