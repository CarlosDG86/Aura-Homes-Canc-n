"""Pruebas E11 — panel del propietario, filtros y descarga de cartera.

Base desechable, NUNCA toca platform.db real.

Tres cosas que se comprueban y que no son obvias:

1. **Que exista UNA sola ruta GET /owner.** La definición vieja vivía en
   `pages.py`, que se registra antes; si hubiera quedado viva, ganaría ella y
   este módulo no se ejecutaría nunca sin que nada fallara de forma visible.
2. **Que el número de consultas no crezca con la cartera.** El panel anterior
   hidrataba todos los tickets del propietario en cada carga solo para
   contarlos.
3. **Que ningún CSV lleve datos del inquilino.** Un CSV sale de la plataforma
   y llega a un tercero que nunca aceptó el aviso de privacidad.
"""
import os, sys, re, tempfile, pathlib

TMP = tempfile.mkdtemp(prefix="aura_panel_")
DB = os.path.join(TMP, "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["APP_ENV"] = "dev"
os.environ["DATA_MODE"] = "mock"
os.environ["UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["SEED_ADMIN_EMAIL"] = "admin@test.local"
os.environ["SEED_ADMIN_PASSWORD"] = "TestPass123!"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import event

from app import filtros_owner as fo
from app.auth import hash_password
from app.db import SessionLocal, engine
from app.main import app
from app.models import (Lease, LeaseStatusEnum, MaintenanceTicket, Property,
                        PropertyStatusEnum, RoleEnum, TicketPriorityEnum,
                        TicketStatusEnum, User)

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print(f"  PASS  {name}")
    else: fail += 1; print(f"  FAIL  {name} {extra}")


def csrf(cl, ruta="/login"):
    return re.search(r'name="csrf_token" value="([^"]+)"', cl.get(ruta).text).group(1)


def entrar(cl, correo, clave="Pass123456!"):
    t = csrf(cl)
    return cl.post("/login", data={"email": correo, "password": clave, "csrf_token": t},
                   follow_redirects=False)


print(f"DB de prueba: {DB}\n")

with TestClient(app) as boot:
    d = SessionLocal()
    duenio = User(name="Dueña", email="duenia@test.local",
                  password_hash=hash_password("Pass123456!"), role=RoleEnum.owner)
    otro = User(name="Otro dueño", email="otro@test.local",
                password_hash=hash_password("Pass123456!"), role=RoleEnum.owner)
    inq1 = User(name="Inq Uno", email="i1@test.local",
                password_hash=hash_password("Pass123456!"), role=RoleEnum.tenant)
    inq2 = User(name="Inq Dos", email="i2@test.local",
                password_hash=hash_password("Pass123456!"), role=RoleEnum.tenant)
    d.add_all([duenio, otro, inq1, inq2]); d.commit()
    did, oid, i1, i2 = duenio.id, otro.id, inq1.id, inq2.id

    # Cartera pensada para ejercitar cada filtro y cada discrepancia.
    casas = [
        # ocupada y publicada como rentada -> coherente
        Property(owner_id=did, title="Casa Centro", zone="Centro", bedrooms=3,
                 area_m2=180, status=PropertyStatusEnum.rented),
        # vacía y publicada disponible -> coherente
        Property(owner_id=did, title="Depto SM 15", zone="SM 15", bedrooms=1,
                 area_m2=62, status=PropertyStatusEnum.available),
        # publicada como rentada pero SIN contrato -> discrepancia
        Property(owner_id=did, title="Casa Polígono", zone="Polígono Sur", bedrooms=4,
                 area_m2=200, status=PropertyStatusEnum.rented),
        # sin zona y sin metros -> cae en las cubetas «sin dato»
        Property(owner_id=did, title="Casa sin datos", zone=None, bedrooms=None,
                 area_m2=None, status=PropertyStatusEnum.available),
    ]
    ajena = Property(owner_id=oid, title="Casa Ajena", zone="Centro", bedrooms=2,
                     area_m2=90, status=PropertyStatusEnum.available)
    d.add_all(casas + [ajena]); d.commit()
    ids = [c.id for c in casas]; ajena_id = ajena.id

    # Un contrato vigente en la primera y otro terminado (no debe contar).
    d.add(Lease(property_id=ids[0], tenant_id=i1, status=LeaseStatusEnum.active))
    d.add(Lease(property_id=ids[1], tenant_id=i2, status=LeaseStatusEnum.ended))
    d.add(MaintenanceTicket(property_id=ids[0], reported_by_user_id=i1,
                            title="Fuga", status=TicketStatusEnum.open,
                            priority=TicketPriorityEnum.emergencia,
                            created_at=datetime.now(timezone.utc) - timedelta(days=9)))
    d.add(MaintenanceTicket(property_id=ids[1], reported_by_user_id=i2,
                            title="Resuelto", status=TicketStatusEnum.resolved))
    d.commit(); d.close()

    c = TestClient(app)
    entrar(c, "duenia@test.local")

    print("== 1. Existe UNA sola ruta GET /owner, y es la nueva ==")
    rutas = [r for r in app.routes
             if getattr(r, "path", "") == "/owner" and "GET" in getattr(r, "methods", set())]
    check("hay exactamente una", len(rutas) == 1, f"-> {len(rutas)}")
    check("y viene de owner_dashboard",
          rutas and rutas[0].endpoint.__module__.endswith("owner_dashboard"),
          f"-> {rutas[0].endpoint.__module__ if rutas else '—'}")

    print("\n== 2. Los cuatro indicadores del CEO ==")
    html = c.get("/owner").text
    check("carga el panel", "Panel" in html)
    check("Propiedades = 4", re.search(r'Propiedades</div>\s*<div class="metric-value">4<', html) is not None)
    check("Inquilinos activos = 1 (el contrato terminado no cuenta)",
          re.search(r'Inquilinos activos</div>\s*<div class="metric-value">1<', html) is not None)
    check("Reportes abiertos = 1 (el resuelto no cuenta)",
          re.search(r'Reportes abiertos</div>\s*<div class="metric-value[^"]*">1<', html) is not None)
    # 1 de 4 casas con contrato vigente = 25 %
    check("Ocupación = 25 %", re.search(r'Ocupación</div>\s*<div class="metric-value">25%<', html) is not None)
    check("cada indicador lleva su definición impresa", html.count('class="metric-def"') >= 8)

    print("\n== 3. La ocupación sale del contrato, no del sitio público ==")
    # «Casa Polígono» está publicada como rentada y NO tiene contrato: si la
    # ocupación saliera del estatus publicado, serían 2 de 4 = 50 %.
    check("no se usa el estatus publicado (sería 50 %)", "50%" not in html)
    check("la discrepancia se detecta y se ofrece aislarla",
          "/owner?ocupacion=revisar" in html)
    d = SessionLocal()
    datos = fo.componer(d, d.get(User, did), {})
    d.close()
    check("una casa marcada como revisar", datos["calidad"]["discrepancias"] == 1,
          f"-> {datos['calidad']['discrepancias']}")

    print("\n== 4. Bloque «Datos por revisar» ==")
    check("avisa del contrato sin renta capturada", "sin renta capturada" in html)
    check("avisa del contrato sin fechas", "sin fecha de inicio" in html)
    check("avisa de la casa sin zona", "sin zona" in html)
    check("avisa de la casa sin metros", "sin metros" in html)

    print("\n== 5. Filtros ==")
    def cuantas(qs=""):
        h = c.get(f"/owner{qs}").text
        cuerpo = h.split("<tbody>")[1].split("</tbody>")[0]
        return cuerpo.count("<tr")
    check("sin filtro salen las 4", cuantas() == 4, f"-> {cuantas()}")
    check("por zona Centro sale 1", cuantas("?zona=centro") == 1, f"-> {cuantas('?zona=centro')}")
    check("por zona con acento y mayúsculas funciona",
          cuantas("?zona=poligono sur") == 1, f"-> {cuantas('?zona=poligono sur')}")
    check("por recámaras=1 sale 1", cuantas("?recamaras=1") == 1)
    check("por recámaras=4mas sale 1", cuantas("?recamaras=4mas") == 1)
    check("por recámaras sin dato sale 1", cuantas("?recamaras=sin-dato") == 1)
    check("por m² hasta80 sale 1", cuantas("?m2=hasta80") == 1)
    check("por m² mas150 salen 2", cuantas("?m2=mas150") == 2)
    check("por ocupación=ocupada sale 1", cuantas("?ocupacion=ocupada") == 1)
    check("por ocupación=revisar sale 1", cuantas("?ocupacion=revisar") == 1)
    check("se combinan dos filtros", cuantas("?zona=centro&recamaras=3") == 1)
    check("una combinación sin resultados lo dice",
          "Ningún inmueble coincide" in c.get("/owner?zona=centro&recamaras=1").text)

    print("\n== 6. Un valor no reconocido se ignora y se anuncia ==")
    h = c.get("/owner?zona=inventada&recamaras=99").text
    check("no revienta", "Panel" in h)
    check("salen todas igualmente", h.split("<tbody>")[1].split("</tbody>")[0].count("<tr") == 4)
    check("y lo avisa", "no se reconoce" in h)

    print("\n== 7. La selección es efímera y no da acceso ==")
    check("seleccionar dos casas propias deja dos",
          cuantas(f"?prop={ids[0]}&prop={ids[1]}") == 2)
    h = c.get(f"/owner?prop={ajena_id}").text
    cuerpo = h.split("<tbody>")[1].split("</tbody>")[0]
    check("un id ajeno no devuelve datos ajenos", "Casa Ajena" not in h)
    check("y no revienta: 200 con lista vacía", "Ningún inmueble coincide" in h or "<tr" not in cuerpo.strip())
    check("se avisa sin confirmar si existe", "ya no están disponibles" in h)
    check("un id no numérico se descarta en silencio",
          c.get("/owner?prop=abc").status_code == 200)

    print("\n== 8. Presupuesto de consultas, constante con el tamaño ==")
    consultas = []
    def _contar(conn, cur, sentencia, params, ctx, many): consultas.append(sentencia)
    event.listen(engine, "before_cursor_execute", _contar)
    consultas.clear(); c.get("/owner"); con_4 = len(consultas)
    # Se triplica la cartera y se vuelve a medir.
    d = SessionLocal()
    for i in range(8):
        d.add(Property(owner_id=did, title=f"Extra {i}", zone="Centro",
                       bedrooms=2, area_m2=100, status=PropertyStatusEnum.available))
    d.commit(); d.close()
    consultas.clear(); c.get("/owner"); con_12 = len(consultas)
    event.remove(engine, "before_cursor_execute", _contar)
    check("el número de consultas no crece con la cartera", con_4 == con_12,
          f"-> 4 casas: {con_4} consultas; 12 casas: {con_12}")
    check("y se mantiene dentro del presupuesto (<=12 con sesión y menú)",
          con_12 <= 12, f"-> {con_12}")

    print("\n== 9. El formulario de filtros es GET y NO lleva CSRF ==")
    h = c.get("/owner").text
    formulario = h.split('<form method="get"')[1].split("</form>")[0]
    check("el formulario es GET", 'method="get"' in h)
    check("no incluye csrf_token", "csrf_token" not in formulario)
    check("«Limpiar» es un enlace, no JS", 'href="/owner"' in formulario)

    print("\n== 10. Descarga de la cartera ==")
    r = c.get("/owner?formato=csv")
    check("responde CSV", r.headers.get("content-type", "").startswith("text/csv"),
          f"-> {r.headers.get('content-type')}")
    check("se descarga como archivo", "attachment" in r.headers.get("content-disposition", ""))
    cuerpo = r.text
    check("empieza con BOM para que Excel no destroce los acentos", cuerpo.startswith("﻿"))
    check("lleva cabecera de procedencia", "Generado" in cuerpo and "Filtro" in cuerpo)
    check("y el número de casas incluidas", "Casas incluidas" in cuerpo)

    print("\n== 11. El CSV no lleva NADA del inquilino ==")
    for dato in ("Inq Uno", "i1@test.local", "Inq Dos", "i2@test.local"):
        check(f"no aparece «{dato}»", dato not in cuerpo)
    check("la ocupación es un estado, no una persona",
          "ocupada" in cuerpo and "vacante" in cuerpo)

    print("\n== 12. Una celda que Excel ejecutaría queda neutralizada ==")
    d = SessionLocal()
    d.add(Property(owner_id=did, title="=1+1", zone="Centro", bedrooms=2,
                   area_m2=100, status=PropertyStatusEnum.available))
    d.commit(); d.close()
    cuerpo2 = c.get("/owner?formato=csv").text
    check("el título con fórmula se escapa", "'=1+1" in cuerpo2, "-> Excel lo ejecutaría")
    check("la función de escape cubre los cinco prefijos",
          all(fo.escapar_csv(p + "x").startswith("'") for p in ("=", "+", "-", "@", "\t")))

    print("\n== 13. La descarga queda registrada, la lectura no ==")
    from app.models import AuditLog
    d = SessionLocal()
    n_export = d.query(AuditLog).filter(AuditLog.action == "owner.report.export").count()
    d.close()
    check("se audita cada descarga", n_export >= 2, f"-> {n_export}")
    d = SessionLocal()
    antes = d.query(AuditLog).count(); d.close()
    c.get("/owner")
    d = SessionLocal(); despues = d.query(AuditLog).count(); d.close()
    check("abrir el panel NO deja rastro (sería ruido)", antes == despues,
          f"-> {antes} -> {despues}")

    print("\n== 14. El panel no escribe nada ==")
    d = SessionLocal()
    n_props = d.query(Property).count(); n_leases = d.query(Lease).count(); d.close()
    for qs in ("", "?ocupacion=revisar", "?zona=centro", "?formato=csv", "?prop=1&prop=2"):
        c.get(f"/owner{qs}")
    d = SessionLocal()
    check("ni una propiedad creada o borrada", d.query(Property).count() == n_props)
    check("ni un contrato tocado", d.query(Lease).count() == n_leases)
    d.close()

    print("\n== 15. Un inquilino no ve el panel del propietario ==")
    ti = TestClient(app)
    entrar(ti, "i1@test.local")
    r = ti.get("/owner", follow_redirects=False)
    check("se le manda a su propio panel, no al acceso",
          r.status_code == 302 and r.headers.get("location") == "/inquilino",
          f"-> {r.status_code} {r.headers.get('location')}")

print(f"\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
