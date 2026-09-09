"""Pruebas E9 — cuentas como raíz de aislamiento (D-013) y matriz de planes.

Base desechable, NUNCA toca platform.db real.

Cubre tres cosas distintas:

1. **La migración**: qué cuentas crea, a quién se las asigna y qué invariantes
   deben cumplirse después. Incluye el caso que falló durante el desarrollo:
   la sesión se abre con `autoflush=False`, así que una consulta que dependa de
   escrituras pendientes ve una foto incompleta. Eso dejaba a un propietario
   sin marcar como operador y, en la base real, habría dejado una de las tres
   casas publicadas sin poder publicarse.
2. **La detección de deriva**: `PRAGMA foreign_keys` devuelve 0, así que SQLite
   no impide que una propiedad y su dueño acaben en cuentas distintas. Se
   inyecta esa deriva a propósito y se comprueba que el verificador la ve.
3. **La matriz de planes** (D-018): qué incluye cada plan y qué límite tiene.
"""
import os, sys, tempfile, pathlib

TMP = tempfile.mkdtemp(prefix="aura_cuentas_")
DB = os.path.join(TMP, "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["APP_ENV"] = "dev"
os.environ["DATA_MODE"] = "mock"
os.environ["UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["SEED_ADMIN_EMAIL"] = "admin@test.local"
os.environ["SEED_ADMIN_PASSWORD"] = "TestPass123!"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from app import migrate, plans
from app.auth import hash_password
from app.db import SessionLocal, engine
from app.main import app
from app.models import Account, Lease, LeaseStatusEnum, Property, RoleEnum, User

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  PASS  {name}")
    else: fail += 1; print(f"  FAIL  {name} {extra}")


print(f"DB de prueba: {DB}\n")

# --- Siembra ANTES del primer arranque, para que la migración tenga trabajo --
from app.db import Base
Base.metadata.create_all(bind=engine)
db = SessionLocal()
d1 = User(name="Dueño Uno", email="d1@test.local",
          password_hash=hash_password("Pass123456!"), role=RoleEnum.owner)
d2 = User(name="Dueño Dos", email="d2@test.local",
          password_hash=hash_password("Pass123456!"), role=RoleEnum.owner)
d3 = User(name="Dueño Tres", email="d3@test.local",
          password_hash=hash_password("Pass123456!"), role=RoleEnum.owner)
inq = User(name="Inquilino", email="inq@test.local",
           password_hash=hash_password("Pass123456!"), role=RoleEnum.tenant)
db.add_all([d1, d2, d3, inq]); db.commit()
ids = {"d1": d1.id, "d2": d2.id, "d3": d3.id, "inq": inq.id}

# d1 y d3 tienen casa PUBLICADA (site_ref). d3 va el último a propósito: es la
# posición en la que el fallo del flush dejaba la cuenta sin marcar.
p1 = Property(owner_id=ids["d1"], title="Casa publicada 1", site_ref="AUR-T1")
p2 = Property(owner_id=ids["d2"], title="Casa interna", site_ref=None)
p3 = Property(owner_id=ids["d3"], title="Casa publicada 2", site_ref="AUR-T2")
db.add_all([p1, p2, p3]); db.commit()
ids["p1"], ids["p2"], ids["p3"] = p1.id, p2.id, p3.id
db.add(Lease(property_id=ids["p1"], tenant_id=ids["inq"], status=LeaseStatusEnum.active))
db.commit(); db.close()

with TestClient(app):
    pass  # dispara on_startup -> migrar()

print("== 1. La migración crea las cuentas ==")
db = SessionLocal()
cuentas = db.query(Account).all()
check("hay una cuenta por propietario más la operadora", len(cuentas) == 4,
      f"-> {len(cuentas)}: {[c.name for c in cuentas]}")
operadora = db.query(Account).filter(Account.name == migrate.CUENTA_OPERADORA).first()
check("existe la cuenta operadora de Aura", operadora is not None)
admin = db.query(User).filter(User.role == RoleEnum.admin).first()
check("el administrador queda en la cuenta operadora",
      admin is not None and operadora is not None and admin.account_id == operadora.id)

print("\n== 2. Todo el mundo tiene cuenta ==")
check("ningún usuario queda sin cuenta",
      db.query(User).filter(User.account_id.is_(None)).count() == 0)
check("ninguna propiedad queda sin cuenta",
      db.query(Property).filter(Property.account_id.is_(None)).count() == 0)
derivadas = (db.query(Property.id).join(User, User.id == Property.owner_id)
             .filter(Property.account_id != User.account_id).count())
check("cada propiedad está en la cuenta de su dueño", derivadas == 0, f"-> {derivadas}")

print("\n== 3. Operador: quien tiene casa publicada (el fallo del flush) ==")
for clave, esperado in (("d1", True), ("d2", False), ("d3", True)):
    u = db.get(User, ids[clave])
    c = db.get(Account, u.account_id)
    check(f"{u.name} operadora={esperado}", c.is_operator is esperado,
          f"-> {c.is_operator}")
publicadas_mal = (db.query(Property.id).join(Account, Account.id == Property.account_id)
                  .filter(Property.site_ref.isnot(None), Account.is_operator.is_(False))
                  .count())
check("ninguna casa publicada queda en cuenta no operadora", publicadas_mal == 0,
      f"-> {publicadas_mal}")

print("\n== 4. Las cuentas migradas nacen sin plan y sin reloj (D-020) ==")
migradas = [c for c in cuentas if c.name != migrate.CUENTA_OPERADORA]
check("ninguna tiene plan asignado",
      all(c.plan_assigned_at is None for c in migradas))
check("ninguna hereda un reloj de prueba empezado",
      all(c.trial_started_at is None and c.trial_ends_at is None for c in migradas))
check("ninguna queda por debajo de su límite el primer día",
      all(plans.propiedades_max(c) is None for c in migradas),
      "-> alguna quedó con tope y ya tiene casas")
check("todas quedan activas",
      all(plans.normalizar_estado(c.status) == plans.ESTADO_ACTIVA for c in cuentas))

print("\n== 5. El inquilino hereda la cuenta del dueño de su arrendamiento ==")
u_inq = db.get(User, ids["inq"])
u_d1 = db.get(User, ids["d1"])
check("el inquilino queda en la cuenta del dueño de su casa",
      u_inq.account_id == u_d1.account_id,
      f"-> inq={u_inq.account_id} dueño={u_d1.account_id}")

print("\n== 6. Versión de esquema fijada ==")
check("schema_version = C1", migrate._schema_version(db) == migrate.SCHEMA_VERSION,
      f"-> {migrate._schema_version(db)}")
db.close()

print("\n== 7. Idempotencia: correrla otra vez no cambia nada ==")
antes = SessionLocal(); n_cuentas = antes.query(Account).count(); antes.close()
resumen = migrate.migrar(engine, SessionLocal)
check("la segunda pasada se salta el relleno", resumen["omitida"] is True)
despues = SessionLocal(); n2 = despues.query(Account).count(); despues.close()
check("no crea cuentas nuevas", n2 == n_cuentas, f"-> {n_cuentas} -> {n2}")

print("\n== 8. El verificador detecta la deriva inyectada a propósito ==")
limpio = migrate.verificar_integridad_cuentas(SessionLocal, imprimir=False)
check("con los datos sanos no reporta deriva",
      limpio["propiedades_con_cuenta_derivada"] == 0, f"-> {limpio}")
d = SessionLocal()
prop = d.get(Property, ids["p1"])
cuenta_ajena = d.query(Account).filter(Account.id != prop.account_id).first()
prop.account_id = cuenta_ajena.id   # SQLite no lo impide: foreign_keys = 0
d.commit(); d.close()
sucio = migrate.verificar_integridad_cuentas(SessionLocal, imprimir=False)
check("tras mover una propiedad a otra cuenta, la deriva se detecta",
      sucio["propiedades_con_cuenta_derivada"] == 1, f"-> {sucio}")
# se deja como estaba para no ensuciar lo que venga después
d = SessionLocal()
p = d.get(Property, ids["p1"]); u = d.get(User, p.owner_id)
p.account_id = u.account_id; d.commit(); d.close()

print("\n== 9. Matriz de planes (D-018) ==")
check("Standard admite hasta 20 casas",
      plans.PLANES[plans.PLAN_STANDARD]["propiedades_max"] == 20)
check("Enterprise no tiene tope",
      plans.PLANES[plans.PLAN_ENTERPRISE]["propiedades_max"] is None)
check("la prueba admite una sola casa (punto 7.1)",
      plans.PLANES[plans.PLAN_TRIAL]["propiedades_max"] == 1)
check("la prueba dura 90 días (D-019)", plans.TRIAL_DIAS_POR_OMISION == 90)


class _C:
    def __init__(self, plan, status=plans.ESTADO_ACTIVA, override=None):
        self.plan, self.status, self.properties_max_override = plan, status, override


check("Enterprise incluye el agente, igual que Standard+ (no pierde funciones al crecer)",
      plans.tiene_derecho(_C(plans.PLAN_ENTERPRISE), plans.AGENTE_MENSAJERIA))
check("Standard, sin el «+», no incluye el agente",
      not plans.tiene_derecho(_C(plans.PLAN_STANDARD), plans.AGENTE_MENSAJERIA))
check("la cotización automática es solo de Enterprise+",
      plans.tiene_derecho(_C(plans.PLAN_ENTERPRISE_PLUS), plans.COTIZACION_AUTOMATICA)
      and not plans.tiene_derecho(_C(plans.PLAN_ENTERPRISE), plans.COTIZACION_AUTOMATICA))
check("proveedores, gastos y exportación manual no son un derecho de pago",
      "proveedores_crud" in plans.SIEMPRE_INCLUIDO
      and "gastos_captura" in plans.SIEMPRE_INCLUIDO
      and "fiscal_export_manual" in plans.SIEMPRE_INCLUIDO)
check("entrar y recuperar la contraseña nunca se cobran",
      "acceso_y_recuperacion" in plans.SIEMPRE_INCLUIDO)

print("\n== 10. Degradación segura de valores desconocidos ==")
check("un plan desconocido degrada a prueba, no a enterprise",
      plans.normalizar_plan("plan_que_no_existe") == plans.PLAN_TRIAL)
check("un estado desconocido degrada a suspendida, no a activa",
      plans.normalizar_estado("vaya_usted_a_saber") == plans.ESTADO_SUSPENDIDA)
check("una cuenta suspendida pierde sus derechos",
      not plans.tiene_derecho(_C(plans.PLAN_ENTERPRISE_PLUS, plans.ESTADO_SUSPENDIDA),
                              plans.AGENTE_MENSAJERIA))
check("sin cuenta no hay derechos (falla cerrado)",
      not plans.tiene_derecho(None, plans.AGENTE_MENSAJERIA))
check("la excepción por cuenta manda sobre el plan",
      plans.propiedades_max(_C(plans.PLAN_TRIAL, override=7)) == 7)
derechos = plans.derechos_de(None)
check("derechos_de() devuelve todas las claves aunque no haya cuenta",
      set(derechos) == {plans.AGENTE_MENSAJERIA, plans.COTIZACION_AUTOMATICA,
                        plans.FISCAL_AUTOMATIZADO, plans.GASTOS_RECURRENTES},
      "-> Jinja lanzaría UndefinedError con una clave ausente")

print("\n== 11. La plataforma sigue sin saber de dinero (D-019) ==")
prohibidas = {"price", "amount", "precio", "importe", "monto", "clabe", "iban",
              "card", "tarjeta", "rfc", "ein", "billing", "invoice"}
cols = {c.name.lower() for c in Account.__table__.columns}
encontradas = {c for c in cols if any(p in c for p in prohibidas)}
check("la tabla de cuentas no tiene ninguna columna de dinero ni fiscal",
      not encontradas, f"-> {encontradas}")

print(f"\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
