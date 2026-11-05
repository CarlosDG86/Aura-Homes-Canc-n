"""Pruebas E10 — recuperación de contraseña y «ver contraseña».

Base desechable, NUNCA toca platform.db real.

El grueso de estas comprobaciones no mira si la función «hace lo que dice»,
sino si **no dice de más**: un flujo de recuperación mal hecho es una forma
cómoda de averiguar qué direcciones tienen cuenta. Por eso se comparan
respuestas carácter a carácter, se cronometra el límite y se verifica que el
token no aparezca en ninguna cabecera.
"""
import os, sys, re, tempfile, pathlib, hashlib

TMP = tempfile.mkdtemp(prefix="aura_acceso_")
DB = os.path.join(TMP, "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["APP_ENV"] = "dev"
os.environ["DATA_MODE"] = "mock"
os.environ["UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["SEED_ADMIN_EMAIL"] = "admin@test.local"
os.environ["SEED_ADMIN_PASSWORD"] = "TestPass123!"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from app.auth import hash_password, verify_password
from app.db import SessionLocal
from app.main import app
from app.models import (AuditLog, LoginAttempt, OutboxEmail, PasswordResetToken,
                        RoleEnum, User, UserSession)
from app.security import MIN_PASSWORD_LEN, validar_fuerza_contrasena

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  PASS  {name}")
    else: fail += 1; print(f"  FAIL  {name} {extra}")


def csrf(cl, ruta="/login"):
    return re.search(r'name="csrf_token" value="([^"]+)"', cl.get(ruta).text).group(1)


def pedir_reset(cl, correo):
    t = csrf(cl, "/recuperar")
    return cl.post("/recuperar", data={"email": correo, "csrf_token": t},
                   follow_redirects=False)


def ultimo_enlace(correo):
    """El enlace tal y como le llegaría a la persona, leído del buzón."""
    d = SessionLocal()
    fila = (d.query(OutboxEmail).filter(OutboxEmail.to_email == correo,
                                        OutboxEmail.kind == "reset")
            .order_by(OutboxEmail.id.desc()).first())
    cuerpo = fila.body if fila else None
    d.close()
    if not cuerpo:
        return None
    m = re.search(r"(https?://\S+/recuperar/([A-Za-z0-9_\-]+))", cuerpo)
    return m.groups() if m else None


print(f"DB de prueba: {DB}\n")

with TestClient(app) as boot:
    db = SessionLocal()
    duenio = User(name="Propietaria", email="duenia@test.local",
                  password_hash=hash_password("ClaveVieja123!"), role=RoleEnum.owner)
    inactivo = User(name="Dado de baja", email="baja@test.local",
                    password_hash=hash_password("ClaveVieja123!"),
                    role=RoleEnum.owner, is_active=False)
    # Cuentas aparte para las secciones 7 y 8: el límite es de 3 solicitudes
    # por correo y por hora, así que reutilizar la misma cuenta agotaría el
    # cupo y las pruebas medirían el límite en vez de lo que quieren medir.
    caduca = User(name="Para caducar", email="caduca@test.local",
                  password_hash=hash_password("ClaveVieja123!"), role=RoleEnum.owner)
    duplica = User(name="Para reemplazar", email="duplica@test.local",
                   password_hash=hash_password("ClaveVieja123!"), role=RoleEnum.owner)
    db.add_all([duenio, inactivo, caduca, duplica]); db.commit()
    duenio_id = duenio.id
    db.close()

    c = TestClient(app)

    print("== 1. La respuesta es idéntica exista o no la cuenta ==")
    r_real = pedir_reset(c, "duenia@test.local")
    r_falso = pedir_reset(c, "no-existe-jamas@test.local")
    r_baja = pedir_reset(c, "baja@test.local")
    r_admin = pedir_reset(c, "admin@test.local")
    check("mismo código de estado en los cuatro casos",
          {r_real.status_code, r_falso.status_code, r_baja.status_code,
           r_admin.status_code} == {302},
          f"-> {[x.status_code for x in (r_real, r_falso, r_baja, r_admin)]}")
    destinos = {x.headers.get("location") for x in (r_real, r_falso, r_baja, r_admin)}
    check("mismo destino en los cuatro casos", destinos == {"/recuperar/enviado"},
          f"-> {destinos}")
    cuerpos = {x.text for x in (r_real, r_falso, r_baja, r_admin)}
    check("mismo cuerpo, carácter a carácter", len(cuerpos) == 1)

    print("\n== 2. Solo la cuenta válida recibe token ==")
    d = SessionLocal()
    check("se emitió token para la cuenta real",
          d.query(PasswordResetToken).filter(PasswordResetToken.user_id == duenio_id).count() == 1)
    check("el administrador NO recibe token (D-022)",
          d.query(PasswordResetToken).join(User, User.id == PasswordResetToken.user_id)
           .filter(User.role == RoleEnum.admin).count() == 0)
    check("la cuenta dada de baja tampoco",
          d.query(PasswordResetToken).join(User, User.id == PasswordResetToken.user_id)
           .filter(User.is_active.is_(False)).count() == 0)
    check("cada motivo de rechazo deja su propia marca en la bitácora",
          {"password_reset.suppressed_unknown", "password_reset.suppressed_admin",
           "password_reset.suppressed_inactive"}
          <= {a.action for a in d.query(AuditLog).all()})
    d.close()

    print("\n== 3. El token nunca se guarda en claro ni se filtra ==")
    par = ultimo_enlace("duenia@test.local")
    check("el correo del buzón trae un enlace", par is not None)
    enlace, token = par
    d = SessionLocal()
    fila = d.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == duenio_id).first()
    check("en la base se guarda el sha256, no el token",
          fila.token_hash == hashlib.sha256(token.encode()).hexdigest()
          and len(fila.token_hash) == 64)
    check("el token en claro no está en ninguna columna de la fila",
          token not in " ".join(str(getattr(fila, col.name)) for col in fila.__table__.columns))
    d.close()
    check("el token no aparece en la respuesta ni en las cabeceras de /recuperar",
          token not in r_real.text and token not in str(r_real.headers))

    print("\n== 4. Abrir el enlace NO lo consume (previsualizadores de correo) ==")
    nav = TestClient(app)
    r = nav.get(f"/recuperar/{token}", follow_redirects=False)
    check("redirige al formulario de contraseña nueva",
          r.status_code == 302 and r.headers.get("location") == "/recuperar/nueva",
          f"-> {r.status_code} {r.headers.get('location')}")
    check("el token desaparece de la URL de destino",
          token not in (r.headers.get("location") or ""))
    check("la respuesta pide no cachear ni indexar",
          r.headers.get("cache-control") == "no-store"
          and "noindex" in (r.headers.get("x-robots-tag") or ""))
    d = SessionLocal()
    check("y el token sigue SIN usar tras el GET",
          d.query(PasswordResetToken).filter(
              PasswordResetToken.user_id == duenio_id).first().used_at is None)
    d.close()

    print("\n== 5. Fijar la contraseña: uso único y cierre de sesiones ==")
    # Sesión abierta en otro navegador, que debe morir al completar el cambio.
    otro = TestClient(app)
    t = csrf(otro)
    otro.post("/login", data={"email": "duenia@test.local",
                              "password": "ClaveVieja123!", "csrf_token": t},
              follow_redirects=False)
    check("la sesión previa funciona antes del cambio",
          otro.get("/owner", follow_redirects=False).status_code == 200)

    t = csrf(nav, "/recuperar/nueva")
    r = nav.post("/recuperar/nueva",
                 data={"password": "UnaFraseLargaYNueva1", "password2": "UnaFraseLargaYNueva1",
                       "csrf_token": t}, follow_redirects=False)
    check("el cambio redirige al acceso", r.status_code == 302, f"-> {r.status_code}")
    d = SessionLocal()
    u = d.get(User, duenio_id)
    check("la contraseña nueva funciona", verify_password("UnaFraseLargaYNueva1", u.password_hash))
    check("la vieja ya no", not verify_password("ClaveVieja123!", u.password_hash))
    check("se anota cuándo se cambió", u.password_changed_at is not None)
    f = d.query(PasswordResetToken).filter(PasswordResetToken.user_id == duenio_id).first()
    check("el token queda consumido", f.used_at is not None and f.consumed_reason == "usado")
    d.close()
    check("la sesión abierta en el otro navegador queda cerrada",
          otro.get("/owner", follow_redirects=False).status_code == 302)

    print("\n== 6. El mismo enlace no sirve dos veces ==")
    repe = TestClient(app)
    r = repe.get(f"/recuperar/{token}", follow_redirects=False)
    check("reutilizar el enlace lleva a «ya no vale»",
          r.headers.get("location") == "/recuperar/caducado", f"-> {r.headers.get('location')}")

    print("\n== 7. Un enlace caducado tampoco ==")
    c2 = TestClient(app)
    pedir_reset(c2, "caduca@test.local")
    _, token2 = ultimo_enlace("caduca@test.local")
    d = SessionLocal()
    f2 = d.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == hashlib.sha256(token2.encode()).hexdigest()).first()
    f2.expires_at = datetime.utcnow() - timedelta(minutes=1)
    d.commit(); d.close()
    r = c2.get(f"/recuperar/{token2}", follow_redirects=False)
    check("un enlace caducado lleva al mismo sitio, sin decir por qué",
          r.headers.get("location") == "/recuperar/caducado")

    print("\n== 8. Pedir uno nuevo invalida el anterior ==")
    c3 = TestClient(app)
    pedir_reset(c3, "duplica@test.local")
    _, t_viejo = ultimo_enlace("duplica@test.local")
    pedir_reset(c3, "duplica@test.local")
    _, t_nuevo = ultimo_enlace("duplica@test.local")
    check("los dos enlaces son distintos", t_viejo != t_nuevo)
    r = c3.get(f"/recuperar/{t_viejo}", follow_redirects=False)
    check("el anterior deja de valer",
          r.headers.get("location") == "/recuperar/caducado")

    print("\n== 9. El límite por hora no delata a nadie ==")
    c4 = TestClient(app)
    respuestas = [pedir_reset(c4, "duenia@test.local") for _ in range(8)]
    check("pasado el límite sigue respondiendo 302, nunca 429",
          all(x.status_code == 302 for x in respuestas),
          f"-> {sorted({x.status_code for x in respuestas})}")
    check("y siempre al mismo sitio",
          {x.headers.get("location") for x in respuestas} == {"/recuperar/enviado"})
    d = SessionLocal()
    check("el exceso queda registrado como limitado",
          d.query(AuditLog).filter(AuditLog.action == "password_reset.rate_limited").count() >= 1)
    d.close()

    print("\n== 10. Recuperar no deja sin acceso a toda una IP ==")
    # Este es el motivo de `login_attempts.kind`: sin él, las solicitudes de
    # recuperación contarían como fallos de acceso y bloquearían /login.
    d = SessionLocal()
    resets = d.query(LoginAttempt).filter(LoginAttempt.kind == "reset").count()
    d.close()
    check("hay más solicitudes de recuperación que el tope por IP de /login",
          resets > 10, f"-> {resets}")
    limpio = TestClient(app)
    t = csrf(limpio)
    r = limpio.post("/login", data={"email": "duenia@test.local",
                                    "password": "UnaFraseLargaYNueva1", "csrf_token": t},
                    follow_redirects=False)
    check("se puede entrar igualmente: /login no las cuenta",
          r.status_code == 302, f"-> {r.status_code} (429 significaría que sí las cuenta)")

    print("\n== 11. Mínimo de contraseña unificado en 12 ==")
    check("el mínimo aprobado es 12", MIN_PASSWORD_LEN == 12)
    check("una de 8 se rechaza", validar_fuerza_contrasena("12345678") is not None)
    check("una de 12 se acepta", validar_fuerza_contrasena("123456789012") is None)
    check("si no coinciden, se rechaza",
          validar_fuerza_contrasena("123456789012", "123456789013") is not None)
    check("repetir la actual se rechaza",
          validar_fuerza_contrasena("123456789012", "123456789012",
                                    actual="123456789012") is not None)

    print("\n== 12. Cambio con sesión abierta ==")
    ses = TestClient(app)
    t = csrf(ses)
    ses.post("/login", data={"email": "duenia@test.local",
                             "password": "UnaFraseLargaYNueva1", "csrf_token": t},
             follow_redirects=False)
    t = csrf(ses, "/cambiar-contrasena")
    r = ses.post("/cambiar-contrasena",
                 data={"actual": "EquivocadaDelTodo1", "password": "OtraFraseLarga12345",
                       "password2": "OtraFraseLarga12345", "csrf_token": t},
                 follow_redirects=False)
    d = SessionLocal()
    u = d.get(User, duenio_id)
    check("con la contraseña actual equivocada no cambia nada",
          verify_password("UnaFraseLargaYNueva1", u.password_hash))
    d.close()
    t = csrf(ses, "/cambiar-contrasena")
    r = ses.post("/cambiar-contrasena",
                 data={"actual": "UnaFraseLargaYNueva1", "password": "OtraFraseLarga12345",
                       "password2": "OtraFraseLarga12345", "csrf_token": t},
                 follow_redirects=False)
    d = SessionLocal()
    u = d.get(User, duenio_id)
    check("con la actual correcta sí cambia",
          verify_password("OtraFraseLarga12345", u.password_hash))
    d.close()
    check("y la sesión propia sobrevive al cambio",
          ses.get("/owner", follow_redirects=False).status_code == 200)

    print("\n== 13. El buzón de salida tiene doble puerta ==")
    anon = TestClient(app)
    check("sin sesión, no se ve",
          anon.get("/admin/correos", follow_redirects=False).status_code == 302)
    check("con sesión de propietario, tampoco",
          ses.get("/admin/correos", follow_redirects=False).status_code == 302)

    print("\n== 14. «Ver contraseña» no mete código en el HTML ==")
    html = TestClient(app).get("/login").text
    check("el botón está en el formulario de acceso", 'data-pw-toggle="password"' in html)
    check("hay enlace a «olvidaste tu contraseña»", 'href="/recuperar"' in html)
    for patron in ("onclick=", "onsubmit=", "onchange=", "javascript:"):
        check(f"no aparece {patron} en el HTML servido", patron not in html)
    for ruta in ("/recuperar", "/recuperar/enviado", "/recuperar/caducado"):
        t_html = TestClient(app).get(ruta).text
        check(f"{ruta} tampoco trae código en línea",
              "onclick=" not in t_html and "<script>" not in t_html)

    print("\n== 15. Clave temporal: obliga a cambiarla, pero NO encierra ==")
    d = SessionLocal()
    temp = User(name="Inquilino nuevo", email="temporal@test.local",
                password_hash=hash_password("ClaveTemporal123"),
                role=RoleEnum.tenant, must_change_password=True)
    d.add(temp); d.commit(); temp_id = temp.id; d.close()

    tmp = TestClient(app)
    t = csrf(tmp)
    r = tmp.post("/login", data={"email": "temporal@test.local",
                                 "password": "ClaveTemporal123", "csrf_token": t},
                 follow_redirects=False)
    check("puede iniciar sesión con la clave temporal", r.status_code == 302,
          f"-> {r.status_code}")

    r = tmp.get("/inquilino", follow_redirects=False)
    check("al navegar se le manda a cambiarla",
          r.status_code == 302 and r.headers.get("location") == "/cambiar-contrasena",
          f"-> {r.status_code} {r.headers.get('location')}")

    # Lo más importante de esta sección: que la puerta de salida esté abierta.
    r = tmp.get("/cambiar-contrasena", follow_redirects=False)
    check("SÍ puede abrir el formulario de cambio (sin bucle de redirecciones)",
          r.status_code == 200, f"-> {r.status_code}")
    check("y el formulario le explica por qué está ahí", "temporal" in r.text.lower())
    check("puede cerrar sesión",
          tmp.get("/logout", follow_redirects=False).status_code == 302)
    check("el CSS carga, así que la pantalla no sale en crudo",
          TestClient(app).get("/static/platform.css").status_code == 200)

    # Vuelve a entrar y cambia la contraseña de verdad.
    t = csrf(tmp)
    tmp.post("/login", data={"email": "temporal@test.local",
                             "password": "ClaveTemporal123", "csrf_token": t},
             follow_redirects=False)
    t = csrf(tmp, "/cambiar-contrasena")
    r = tmp.post("/cambiar-contrasena",
                 data={"actual": "ClaveTemporal123", "password": "MiPropiaFrase12345",
                       "password2": "MiPropiaFrase12345", "csrf_token": t},
                 follow_redirects=False)
    check("el cambio se acepta", r.status_code == 302)
    d = SessionLocal()
    u = d.get(User, temp_id)
    check("la marca de clave temporal se levanta", not u.must_change_password)
    d.close()
    r = tmp.get("/inquilino", follow_redirects=False)
    check("y ya puede navegar con normalidad", r.status_code == 200, f"-> {r.status_code}")

    print("\n== 16. A quien no tiene clave temporal no le afecta ==")
    normal = TestClient(app)
    t = csrf(normal)
    normal.post("/login", data={"email": "duenia@test.local",
                                "password": "OtraFraseLarga12345", "csrf_token": t},
                follow_redirects=False)
    check("entra y navega sin interceptación",
          normal.get("/owner", follow_redirects=False).status_code == 200)

    print("\n== 12. Reseteo forzado por el administrador (D-022) ==")
    import pyotp

    d = SessionLocal()
    adm = d.query(User).filter(User.role == RoleEnum.admin).first()
    secreto = pyotp.random_base32()
    adm.totp_secret, adm.totp_enabled, adm.must_change_password = secreto, True, False
    victima = User(name="Con Teléfono", email="contel@test.local", phone="+52 555 0100 4321",
                   password_hash=hash_password("ClaveVieja12345"), role=RoleEnum.owner)
    sintel = User(name="Sin Teléfono", email="sintel@test.local",
                  password_hash=hash_password("ClaveVieja12345"), role=RoleEnum.owner)
    d.add_all([victima, sintel]); d.commit()
    vid, sid_u, adm_id = victima.id, sintel.id, adm.id
    hash_viejo = victima.password_hash
    d.close()

    cadm = TestClient(app)
    t = csrf(cadm)
    cadm.post("/login", data={"email": "admin@test.local", "password": "TestPass123!",
                              "csrf_token": t}, follow_redirects=False)
    cadm.post("/2fa", data={"code": pyotp.TOTP(secreto).now(), "csrf_token": csrf(cadm, "/2fa")},
              follow_redirects=False)
    check("el administrador entra", cadm.get("/admin").status_code == 200)

    ficha = cadm.get(f"/admin/users/{vid}").text
    check("la ficha pide los últimos dígitos", 'name="telefono_confirmacion"' in ficha)
    # La pista va enmascarada. El administrador puede ver el teléfono completo
    # más arriba, en los datos del usuario —es su trabajo—, pero el bloque de
    # reseteo no se lo recuerda: el dato lo tiene que decir la persona.
    check("la pista del teléfono va enmascarada", "••••" in ficha)

    # Sin motivo no se hace nada: el historial tiene que poder explicarse.
    r = cadm.post(f"/admin/users/{vid}/password",
                  data={"telefono_confirmacion": "4321", "motivo": "",
                        "csrf_token": csrf(cadm, f"/admin/users/{vid}")},
                  follow_redirects=False)
    d = SessionLocal()
    check("sin motivo no restablece", d.get(User, vid).password_hash == hash_viejo)
    d.close()

    # Dígitos que no coinciden: se rechaza y queda el intento.
    r = cadm.post(f"/admin/users/{vid}/password",
                  data={"telefono_confirmacion": "9999", "motivo": "llamó por teléfono",
                        "csrf_token": csrf(cadm, f"/admin/users/{vid}")},
                  follow_redirects=False)
    d = SessionLocal()
    check("con dígitos equivocados NO cambia la clave",
          d.get(User, vid).password_hash == hash_viejo)
    rechazos = d.query(AuditLog).filter(
        AuditLog.action == "admin.reset_forzado_fallido").count()
    d.close()
    check("y el intento fallido queda registrado", rechazos == 1, f"-> {rechazos}")

    # Con los dígitos correctos: credenciales nuevas.
    r = cadm.post(f"/admin/users/{vid}/password",
                  data={"telefono_confirmacion": "4321", "motivo": "perdió su correo",
                        "csrf_token": csrf(cadm, f"/admin/users/{vid}")},
                  follow_redirects=False)
    check("se acepta", r.status_code == 302, f"-> {r.status_code}")
    d = SessionLocal()
    v = d.get(User, vid)
    check("la clave cambió", v.password_hash != hash_viejo)
    check("y obliga a cambiarla al entrar", v.must_change_password is True)
    fila = (d.query(AuditLog).filter(AuditLog.action == "admin.reset_forzado")
            .order_by(AuditLog.id.desc()).first())
    d.close()
    check("queda quién, a quién y por qué",
          fila is not None and fila.actor_user_id == adm_id and fila.object_id == vid
          and "perdió su correo" in (fila.meta or ""))
    check("y con qué se verificó la identidad", "identidad=telefono" in (fila.meta or ""))

    # La clave nueva se muestra UNA vez, en el aviso.
    pantalla = cadm.get(f"/admin/users/{vid}").text
    check("la clave nueva se enseña una sola vez", "Credenciales nuevas" in pantalla)
    check("y al recargar ya no está",
          "Credenciales nuevas" not in cadm.get(f"/admin/users/{vid}").text)

    # Sin teléfono en la ficha: hay que declararlo.
    r = cadm.post(f"/admin/users/{sid_u}/password",
                  data={"motivo": "no tiene correo ni teléfono",
                        "csrf_token": csrf(cadm, f"/admin/users/{sid_u}")},
                  follow_redirects=False)
    d = SessionLocal()
    sin_marca = d.query(AuditLog).filter(AuditLog.action == "admin.reset_forzado",
                                         AuditLog.object_id == sid_u).count()
    d.close()
    check("sin teléfono y sin declararlo, no se restablece", sin_marca == 0, f"-> {sin_marca}")
    r = cadm.post(f"/admin/users/{sid_u}/password",
                  data={"sin_telefono": "1", "motivo": "no tiene correo ni teléfono",
                        "csrf_token": csrf(cadm, f"/admin/users/{sid_u}")},
                  follow_redirects=False)
    d = SessionLocal()
    marca = (d.query(AuditLog).filter(AuditLog.action == "admin.reset_forzado",
                                      AuditLog.object_id == sid_u)
             .order_by(AuditLog.id.desc()).first())
    d.close()
    check("declarándolo sí restablece", marca is not None)
    check("y deja escrito que fue sin verificar",
          "identidad=sin_telefono" in (marca.meta or "") if marca else False)

    print("\n== 13. El historial de reseteos se puede leer (D-029) ==")
    r = cadm.get("/admin/reseteos")
    check("el administrador lo abre", r.status_code == 200, f"-> {r.status_code}")
    check("sale quién lo hizo y a quién", "Con Teléfono" in r.text and "Sin Teléfono" in r.text)
    check("los intentos rechazados también", "rechazado" in r.text)
    check("y el motivo", "perdió su correo" in r.text)
    r = normal.get("/admin/reseteos", follow_redirects=False)
    check("un propietario no entra", r.status_code in (302, 303, 403, 404), f"-> {r.status_code}")

print(f"\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
