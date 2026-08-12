"""Modulo de inquilinos + candados de modo simulacion. Base desechable."""
import os, sys, io, re, tempfile
import pathlib

TMP = tempfile.mkdtemp(prefix="aura_ten_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(TMP,'t.db')}"
os.environ["UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["APP_ENV"] = "dev"
os.environ["DATA_MODE"] = "mock"
os.environ["TENANT_MODULE_ENABLED"] = "true"
os.environ.pop("ANTHROPIC_API_KEY", None)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from fastapi import HTTPException
from PIL import Image
from app.main import app
from app.db import SessionLocal
from app.auth import hash_password
from app.models import (User, Property, Lease, RoleEnum, LeaseStatusEnum,
                        MaintenanceTicket, TicketPhoto, TicketEvent)

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  PASS  {name}")
    else: fail += 1; print(f"  FAIL  {name} {extra}")

def tok(client, url="/login"):
    r = client.get(url)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    return m.group(1) if m else None

def jpeg_bytes(w=2400, h=1800, exif_gps=True):
    img = Image.new("RGB", (w, h), (120, 90, 60))
    buf = io.BytesIO()
    if exif_gps:
        from PIL import Image as I
        exif = I.Exif()
        exif[0x8825] = {1: "N", 2: (21.0, 9.0, 0.0), 3: "W", 4: (86.0, 51.0, 0.0)}
        img.save(buf, format="JPEG", exif=exif)
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()

with TestClient(app) as c:
    db = SessionLocal()
    def mk(name, email, role):
        u = User(name=name, email=email, password_hash=hash_password("Pass123456!"), role=role)
        db.add(u); db.commit(); db.refresh(u); return u
    owner = mk("Owner A", "owner@example.com", RoleEnum.owner)
    ten   = mk("Inquilino A", "ten@example.com", RoleEnum.tenant)
    ten2  = mk("Inquilino B", "ten2@example.com", RoleEnum.tenant)
    prop = Property(owner_id=owner.id, title="Casa A"); db.add(prop); db.commit(); db.refresh(prop)
    lease = Lease(property_id=prop.id, tenant_id=ten.id, status=LeaseStatusEnum.active)
    db.add(lease); db.commit()
    # IDs como enteros simples: los objetos ORM quedan inutilizables al cerrar la sesion
    PROP_ID, TEN_ID, TEN2_ID, OWNER_ID = prop.id, ten.id, ten2.id, owner.id
    db.close()

    print("== 1. Candados de modo simulacion ==")
    from app.mockmode import validate_mock_email, validate_mock_phone, is_mock
    check("is_mock activo", is_mock())
    try:
        validate_mock_email("persona.real@gmail.com"); check("rechaza correo real", False, "(permitido!)")
    except HTTPException as e: check("rechaza correo real -> 400", e.status_code == 400)
    try:
        validate_mock_email("prueba@example.com"); check("acepta dominio de prueba", True)
    except HTTPException: check("acepta dominio de prueba", False)
    try:
        validate_mock_phone("+52 998 123 4567"); check("rechaza telefono real", False, "(permitido!)")
    except HTTPException as e: check("rechaza telefono real -> 400", e.status_code == 400)
    try:
        validate_mock_phone("+52 555 0100 0000"); check("acepta telefono reservado", True)
    except HTTPException: check("acepta telefono reservado", False)

    print("\n== 2. Base separada (candado principal) ==")
    from app.db import _resolve_database_url, MOCK_DB_PATH, DEFAULT_DB_PATH
    os.environ.pop("DATABASE_URL")
    os.environ["DATA_MODE"] = "mock"
    check("modo mock -> platform-mock.db", "platform-mock.db" in _resolve_database_url())
    os.environ["DATA_MODE"] = "live"
    check("modo live -> platform.db", _resolve_database_url().endswith("platform.db"))
    os.environ["DATA_MODE"] = "mock"
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(TMP,'t.db')}"

    print("\n== 3. Candado legal ==")
    from app.mockmode import require_legal_clearance_for_live
    os.environ["DATA_MODE"] = "live"; os.environ.pop("LEGAL_CLEARANCE_REF", None)
    try:
        require_legal_clearance_for_live(); check("live sin Legal -> bloquea arranque", False, "(arranco!)")
    except RuntimeError: check("live sin referencia de Legal NO arranca", True)
    os.environ["LEGAL_CLEARANCE_REF"] = "LEGAL-2026-001"
    try:
        require_legal_clearance_for_live(); check("live con referencia si arranca", True)
    except RuntimeError: check("live con referencia si arranca", False)
    os.environ["DATA_MODE"] = "mock"; os.environ.pop("LEGAL_CLEARANCE_REF")

    print("\n== 4. Sesion de inquilino ==")
    t = tok(c)
    r = c.post("/login", data={"email": "ten@example.com", "password": "Pass123456!",
                               "csrf_token": t}, follow_redirects=False)
    check("inquilino inicia sesion", r.status_code == 302, f"(fue {r.status_code})")
    r = c.get("/inquilino")
    check("panel de inquilino carga", r.status_code == 200, f"(fue {r.status_code})")
    check("banda MODO PRUEBAS visible", "MODO PRUEBAS" in r.text)
    check("WhatsApp desactivado en pruebas", "desactivado" in r.text or "wa.me" not in r.text)

    print("\n== 5. Crear ticket con foto ==")
    t = tok(c, "/inquilino/tickets/nuevo")
    check("formulario manual disponible sin llave AI", t is not None)
    r = c.post("/inquilino/tickets/nuevo",
               data={"title": "Gotea el lavabo", "description": "Desde ayer",
                     "category": "plomeria", "priority": "media",
                     "location_in_unit": "Bano", "csrf_token": t},
               files=[("photos", ("foto.jpg", jpeg_bytes(), "image/jpeg"))],
               follow_redirects=False)
    check("ticket creado -> 302", r.status_code == 302, f"(fue {r.status_code})")
    db = SessionLocal()
    tk = db.query(MaintenanceTicket).first()
    check("ticket guardado", tk is not None)
    check("public_ref generada", bool(tk and tk.public_ref), f"({tk.public_ref if tk else None})")
    check("property_id del servidor, no del formulario", tk.property_id == PROP_ID)
    ph = db.query(TicketPhoto).filter(TicketPhoto.ticket_id == tk.id).first()
    check("foto guardada", ph is not None)
    check("foto redimensionada a <=1568px", ph and max(ph.width, ph.height) <= 1568,
          f"({ph.width}x{ph.height})" if ph else "")
    check("EXIF marcado como eliminado", ph and ph.exif_stripped)
    # verificacion real del EXIF en disco
    from app.uploads import resolve_stored_path
    with Image.open(resolve_stored_path(ph.stored_path)) as im:
        gps = (im.getexif() or {}).get(0x8825)
    check("GPS del EXIF realmente eliminado", not gps, f"(gps={gps})")
    ev = db.query(TicketEvent).filter(TicketEvent.ticket_id == tk.id).count()
    check("historial registrado", ev >= 1)
    TK_ID, PH_ID = tk.id, ph.id
    db.close()

    print("\n== 6. Emergencia detectada del lado del servidor ==")
    t = tok(c, "/inquilino/tickets/nuevo")
    c.post("/inquilino/tickets/nuevo",
           data={"title": "Huele a gas en la cocina", "description": "fuerte olor",
                 "category": "otro", "priority": "baja", "csrf_token": t},
           follow_redirects=False)
    db = SessionLocal()
    tk2 = db.query(MaintenanceTicket).filter(MaintenanceTicket.title.like("%gas%")).first()
    check("prioridad elevada a emergencia pese a elegir 'baja'",
          tk2 and tk2.priority.value == "emergencia", f"({tk2.priority.value if tk2 else None})")
    db.close()

    print("\n== 7. Fotos protegidas (no publicas) ==")
    r = c.get(f"/media/tickets/{TK_ID}/{PH_ID}")
    check("autor ve su foto", r.status_code == 200, f"(fue {r.status_code})")
    anon = TestClient(app)
    r = anon.get(f"/media/tickets/{TK_ID}/{PH_ID}")
    check("sin sesion -> 401", r.status_code == 401, f"(fue {r.status_code})")
    c2 = TestClient(app)
    t2 = tok(c2)
    c2.post("/login", data={"email": "ten2@example.com", "password": "Pass123456!",
                            "csrf_token": t2}, follow_redirects=False)
    r = c2.get(f"/media/tickets/{TK_ID}/{PH_ID}")
    check("otro inquilino -> 404", r.status_code == 404, f"(fue {r.status_code})")
    r = c2.get(f"/inquilino/tickets/{TK_ID}")
    check("otro inquilino no ve el ticket -> 404", r.status_code == 404, f"(fue {r.status_code})")

    print("\n== 8. Archivos maliciosos ==")
    t = tok(c, "/inquilino/tickets/nuevo")
    r = c.post("/inquilino/tickets/nuevo",
               data={"title": "Prueba", "csrf_token": t},
               files=[("photos", ("shell.jpg", b"<?php system($_GET['c']); ?>", "image/jpeg"))],
               follow_redirects=False)
    check("PHP disfrazado de .jpg rechazado -> 400", r.status_code == 400, f"(fue {r.status_code})")

    print("\n== 9. Agente AI degrada sin llave ==")
    from app import ai_agent
    check("is_configured() False sin llave", not ai_agent.is_configured())
    try:
        ai_agent.draft_ticket([{"role": "user", "content": "hola"}])
        check("draft_ticket lanza AgentUnavailable", False, "(no lanzo)")
    except ai_agent.AgentUnavailable:
        check("draft_ticket lanza AgentUnavailable (no rompe)", True)
    check("red de emergencia funciona sin AI",
          ai_agent.apply_emergency_safety_net("hay humo", {})["is_emergency"] is True)

    print("\n== 10. Bandera del modulo ==")
    os.environ["TENANT_MODULE_ENABLED"] = "false"
    r = c.get("/inquilino")
    check("modulo apagado -> 503", r.status_code == 503, f"(fue {r.status_code})")
    os.environ["TENANT_MODULE_ENABLED"] = "true"

print(f"\n{'='*46}\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
