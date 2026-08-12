"""E4 - Portal del propietario. Base desechable, nunca platform.db real."""
import os, sys, re, tempfile
import pathlib

TMP = tempfile.mkdtemp(prefix="aura_own_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(TMP,'t.db')}"
os.environ["UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["APP_ENV"] = "dev"; os.environ["DATA_MODE"] = "mock"
os.environ["TENANT_MODULE_ENABLED"] = "true"
os.environ["OWNER_PROPERTY_MANAGE_ENABLED"] = "true"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.auth import hash_password
from app.models import (User, Property, Lease, RoleEnum, LeaseStatusEnum,
                        MaintenanceTicket, TicketStatusEnum, TicketPriorityEnum,
                        TicketEvent, Announcement, AnnouncementRecipient, Message)

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
    la = Lease(property_id=pa.id, tenant_id=ta.id, status=LeaseStatusEnum.active)
    lb = Lease(property_id=pb.id, tenant_id=tb.id, status=LeaseStatusEnum.active)
    db.add(la); db.add(lb); db.commit(); db.refresh(la); db.refresh(lb)
    tkA = MaintenanceTicket(property_id=pa.id, reported_by_user_id=ta.id, title="Fuga A",
                            status=TicketStatusEnum.open, priority=TicketPriorityEnum.alta)
    tkB = MaintenanceTicket(property_id=pb.id, reported_by_user_id=tb.id, title="Fuga B",
                            status=TicketStatusEnum.open)
    db.add(tkA); db.add(tkB); db.commit(); db.refresh(tkA); db.refresh(tkB)
    PA, PB, TKA, TKB, LA, LB, TA, TB, OB = pa.id, pb.id, tkA.id, tkB.id, la.id, lb.id, ta.id, tb.id, ob.id
    db.close()

    ca = TestClient(app); login(ca, "oa@example.com")
    cb = TestClient(app); login(cb, "ob@example.com")

    print("== 1. Tickets del propietario ==")
    r = ca.get("/owner/tickets")
    check("listado carga", r.status_code == 200, f"({r.status_code})")
    check("ve su ticket", "Fuga A" in r.text)
    check("NO ve el ticket de B", "Fuga B" not in r.text)
    check("detalle propio -> 200", ca.get(f"/owner/tickets/{TKA}").status_code == 200)
    check("detalle ajeno -> 404", ca.get(f"/owner/tickets/{TKB}").status_code == 404,
          f"({ca.get(f'/owner/tickets/{TKB}').status_code})")

    print("\n== 2. Resolver exige nota ==")
    t = tok(ca, f"/owner/tickets/{TKA}")
    r = ca.post(f"/owner/tickets/{TKA}/actualizar",
                data={"accion": "resolver", "body": "", "csrf_token": t}, follow_redirects=False)
    check("resolver sin nota -> 400", r.status_code == 400, f"({r.status_code})")
    t = tok(ca, f"/owner/tickets/{TKA}")
    r = ca.post(f"/owner/tickets/{TKA}/actualizar",
                data={"accion": "resolver", "body": "Se cambio el empaque", "csrf_token": t},
                follow_redirects=False)
    check("resolver con nota -> 302", r.status_code == 302, f"({r.status_code})")
    db = SessionLocal()
    tt = db.query(MaintenanceTicket).filter(MaintenanceTicket.id == TKA).first()
    check("estado resuelto", tt.status == TicketStatusEnum.resolved)
    check("resolved_at grabado", tt.resolved_at is not None)
    check("nota guardada", tt.resolution_notes == "Se cambio el empaque")
    check("evento en historial",
          db.query(TicketEvent).filter(TicketEvent.ticket_id == TKA).count() >= 1)
    db.close()

    print("\n== 3. No se puede tocar un ticket ajeno ==")
    t = tok(cb, "/owner/perfil")
    r = cb.post(f"/owner/tickets/{TKA}/actualizar",
                data={"accion": "reabrir", "body": "x", "csrf_token": t}, follow_redirects=False)
    check("owner B actualizando ticket de A -> 404", r.status_code == 404, f"({r.status_code})")

    print("\n== 4. Alta de inquilino ==")
    t = tok(ca, "/owner/inquilinos")
    r = ca.post("/owner/inquilinos", data={"name": "Nuevo Inq", "email": "nuevo@example.com",
                "phone": "+52 555 0100 0001", "property_id": PA, "csrf_token": t},
                follow_redirects=False)
    check("alta correcta -> 302", r.status_code == 302, f"({r.status_code})")
    db = SessionLocal()
    nu = db.query(User).filter(User.email == "nuevo@example.com").first()
    check("inquilino creado", nu is not None)
    check("rol tenant", nu and nu.role == RoleEnum.tenant)
    check("must_change_password activo", nu and nu.must_change_password)
    check("vinculado a la vivienda",
          db.query(Lease).filter(Lease.tenant_id == nu.id, Lease.property_id == PA).count() == 1)
    db.close()

    print("\n== 5. Correo real rechazado en modo pruebas ==")
    t = tok(ca, "/owner/inquilinos")
    r = ca.post("/owner/inquilinos", data={"name": "Real", "email": "persona@gmail.com",
                "property_id": PA, "csrf_token": t}, follow_redirects=False)
    check("correo real -> 400", r.status_code == 400, f"({r.status_code})")

    print("\n== 6. Campo oculto manipulado (DESIGN.md 11) ==")
    t = tok(ca, "/owner/inquilinos")
    r = ca.post("/owner/inquilinos", data={"name": "Intruso", "email": "intruso@example.com",
                "property_id": PB, "csrf_token": t}, follow_redirects=False)
    check("owner A asignando a casa de B -> 404", r.status_code == 404, f"({r.status_code})")
    db = SessionLocal()
    check("NO se creo el usuario intruso",
          db.query(User).filter(User.email == "intruso@example.com").count() == 0)
    db.close()

    print("\n== 7. Comunicados ==")
    t = tok(ca, "/owner/comunicados")
    r = ca.post("/owner/comunicados", data={"title": "Mantenimiento", "body": "El sabado",
                "audience": "todos", "csrf_token": t}, follow_redirects=False)
    check("comunicado enviado -> 302", r.status_code == 302, f"({r.status_code})")
    db = SessionLocal()
    ann = db.query(Announcement).first()
    rec_ids = [r_.user_id for r_ in db.query(AnnouncementRecipient).all()]
    check("comunicado guardado", ann is not None)
    check("llego a inquilino de A", TA in rec_ids)
    check("NO llego al inquilino de B", TB not in rec_ids)
    db.close()

    print("\n== 8. Mensajes 1:1 ==")
    t = tok(ca, "/owner/mensajes")
    r = ca.post("/owner/mensajes", data={"recipient_id": TA, "subject": "Hola",
                "body": "Mensaje", "csrf_token": t}, follow_redirects=False)
    check("mensaje a su inquilino -> 302", r.status_code == 302, f"({r.status_code})")
    t = tok(ca, "/owner/mensajes")
    r = ca.post("/owner/mensajes", data={"recipient_id": TB, "subject": "x",
                "body": "y", "csrf_token": t}, follow_redirects=False)
    check("mensaje al inquilino de B -> 404", r.status_code == 404, f"({r.status_code})")

    print("\n== 9. Reporte por unidad + CSV ==")
    r = ca.get("/owner/tickets/reporte")
    check("reporte carga", r.status_code == 200 and "Casa A" in r.text)
    check("reporte NO incluye casa de B", "Casa B" not in r.text)
    r = ca.get("/owner/tickets/reporte?formato=csv")
    check("CSV descarga", r.status_code == 200 and "text/csv" in r.headers.get("content-type", ""))
    check("CSV con encabezados", "Propiedad" in r.text and "Horas promedio" in r.text)

    print("\n== 10. Perfil: contact_phone ==")
    t = tok(ca, "/owner/perfil")
    r = ca.post("/owner/perfil", data={"name": "Owner A", "contact_phone": "+52 555 0100 9999",
                "csrf_token": t})
    check("guardado -> 200", r.status_code == 200, f"({r.status_code})")
    db = SessionLocal()
    check("contact_phone guardado",
          db.query(User).filter(User.email == "oa@example.com").first().contact_phone == "+52 555 0100 9999")
    db.close()
    t = tok(ca, "/owner/perfil")
    r = ca.post("/owner/perfil", data={"name": "Owner A", "contact_phone": "+52 998 1234567",
                "csrf_token": t})
    check("telefono real rechazado en pruebas -> 400", r.status_code == 400, f"({r.status_code})")

    print("\n== 11. Bandera OWNER_PROPERTY_MANAGE_ENABLED (dos capas) ==")
    os.environ["OWNER_PROPERTY_MANAGE_ENABLED"] = "false"
    r = ca.post("/api/owner/properties", json={"title": "Nueva"},
                headers={"x-csrf-token": tok(ca, "/owner/perfil") or ""})
    check("apagada: crear propiedad -> 403", r.status_code == 403, f"({r.status_code})")
    r = ca.delete(f"/api/owner/properties/{PA}", headers={"x-csrf-token": tok(ca, "/owner/perfil") or ""})
    check("apagada: borrar propiedad -> 403", r.status_code == 403, f"({r.status_code})")
    os.environ["OWNER_PROPERTY_MANAGE_ENABLED"] = "true"
    r = ca.post("/api/owner/properties", json={"title": "Nueva"},
                headers={"x-csrf-token": tok(ca, "/owner/perfil") or ""})
    check("encendida: crear propiedad -> 201", r.status_code == 201, f"({r.status_code})")

    print("\n== 12. Terminar arrendamiento corta acceso ==")
    t = tok(ca, "/owner/inquilinos")
    r = ca.post(f"/owner/inquilinos/{LA}/terminar", data={"csrf_token": t}, follow_redirects=False)
    check("terminar -> 302", r.status_code == 302, f"({r.status_code})")
    t = tok(cb, "/owner/inquilinos")
    r = cb.post(f"/owner/inquilinos/{LA}/terminar", data={"csrf_token": t}, follow_redirects=False)
    check("owner B terminando arrendamiento de A -> 404", r.status_code == 404, f"({r.status_code})")

print(f"\n{'='*46}\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
