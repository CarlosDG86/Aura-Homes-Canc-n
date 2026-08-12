"""Bandejas y comunicacion en ambos sentidos. Base desechable."""
import os, sys, re, tempfile
import pathlib

TMP = tempfile.mkdtemp(prefix="aura_box_")
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
                        Message, Announcement, AnnouncementRecipient)

ok = fail = 0
def check(n, c, e=""):
    global ok, fail
    if c: ok += 1; print(f"  PASS  {n}")
    else: fail += 1; print(f"  FAIL  {n} {e}")

def tok(cl, url):
    r = cl.get(url)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    return m.group(1) if m else None

def login(cl, email):
    t = tok(cl, "/login")
    return cl.post("/login", data={"email": email, "password": "Pass123456!", "csrf_token": t},
                   follow_redirects=False)

with TestClient(app) as c:
    db = SessionLocal()
    def mk(n, e, r):
        u = User(name=n, email=e, password_hash=hash_password("Pass123456!"), role=r)
        db.add(u); db.commit(); db.refresh(u); return u
    oa = mk("Owner A", "oa@example.com", RoleEnum.owner)
    ob = mk("Owner B", "ob@example.com", RoleEnum.owner)
    ta = mk("Inq A", "ia@example.com", RoleEnum.tenant)
    tb = mk("Inq B", "ib@example.com", RoleEnum.tenant)
    pa = Property(owner_id=oa.id, title="Casa A"); db.add(pa)
    pb = Property(owner_id=ob.id, title="Casa B"); db.add(pb); db.commit(); db.refresh(pa); db.refresh(pb)
    db.add(Lease(property_id=pa.id, tenant_id=ta.id, status=LeaseStatusEnum.active))
    db.add(Lease(property_id=pb.id, tenant_id=tb.id, status=LeaseStatusEnum.active))
    db.commit()
    OA, OB, TA, TB = oa.id, ob.id, ta.id, tb.id
    db.close()

    ca = TestClient(app); login(ca, "oa@example.com")   # owner A
    cb = TestClient(app); login(cb, "ob@example.com")   # owner B
    cta = TestClient(app); login(cta, "ia@example.com") # inquilino A
    ctb = TestClient(app); login(ctb, "ib@example.com") # inquilino B

    print("== 1. Owner -> inquilino ==")
    t = tok(ca, "/owner/mensajes")
    r = ca.post("/owner/mensajes", data={"recipient_id": TA, "subject": "Visita",
                "body": "Paso el jueves", "csrf_token": t}, follow_redirects=False)
    check("owner envia -> 302", r.status_code == 302, f"({r.status_code})")

    print("\n== 2. El inquilino lo ve en su bandeja ==")
    r = cta.get("/inquilino/mensajes")
    check("bandeja carga", r.status_code == 200, f"({r.status_code})")
    check("ve el mensaje", "Paso el jueves" in r.text)
    check("resaltado como nuevo", "badge-new" in r.text)
    check("inquilino B NO lo ve", "Paso el jueves" not in ctb.get("/inquilino/mensajes").text)

    print("\n== 3. Se marca leido al abrir ==")
    db = SessionLocal()
    unread = db.query(Message).filter(Message.recipient_user_id == TA,
                                      Message.read_at.is_(None)).count()
    check("ya no queda sin leer", unread == 0, f"({unread} sin leer)")
    db.close()
    r = cta.get("/inquilino/mensajes")
    check("segunda visita ya no marca 'nuevo'", "badge-new" not in r.text)

    print("\n== 4. Inquilino -> owner (la vuelta) ==")
    t = tok(cta, "/inquilino/mensajes")
    r = cta.post("/inquilino/mensajes", data={"subject": "Gracias",
                 "body": "El jueves me viene bien", "csrf_token": t}, follow_redirects=False)
    check("inquilino responde -> 302", r.status_code == 302, f"({r.status_code})")
    db = SessionLocal()
    m = db.query(Message).filter(Message.sender_user_id == TA).first()
    check("mensaje guardado", m is not None)
    check("destinatario resuelto en servidor (su owner)", m and m.recipient_user_id == OA,
          f"(fue {m.recipient_user_id if m else None})")
    db.close()

    print("\n== 5. El owner lo recibe ==")
    r = ca.get("/owner")
    # El contador vive ahora en la insignia del menu lateral, no en una fila de enlaces.
    import re as _re
    m = _re.search(r'href="/owner/mensajes"[^>]*>\s*Mensajes\s*<span class="nav-badge">(\d+)</span>', r.text)
    check("menu lateral muestra 1 mensaje sin leer", bool(m) and m.group(1) == "1",
          f"(insignia={m.group(1) if m else 'ausente'})")
    r = ca.get("/owner/mensajes")
    check("owner ve la respuesta", "El jueves me viene bien" in r.text)
    check("resaltada como nueva", "badge-new" in r.text)
    check("owner B NO la ve", "El jueves me viene bien" not in cb.get("/owner/mensajes").text)
    db = SessionLocal()
    check("marcada como leida",
          db.query(Message).filter(Message.recipient_user_id == OA,
                                   Message.read_at.is_(None)).count() == 0)
    db.close()

    print("\n== 6. El inquilino NO elige destinatario ==")
    # Aunque mande recipient_id del owner B, el servidor lo ignora: usa su lease.
    t = tok(cta, "/inquilino/mensajes")
    cta.post("/inquilino/mensajes", data={"recipient_id": OB, "subject": "Intento",
             "body": "mensaje dirigido", "csrf_token": t}, follow_redirects=False)
    db = SessionLocal()
    m = db.query(Message).filter(Message.body == "mensaje dirigido").first()
    check("recipient_id del formulario ignorado", m and m.recipient_user_id == OA,
          f"(fue {m.recipient_user_id if m else None})")
    db.close()
    check("owner B no recibio nada", "mensaje dirigido" not in cb.get("/owner/mensajes").text)

    print("\n== 7. Comunicados llegan a la bandeja ==")
    t = tok(ca, "/owner/comunicados")
    ca.post("/owner/comunicados", data={"title": "Fumigacion", "body": "El lunes 10",
            "audience": "todos", "csrf_token": t}, follow_redirects=False)
    r = cta.get("/inquilino/mensajes")
    check("inquilino A ve el comunicado", "Fumigacion" in r.text and "El lunes 10" in r.text)
    check("inquilino B no lo ve", "Fumigacion" not in ctb.get("/inquilino/mensajes").text)
    db = SessionLocal()
    check("comunicado marcado como leido",
          db.query(AnnouncementRecipient).filter(AnnouncementRecipient.user_id == TA,
                                                 AnnouncementRecipient.read_at.is_(None)).count() == 0)
    db.close()

    print("\n== 8. Contador del inquilino ==")
    t = tok(ca, "/owner/mensajes")
    ca.post("/owner/mensajes", data={"recipient_id": TA, "subject": "Otro",
            "body": "Segundo aviso", "csrf_token": t}, follow_redirects=False)
    r = cta.get("/inquilino")
    import re as _re2
    m = _re2.search(r'href="/inquilino/mensajes"[^>]*>\s*Mi bandeja\s*<span class="nav-badge">(\d+)</span>', r.text)
    check("menu lateral del inquilino muestra 1 sin leer", bool(m) and m.group(1) == "1",
          f"(insignia={m.group(1) if m else 'ausente'})")

print(f"\n{'='*46}\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
