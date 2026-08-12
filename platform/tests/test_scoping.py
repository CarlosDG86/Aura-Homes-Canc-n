"""Aislamiento entre propietarios (QA.md §1) — la prueba mas importante.
Base desechable; NUNCA toca platform.db real."""
import os, sys, tempfile, pathlib
import pathlib

TMP = tempfile.mkdtemp(prefix="aura_scope_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(TMP,'t.db')}"
os.environ["APP_ENV"] = "dev"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.auth import hash_password
from app.models import (User, Property, Lease, MaintenanceTicket, RoleEnum,
                        LeaseStatusEnum, TicketStatusEnum)
from app.scoping import (scoped_properties, owned_properties, scoped_tickets,
                         scoped_leases, scoped_users, get_scoped_property_or_404,
                         assert_can_assign_property)
from fastapi import HTTPException

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  PASS  {name}")
    else: fail += 1; print(f"  FAIL  {name} {extra}")

with TestClient(app):
    pass  # dispara create_all + migraciones

db = SessionLocal()
def mk_user(name, email, role):
    u = User(name=name, email=email, password_hash=hash_password("Pass123456!"), role=role)
    db.add(u); db.commit(); db.refresh(u); return u

admin = db.query(User).filter(User.role == RoleEnum.admin).first()
owner_a = mk_user("Owner A", "a@test.local", RoleEnum.owner)
owner_b = mk_user("Owner B", "b@test.local", RoleEnum.owner)
ten_a   = mk_user("Inquilino A", "ta@test.local", RoleEnum.tenant)
ten_b   = mk_user("Inquilino B", "tb@test.local", RoleEnum.tenant)

pa = Property(owner_id=owner_a.id, title="Casa A"); db.add(pa)
pb = Property(owner_id=owner_b.id, title="Casa B"); db.add(pb)
db.commit(); db.refresh(pa); db.refresh(pb)

la = Lease(property_id=pa.id, tenant_id=ten_a.id, status=LeaseStatusEnum.active)
lb = Lease(property_id=pb.id, tenant_id=ten_b.id, status=LeaseStatusEnum.active)
db.add(la); db.add(lb); db.commit(); db.refresh(la); db.refresh(lb)

ta_t = MaintenanceTicket(property_id=pa.id, reported_by_user_id=ten_a.id, title="Fuga A",
                         status=TicketStatusEnum.open)
tb_t = MaintenanceTicket(property_id=pb.id, reported_by_user_id=ten_b.id, title="Fuga B",
                         status=TicketStatusEnum.open)
db.add(ta_t); db.add(tb_t); db.commit(); db.refresh(ta_t); db.refresh(tb_t)

print("== 1. Propiedades ==")
check("owner A solo ve la suya", [p.id for p in scoped_properties(db, owner_a).all()] == [pa.id])
check("owner B solo ve la suya", [p.id for p in scoped_properties(db, owner_b).all()] == [pb.id])
check("admin ve las dos", len(scoped_properties(db, admin).all()) == 2)
check("inquilino A ve su vivienda", [p.id for p in scoped_properties(db, ten_a).all()] == [pa.id])
check("inquilino A NO ve la casa B", pb.id not in [p.id for p in scoped_properties(db, ten_a).all()])

print("\n== 2. Acceso directo por ID ajeno -> 404 (no 403) ==")
try:
    get_scoped_property_or_404(db, owner_a, pb.id); check("owner A leyendo casa B", False, "(no lanzo)")
except HTTPException as e:
    check("owner A leyendo casa B -> 404", e.status_code == 404, f"(fue {e.status_code})")
try:
    get_scoped_property_or_404(db, ten_a, pb.id); check("inquilino A leyendo casa B", False)
except HTTPException as e:
    check("inquilino A leyendo casa B -> 404", e.status_code == 404)

print("\n== 3. Manipulacion de campo oculto (DESIGN.md §11) ==")
try:
    assert_can_assign_property(db, owner_a, pb.id); check("owner A asignando a casa B", False, "(permitido!)")
except HTTPException as e:
    check("owner A NO puede asignar a casa B -> 404", e.status_code == 404)
check("owner A si puede asignar a su casa", assert_can_assign_property(db, owner_a, pa.id).id == pa.id)
check("admin puede asignar a cualquiera", assert_can_assign_property(db, admin, pb.id).id == pb.id)

print("\n== 4. Tickets ==")
check("owner A solo ve tickets de sus casas", [t.id for t in scoped_tickets(db, owner_a).all()] == [ta_t.id])
check("owner B no ve el ticket de A", ta_t.id not in [t.id for t in scoped_tickets(db, owner_b).all()])
check("inquilino A solo ve el suyo", [t.id for t in scoped_tickets(db, ten_a).all()] == [ta_t.id])
check("inquilino B no ve el de A", ta_t.id not in [t.id for t in scoped_tickets(db, ten_b).all()])
check("admin ve todos", len(scoped_tickets(db, admin).all()) == 2)

print("\n== 5. Arrendamientos ==")
check("owner A solo el de su casa", [l.id for l in scoped_leases(db, owner_a).all()] == [la.id])
check("inquilino A solo el suyo", [l.id for l in scoped_leases(db, ten_a).all()] == [la.id])
check("inquilino B no ve el de A", la.id not in [l.id for l in scoped_leases(db, ten_b).all()])

print("\n== 6. Usuarios (directorio) ==")
ids_a = [u.id for u in scoped_users(db, owner_a).all()]
check("owner A ve a su inquilino", ten_a.id in ids_a)
check("owner A NO ve al inquilino de B", ten_b.id not in ids_a)
check("owner A NO ve al owner B", owner_b.id not in ids_a)
check("owner A NO ve al admin", admin.id not in ids_a)
check("inquilino solo se ve a si mismo", [u.id for u in scoped_users(db, ten_a).all()] == [ten_a.id])
check("admin ve a todos", len(scoped_users(db, admin).all()) == 5)

print("\n== 7. owned_properties: admin tambien queda acotado ==")
check("admin por owner router no ve casas ajenas", len(owned_properties(db, admin).all()) == 0)
check("owner A ve la suya", [p.id for p in owned_properties(db, owner_a).all()] == [pa.id])

print("\n== 8. Arrendamiento terminado corta el acceso ==")
la.status = LeaseStatusEnum.ended; db.commit()
check("inquilino pierde acceso al terminar contrato",
      len(scoped_properties(db, ten_a).all()) == 0)
la.status = LeaseStatusEnum.active; db.commit()

db.close()
print(f"\n{'='*46}\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
