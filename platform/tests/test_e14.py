"""Pruebas E14 — paquete para el contador, cotizaciones y planes con efecto.

Base, subidas y exportaciones desechables: NUNCA toca platform.db ni data/.

Lo que más importa de este archivo, en orden:

1. **Ningún dato de contacto de un inquilino sale en el paquete.** Se busca su
   nombre, su correo y su teléfono en TODOS los archivos de texto del ZIP.
2. **Las fotos del interior no salen si nadie marcó la casilla**, y la
   pantalla intermedia no se puede saltar.
3. **Un límite de plan jamás bloquea leer, exportar ni que un inquilino
   reporte una avería.** Una fuga de agua no sabe nada de suscripciones.
"""
import hashlib
import io
import json
import os
import pathlib
import re
import sys
import tempfile
import zipfile
from datetime import date, datetime, timedelta

TMP = tempfile.mkdtemp(prefix="aura_e14_")
DB = os.path.join(TMP, "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["APP_ENV"] = "dev"
os.environ["DATA_MODE"] = "mock"
os.environ["UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["EXPORT_DIR"] = os.path.join(TMP, "exports")
os.environ["SEED_ADMIN_EMAIL"] = "admin@test.local"
os.environ["SEED_ADMIN_PASSWORD"] = "TestPass123!"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("QUOTES_AGENT_ENABLED", None)
os.environ.pop("PLAN_LIMITS_ENFORCED", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from PIL import Image

from app import cuentas as _cuentas
from app import exportacion, plans
from app.auth import hash_password
from app.db import SessionLocal
from app.main import app
from app.models import (Account, AccountPlanEvent, AiUsage, AuditLog, Expense,
                        FiscalExport, Lease, LeaseStatusEnum, MaintenanceTicket,
                        Property, Provider, RoleEnum, TicketEvent, TicketQuote,
                        TicketStatusEnum, User)

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail += 1
        print(f"  FAIL  {name} {extra}")


def csrf(cl, ruta="/login"):
    return re.search(r'name="csrf_token" value="([^"]+)"', cl.get(ruta).text).group(1)


def entrar(cl, correo, clave="Pass123456!"):
    t = csrf(cl)
    return cl.post("/login", data={"email": correo, "password": clave, "csrf_token": t},
                   follow_redirects=False)


def jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (10, 110, 113)).save(buf, format="JPEG")
    return buf.getvalue()


def auditado(accion):
    d = SessionLocal()
    try:
        return d.query(AuditLog).filter(AuditLog.action == accion).all()
    finally:
        d.close()


ANIO = 2025
NOMBRE_INQ = "Pepita Zacarías"
CORREO_INQ = "pepita@test.local"
TEL_INQ = "5550001122"

print(f"DB de prueba: {DB}\n")

with TestClient(app) as boot:
    d = SessionLocal()
    duenio = User(name="Dueña", email="duenia@test.local",
                  password_hash=hash_password("Pass123456!"), role=RoleEnum.owner)
    otro = User(name="Otro", email="otro@test.local",
                password_hash=hash_password("Pass123456!"), role=RoleEnum.owner)
    nuevo = User(name="Nuevo", email="nuevo@test.local",
                 password_hash=hash_password("Pass123456!"), role=RoleEnum.owner)
    inq = User(name=NOMBRE_INQ, email=CORREO_INQ, phone=TEL_INQ,
               password_hash=hash_password("Pass123456!"), role=RoleEnum.tenant)
    d.add_all([duenio, otro, nuevo, inq]); d.flush()
    for u in (duenio, otro, nuevo):
        _cuentas.asegurar_cuenta_de_usuario(d, u)
    _cuentas.asegurar_cuenta_de_usuario(d, inq, creado_por=duenio)
    d.flush()
    # La dueña principal tiene plan sin tope: sus pruebas no deben tropezar
    # con el límite de la prueba gratuita.
    d.get(Account, duenio.account_id).plan = plans.PLAN_STANDARD
    d.commit()
    did, oid, nid, iid = duenio.id, otro.id, nuevo.id, inq.id
    cuenta_d, cuenta_o, cuenta_n = duenio.account_id, otro.account_id, nuevo.account_id

    casa = Property(owner_id=did, account_id=cuenta_d, title="Casa Tulum")
    ajena = Property(owner_id=oid, account_id=cuenta_o, title="Casa ajena")
    d.add_all([casa, ajena]); d.commit()
    casa_id, ajena_id = casa.id, ajena.id
    contrato = Lease(property_id=casa_id, tenant_id=iid, status=LeaseStatusEnum.active,
                     start_date=date(ANIO, 1, 1))
    d.add(contrato); d.commit(); lease_id = contrato.id
    tk = MaintenanceTicket(property_id=casa_id, reported_by_user_id=iid, lease_id=lease_id,
                           title="Fuga en baño", description=f"Llamar a {TEL_INQ}",
                           status=TicketStatusEnum.open,
                           created_at=datetime(ANIO, 5, 2, 10, 0))
    tk_ajeno = MaintenanceTicket(property_id=ajena_id, reported_by_user_id=oid,
                                 title="Ajeno", status=TicketStatusEnum.open)
    d.add_all([tk, tk_ajeno]); d.commit()
    tkid, tk_ajeno_id = tk.id, tk_ajeno.id
    prov = Provider(account_id=cuenta_d, name="Plomería Sol", created_by_user_id=did)
    prov_ajeno = Provider(account_id=cuenta_o, name="Ajeno SA", created_by_user_id=oid)
    d.add_all([prov, prov_ajeno]); d.commit()
    prov_id, prov_ajeno_id = prov.id, prov_ajeno.id
    d.close()

    c = TestClient(app); entrar(c, "duenia@test.local")
    co = TestClient(app); entrar(co, "otro@test.local")
    cn = TestClient(app); entrar(cn, "nuevo@test.local")
    ci = TestClient(app); entrar(ci, CORREO_INQ)
    # El administrador entra con segundo factor: se le fija un secreto conocido
    # y se envía el código del momento, igual que haría su app.
    import pyotp
    d = SessionLocal()
    adm = d.query(User).filter(User.email == "admin@test.local").first()
    secreto = pyotp.random_base32()
    adm.totp_secret, adm.totp_enabled, adm.must_change_password = secreto, True, False
    d.commit(); d.close()
    cadm = TestClient(app); entrar(cadm, "admin@test.local", "TestPass123!")
    cadm.post("/2fa", data={"code": pyotp.TOTP(secreto).now(),
                            "csrf_token": csrf(cadm, "/2fa")}, follow_redirects=False)

    def gasto(**extra):
        datos = {"property_id": casa_id, "expense_date": f"{ANIO}-03-15",
                 "category_code": "mantenimiento", "amount": "1000.00",
                 "currency": "MXN", "csrf_token": csrf(c, "/owner/gastos/nuevo")}
        datos.update(extra)
        return c.post("/owner/gastos", data=datos, follow_redirects=False)

    # ------------------------------------------------------------------
    print("== 0. Tablas nuevas ==")
    from sqlalchemy import inspect
    from app.db import engine
    tablas = set(inspect(engine).get_table_names())
    check("existe ticket_quotes", "ticket_quotes" in tablas)
    check("existe fiscal_exports", "fiscal_exports" in tablas)

    # ------------------------------------------------------------------
    print("\n== 1. Datos del año ==")
    check("gasto en pesos", gasto(note="=HYPERLINK(\"http://x\")").status_code == 302)
    check("gasto en dólares sin tasa", gasto(currency="USD", amount="50").status_code == 302)
    check("gasto que se anulará", gasto(amount="777").status_code == 302)
    d = SessionLocal()
    anular = d.query(Expense).filter(Expense.amount == 777).first()
    anular_id = anular.id
    mxn = d.query(Expense).filter(Expense.currency == "MXN", Expense.amount == 1000).first()
    mxn_id = mxn.id
    # Una fila nacida en otro modo: no debe colarse en un paquete de pruebas.
    d.add(Expense(account_id=cuenta_d, property_id=casa_id, expense_date=date(ANIO, 6, 1),
                  tax_year=ANIO, category_code="predial", amount=999, currency="MXN",
                  base_currency="MXN", amount_base=999, fx_rate=1, data_mode="live"))
    d.commit(); d.close()
    c.post(f"/owner/gastos/{anular_id}/actualizar",
           data={"accion": "anular", "motivo": "duplicado",
                 "csrf_token": csrf(c, f"/owner/gastos/{anular_id}")}, follow_redirects=False)
    r = c.post(f"/owner/gastos/{mxn_id}/actualizar",
               data={"accion": "adjuntar", "csrf_token": csrf(c, f"/owner/gastos/{mxn_id}")},
               files=[("comprobante", ("factura.pdf", b"%PDF-1.4\n" + b"x" * 300,
                                       "application/pdf"))], follow_redirects=False)
    check("comprobante adjunto", r.status_code == 302, f"-> {r.status_code}")
    r = c.post(f"/owner/tickets/{tkid}/fotos",
               data={"fase": "work", "csrf_token": csrf(c, f"/owner/tickets/{tkid}")},
               files=[("fotos", ("trabajo.jpg", jpeg(), "image/jpeg"))], follow_redirects=False)
    check("foto del trabajo subida", r.status_code == 302, f"-> {r.status_code}")
    d = SessionLocal()
    check("el gasto quedó anulado",
          d.get(Expense, anular_id).voided_at is not None)
    d.close()

    # ------------------------------------------------------------------
    print("\n== 2. La pantalla intermedia ==")
    r = c.get(f"/owner/fiscal/exportar?anio={ANIO}")
    check("abre", r.status_code == 200, f"-> {r.status_code}")
    html = r.text
    casilla = re.search(r'<input[^>]*name="incluir_fotos"[^>]*>', html)
    check("hay casilla de fotos", casilla is not None)
    check("y nace DESMARCADA", casilla is not None and "checked" not in casilla.group(0))
    check("avisa de que muestran el interior", "interior de la vivienda" in html)
    check("avisa de datos de prueba", "DATOS-DE-PRUEBA" in html)
    check("declara el hueco de tipo de cambio", "sin tipo de cambio" in html)
    check("y las filas de otro modo", "otro modo de datos" in html)
    check("el año fiscal enlaza aquí",
          f"/owner/fiscal/exportar?anio={ANIO}" in c.get(f"/owner/fiscal?anio={ANIO}").text)

    r = c.post("/owner/fiscal/exportar",
               data={"anio": ANIO, "csrf_token": csrf(c, "/owner/fiscal/exportar")},
               follow_redirects=False)
    d = SessionLocal()
    check("sin confirmar no genera: vuelve a la pantalla intermedia",
          r.status_code == 302 and "/owner/fiscal/exportar" in r.headers["location"]
          and d.query(FiscalExport).count() == 0)
    d.close()

    # ------------------------------------------------------------------
    print("\n== 3. Generar sin fotos ==")
    r = c.post("/owner/fiscal/exportar",
               data={"anio": ANIO, "confirmado": "si",
                     "csrf_token": csrf(c, "/owner/fiscal/exportar")},
               follow_redirects=False)
    check("genera y lleva al historial",
          r.status_code == 302 and r.headers["location"] == "/owner/fiscal/exportaciones",
          f"-> {r.status_code} {r.headers.get('location')}")
    d = SessionLocal()
    fx = d.query(FiscalExport).order_by(FiscalExport.id.desc()).first()
    d.close()
    check("queda la fila", fx is not None)
    check("sin fotos", fx and fx.includes_ticket_photos is False)
    check("2 gastos: sin el anulado ni el de otro modo", fx and fx.expense_count == 2,
          f"-> {fx and fx.expense_count}")
    check("1 sin tipo de cambio", fx and fx.missing_fx_count == 1)
    check("1 excluido por modo", fx and fx.excluded_other_mode_count == 1)
    check("1 comprobante", fx and fx.receipt_count == 1)
    check("sellada en mock", fx and fx.data_mode == "mock")
    check("el ZIP vive en EXPORT_DIR, no en data/",
          fx and os.path.isfile(os.path.join(os.environ["EXPORT_DIR"], fx.stored_path)))
    check("sin restos .parcial",
          not any(n.endswith(".parcial") for _, _, fs in os.walk(os.environ["EXPORT_DIR"])
                  for n in fs))
    aud = auditado("fiscal.exportar")
    check("queda en la bitácora con fotos=no", aud and "fotos=no" in (aud[-1].meta or ""))
    check("y sin registro de fotos de interior", not auditado("fiscal.exportar_fotos_interior"))

    lista = c.get("/owner/fiscal/exportaciones")
    check("aparece en el historial",
          lista.status_code == 200 and f"/owner/fiscal/exportaciones/{fx.id}/descargar" in lista.text)

    r = c.get(f"/owner/fiscal/exportaciones/{fx.id}/descargar")
    check("se descarga", r.status_code == 200, f"-> {r.status_code}")
    check("como ZIP adjunto", r.headers.get("content-type", "").startswith("application/zip")
          and "attachment" in r.headers.get("content-disposition", ""))
    check("el nombre dice DATOS-DE-PRUEBA",
          "DATOS-DE-PRUEBA" in r.headers.get("content-disposition", ""))
    check("el hash coincide con el registrado", hashlib.sha256(r.content).hexdigest() == fx.sha256)
    check("la descarga queda auditada", bool(auditado("fiscal.export_download")))

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    nombres = set(zf.namelist())
    for esperado in ("LEEME.txt", "MANIFIESTO.json", "gastos.csv",
                     "resumen_por_categoria.csv", "tickets.csv", "SHA256SUMS.txt"):
        check(f"lleva {esperado}", esperado in nombres)
    check("lleva el comprobante original",
          any(n.startswith(f"comprobantes/{mxn_id}/") for n in nombres))
    check("NO lleva fotos", not any(n.startswith("fotos/") for n in nombres))

    textos = {n: zf.read(n).decode("utf-8", "replace") for n in nombres
              if n.endswith((".csv", ".txt", ".json"))}
    todo = "\n".join(textos.values())
    check("el nombre del inquilino no sale", NOMBRE_INQ not in todo)
    check("ni su correo", CORREO_INQ not in todo)
    check("ni su teléfono", TEL_INQ not in todo)
    check("ni la descripción que lo contenía", "Llamar a" not in todo)
    check("sale seudonimizado por contrato", f"Inquilino #{lease_id}" in textos["tickets.csv"])

    man = json.loads(textos["MANIFIESTO.json"])
    check("manifiesto: fotos_incluidas false", man["fotos_incluidas"] is False)
    check("manifiesto: huecos declarados",
          man["missing_fx_count"] == 1 and man["excluded_other_mode_count"] == 1)
    check("manifiesto: modo y catálogo", man["data_mode"] == "mock" and man["catalog_version"])
    check("LEEME marcado como prueba", "DATOS-DE-PRUEBA" in textos["LEEME.txt"])
    check("LEEME aclara que no es inmutabilidad criptográfica",
          "criptográfica" in textos["LEEME.txt"])

    filas = list(__import__("csv").reader(io.StringIO(textos["gastos.csv"].lstrip("﻿"))))
    cab = filas[0]
    usd = [f for f in filas[1:] if f[cab.index("moneda")] == "USD"]
    check("el gasto en dólares va con convertido VACÍO",
          usd and usd[0][cab.index("importe_convertido")] == "")
    check("una nota con fórmula sale neutralizada",
          any(f[cab.index("nota")].startswith("'=") for f in filas[1:]))
    check("gastos.csv lista el archivo de su comprobante",
          any(f[cab.index("archivos_comprobante")].startswith("comprobantes/") for f in filas[1:]))
    check("el resumen trae SAT e IRS lado a lado",
          "linea_schedule_e_irs" in textos["resumen_por_categoria.csv"]
          and "concepto_sat" in textos["resumen_por_categoria.csv"])

    sumas = dict((n, h) for h, n in (l.split("  ", 1) for l in textos["SHA256SUMS.txt"].splitlines()))
    check("SHA256SUMS cubre todo salvo a sí mismo", set(sumas) == nombres - {"SHA256SUMS.txt"})
    check("y cada hash es correcto",
          all(hashlib.sha256(zf.read(n)).hexdigest() == h for n, h in sumas.items()))

    # ------------------------------------------------------------------
    print("\n== 4. Generar CON fotos ==")
    r = c.post("/owner/fiscal/exportar",
               data={"anio": ANIO, "confirmado": "si", "incluir_fotos": "si",
                     "csrf_token": csrf(c, "/owner/fiscal/exportar")}, follow_redirects=False)
    d = SessionLocal()
    fx2 = d.query(FiscalExport).order_by(FiscalExport.id.desc()).first()
    d.close()
    check("genera", r.status_code == 302 and fx2.id != fx.id)
    check("la fila lo dice", fx2.includes_ticket_photos is True)
    zf2 = zipfile.ZipFile(io.BytesIO(c.get(f"/owner/fiscal/exportaciones/{fx2.id}/descargar").content))
    check("el ZIP lleva fotos/", any(n.startswith(f"fotos/{tkid}/") for n in zf2.namelist()))
    check("y queda un registro propio en la bitácora",
          bool(auditado("fiscal.exportar_fotos_interior")))

    print("\n== 5. Por propiedad y aislamiento ==")
    r = c.get(f"/owner/fiscal/exportar?anio={ANIO}&propiedad={casa_id}")
    check("se puede acotar a una casa", r.status_code == 200 and "Casa Tulum" in r.text)
    check("una casa ajena es 404",
          c.get(f"/owner/fiscal/exportar?anio={ANIO}&propiedad={ajena_id}").status_code == 404)
    r = c.post("/owner/fiscal/exportar",
               data={"anio": ANIO, "propiedad": ajena_id, "confirmado": "si",
                     "csrf_token": csrf(c, "/owner/fiscal/exportar")}, follow_redirects=False)
    check("y generar sobre ella también", r.status_code == 404, f"-> {r.status_code}")
    check("otro propietario no descarga el paquete: 404",
          co.get(f"/owner/fiscal/exportaciones/{fx.id}/descargar").status_code == 404)
    check("ni lo ve en su historial",
          f"/exportaciones/{fx.id}/" not in co.get("/owner/fiscal/exportaciones").text)
    r = ci.get("/owner/fiscal/exportaciones", follow_redirects=False)
    check("el inquilino no entra", r.status_code in (302, 303, 403, 404), f"-> {r.status_code}")
    check("ni descarga", ci.get(f"/owner/fiscal/exportaciones/{fx.id}/descargar",
                                follow_redirects=False).status_code != 200)

    print("\n== 6. Tope de tamaño ==")
    tope = exportacion.MAX_BYTES
    exportacion.MAX_BYTES = 10
    d = SessionLocal(); antes = d.query(FiscalExport).count(); d.close()
    r = c.post("/owner/fiscal/exportar",
               data={"anio": ANIO, "confirmado": "si",
                     "csrf_token": csrf(c, "/owner/fiscal/exportar")}, follow_redirects=False)
    exportacion.MAX_BYTES = tope
    d = SessionLocal(); despues = d.query(FiscalExport).count(); d.close()
    check("se rechaza sin generar", r.status_code == 302 and antes == despues)
    check("y lo explica en pantalla", "propiedad por propiedad" in c.get("/owner/fiscal/exportar").text)

    # ------------------------------------------------------------------
    print("\n== 7. Cotizaciones manuales ==")
    ruta_c = f"/owner/tickets/{tkid}/cotizaciones"
    r = c.post(ruta_c, data={"accion": "registrar", "proveedor_id": prov_id, "monto": "4200",
                             "moneda": "MXN", "alcance": "Material y mano de obra",
                             "csrf_token": csrf(c, f"/owner/tickets/{tkid}")},
               follow_redirects=False)
    check("se registra con proveedor del directorio", r.status_code == 302, f"-> {r.status_code}")
    r = c.post(ruta_c, data={"accion": "registrar", "proveedor_nombre": "Don Chuy",
                             "monto": "3900", "csrf_token": csrf(c, f"/owner/tickets/{tkid}")},
               follow_redirects=False)
    check("y con un nombre libre", r.status_code == 302)
    r = c.post(ruta_c, data={"accion": "registrar", "proveedor_nombre": "X", "monto": "abc",
                             "csrf_token": csrf(c, f"/owner/tickets/{tkid}")},
               follow_redirects=False)
    check("un importe malo vuelve a la ficha, no a un JSON", r.status_code == 302)
    r = c.post(ruta_c, data={"accion": "registrar", "proveedor_id": prov_ajeno_id, "monto": "1",
                             "csrf_token": csrf(c, f"/owner/tickets/{tkid}")},
               follow_redirects=False)
    check("un proveedor de otra cuenta es 404", r.status_code == 404, f"-> {r.status_code}")
    d = SessionLocal()
    qs = d.query(TicketQuote).filter(TicketQuote.ticket_id == tkid).order_by(TicketQuote.id).all()
    check("quedan exactamente 2", len(qs) == 2, f"-> {len(qs)}")
    check("nacen registradas y manuales",
          all(q.status == "registrada" and q.source == "manual" for q in qs))
    check("con la cuenta del servidor", all(q.account_id == cuenta_d for q in qs))
    q1, q2 = qs[0].id, qs[1].id
    d.close()

    html = c.get(f"/owner/tickets/{tkid}").text
    check("la ficha muestra la sección", 'id="cotizaciones"' in html and "Plomería Sol" in html)
    check("sin botón automático en un plan sin el derecho",
          "cotizaciones/solicitar" not in html)

    r = c.post(ruta_c, data={"accion": "aprobar", "cotizacion_id": q1,
                             "csrf_token": csrf(c, f"/owner/tickets/{tkid}")}, follow_redirects=False)
    d = SessionLocal()
    t_ = d.get(MaintenanceTicket, tkid)
    check("aprobar sella el estado", d.get(TicketQuote, q1).status == "aprobada")
    check("con quién y cuándo", d.get(TicketQuote, q1).decided_by_user_id == did
          and d.get(TicketQuote, q1).decided_at is not None)
    check("deja constancia en el historial",
          d.query(TicketEvent).filter(TicketEvent.ticket_id == tkid,
                                      TicketEvent.body.like("Cotización aprobada%")).count() == 1)
    check("NO cambia el estado del ticket (D-017 omitida)", t_.status == TicketStatusEnum.open)
    check("NO asigna proveedor", t_.provider_id is None)
    d.close()
    c.post(ruta_c, data={"accion": "aprobar", "cotizacion_id": q2,
                         "csrf_token": csrf(c, f"/owner/tickets/{tkid}")}, follow_redirects=False)
    d = SessionLocal()
    check("no se aprueban dos a la vez", d.get(TicketQuote, q2).status == "registrada")
    d.close()
    c.post(ruta_c, data={"accion": "rechazar", "cotizacion_id": q2,
                         "csrf_token": csrf(c, f"/owner/tickets/{tkid}")}, follow_redirects=False)
    d = SessionLocal()
    check("rechazar sella el estado", d.get(TicketQuote, q2).status == "rechazada")
    d.close()
    r = co.post(ruta_c, data={"accion": "aprobar", "cotizacion_id": q2,
                              "csrf_token": csrf(co, "/owner/proveedores")}, follow_redirects=False)
    check("otro propietario sobre este ticket: 404", r.status_code == 404, f"-> {r.status_code}")
    r = c.post(f"/owner/tickets/{tk_ajeno_id}/cotizaciones",
               data={"accion": "aprobar", "cotizacion_id": q1,
                     "csrf_token": csrf(c, f"/owner/tickets/{tkid}")}, follow_redirects=False)
    check("una cotización colgada de un ticket ajeno: 404", r.status_code == 404)

    print("\n== 8. Cotización automática: cuatro cerrojos, cero llamadas ==")
    sol = f"/owner/tickets/{tkid}/cotizaciones/solicitar"
    r = c.post(sol, data={"csrf_token": csrf(c, f"/owner/tickets/{tkid}")}, follow_redirects=False)
    check("sin el plan: 403", r.status_code == 403, f"-> {r.status_code}")
    check("con pantalla explicativa, no JSON", "Enterprise +" in r.text and "<html" in r.text)
    r = co.post(sol, data={"csrf_token": csrf(co, "/owner/proveedores")}, follow_redirects=False)
    check("el aislamiento va antes que el plan: ticket ajeno es 404", r.status_code == 404)
    d = SessionLocal(); d.get(Account, cuenta_d).plan = plans.PLAN_ENTERPRISE_PLUS; d.commit(); d.close()
    check("con el plan la ficha pinta el botón", "cotizaciones/solicitar" in c.get(f"/owner/tickets/{tkid}").text)
    r = c.post(sol, data={"csrf_token": csrf(c, f"/owner/tickets/{tkid}")}, follow_redirects=False)
    check("con el plan y las banderas apagadas: 501", r.status_code == 501, f"-> {r.status_code}")
    os.environ["QUOTES_AGENT_ENABLED"] = "true"
    os.environ["ANTHROPIC_API_KEY"] = "sk-falsa"
    r = c.post(sol, data={"csrf_token": csrf(c, f"/owner/tickets/{tkid}")}, follow_redirects=False)
    check("con bandera y llave, pero en mock: sigue 501", r.status_code == 501)
    os.environ.pop("QUOTES_AGENT_ENABLED"); os.environ.pop("ANTHROPIC_API_KEY")
    d = SessionLocal()
    check("no escribió AiUsage", d.query(AiUsage).count() == 0)
    check("ni cotizaciones", d.query(TicketQuote).count() == 2)
    d.get(Account, cuenta_d).plan = plans.PLAN_STANDARD; d.commit(); d.close()

    # ------------------------------------------------------------------
    print("\n== 9. Límite de casas: se aplica al CREAR ==")
    tok_n = csrf(cn, "/owner/proveedores")
    r = cn.post("/api/owner/properties", json={"title": "Primera"},
                headers={"x-csrf-token": tok_n})
    check("la prueba admite la primera casa", r.status_code == 201, f"-> {r.status_code} {r.text[:120]}")
    d = SessionLocal(); cta = d.get(Account, cuenta_n)
    check("y arranca el reloj de 90 días",
          cta.trial_started_at is not None and cta.trial_ends_at is not None
          and 89 <= (cta.trial_ends_at - cta.trial_started_at).days <= 90)
    check("atado a esa casa", cta.trial_property_id is not None)
    fin_original = cta.trial_ends_at
    d.close()
    r = cn.post("/api/owner/properties", json={"title": "Segunda"},
                headers={"x-csrf-token": tok_n})
    check("la segunda se rechaza con 409", r.status_code == 409, f"-> {r.status_code}")
    check("explicando el límite", "permite 1" in r.text)
    d = SessionLocal()
    check("no se creó", d.query(Property).filter(Property.account_id == cuenta_n).count() == 1)
    check("y el reloj no se movió", d.get(Account, cuenta_n).trial_ends_at == fin_original)
    d.close()

    tok_a = csrf(cadm, "/admin/cuentas")
    r = cadm.post("/api/admin/properties", json={"title": "Por admin", "owner_id": nid},
                  headers={"x-csrf-token": tok_a})
    check("el admin tampoco la salta: 409 sobre la cuenta del dueño", r.status_code == 409,
          f"-> {r.status_code}")

    os.environ["PLAN_LIMITS_ENFORCED"] = "false"
    r = cn.post("/api/owner/properties", json={"title": "Con interruptor"},
                headers={"x-csrf-token": tok_n})
    os.environ.pop("PLAN_LIMITS_ENFORCED")
    check("con PLAN_LIMITS_ENFORCED=false pasa", r.status_code == 201, f"-> {r.status_code}")
    check("pero deja rastro en la bitácora", bool(auditado("plan.limite_omitido")))

    r = cn.get("/owner", follow_redirects=False)
    check("estar por encima del límite no oculta nada: el panel abre", r.status_code == 200)
    d = SessionLocal()
    check("y no se borró ninguna casa",
          d.query(Property).filter(Property.account_id == cuenta_n).count() == 2)
    d.close()

    print("\n== 10. «Mi cuenta» ==")
    r = cn.get("/owner/cuenta")
    check("abre", r.status_code == 200, f"-> {r.status_code}")
    check("dice el plan y el uso", "Prueba" in r.text and "2 / 1" in r.text)
    check("explica que nada se borra", "Nada se borra" in r.text)
    check("sin precios", "$" not in r.text and "MXN" not in r.text)
    check("el menú la enlaza", 'href="/owner/cuenta"' in r.text)

    print("\n== 11. Día 91: se detiene crecer, no vivir ==")
    d = SessionLocal()
    d.get(Account, cuenta_d).plan = plans.PLAN_TRIAL
    d.get(Account, cuenta_d).trial_started_at = datetime(2020, 1, 1)
    d.get(Account, cuenta_d).trial_ends_at = datetime(2020, 4, 1)
    d.commit(); d.close()
    r = gasto(amount="10")
    check("crear un gasto: 403", r.status_code == 403, f"-> {r.status_code}")
    r = c.post("/owner/proveedores", data={"accion": "crear", "name": "Nuevo",
                                           "csrf_token": csrf(c, "/owner/proveedores")},
               follow_redirects=False)
    check("crear un proveedor: 403", r.status_code == 403, f"-> {r.status_code}")
    r = c.post("/owner/inquilinos", data={"name": "X", "email": "x@test.local",
                                          "property_id": casa_id,
                                          "csrf_token": csrf(c, "/owner/inquilinos")},
               follow_redirects=False)
    check("dar de alta un inquilino: 403", r.status_code == 403, f"-> {r.status_code}")
    r = c.post(ruta_c, data={"accion": "registrar", "proveedor_nombre": "Y", "monto": "5",
                             "csrf_token": csrf(c, f"/owner/tickets/{tkid}")},
               follow_redirects=False)
    check("registrar una cotización: 403", r.status_code == 403, f"-> {r.status_code}")
    check("leer gastos sigue", c.get("/owner/gastos").status_code == 200)
    check("la ficha del ticket sigue", c.get(f"/owner/tickets/{tkid}").status_code == 200)
    check("la descarga del paquete sigue",
          c.get(f"/owner/fiscal/exportaciones/{fx.id}/descargar").status_code == 200)
    r = c.post("/owner/fiscal/exportar",
               data={"anio": ANIO, "confirmado": "si",
                     "csrf_token": csrf(c, "/owner/fiscal/exportar")}, follow_redirects=False)
    check("y generar uno nuevo también", r.status_code == 302
          and r.headers["location"] == "/owner/fiscal/exportaciones")
    r = ci.post("/inquilino/tickets/nuevo",
                data={"title": "Se fue la luz", "description": "En la cocina",
                      "csrf_token": csrf(ci, "/inquilino/tickets/nuevo")},
                follow_redirects=False)
    d = SessionLocal()
    check("EL INQUILINO PUEDE REPORTAR UNA AVERÍA",
          r.status_code in (200, 302, 303)
          and d.query(MaintenanceTicket).filter(MaintenanceTicket.title == "Se fue la luz").count() == 1,
          f"-> {r.status_code}")
    d.close()
    r = c.post(f"/owner/tickets/{tkid}/actualizar",
               data={"accion": "resolver", "body": "Listo",
                     "csrf_token": csrf(c, f"/owner/tickets/{tkid}")}, follow_redirects=False)
    d = SessionLocal()
    check("y el propietario puede resolverla",
          d.get(MaintenanceTicket, tkid).status == TicketStatusEnum.resolved)
    d.close()
    check("«Mi cuenta» explica por qué", "prueba de 90 días terminó" in c.get("/owner/cuenta").text)

    print("\n== 12. Cuenta suspendida ==")
    d = SessionLocal()
    a = d.get(Account, cuenta_d)
    a.plan, a.status, a.trial_ends_at = plans.PLAN_STANDARD, plans.ESTADO_SUSPENDIDA, None
    d.commit(); d.close()
    check("no crea gastos", gasto(amount="11").status_code == 403)
    check("pero exporta", c.get(f"/owner/fiscal/exportar?anio={ANIO}").status_code == 200)

    # ------------------------------------------------------------------
    print("\n== 13. Asignación de plan (admin) ==")
    check("un propietario no entra al directorio",
          c.get("/admin/cuentas", follow_redirects=False).status_code in (302, 303))
    r = cadm.get("/admin/cuentas")
    check("el admin sí", r.status_code == 200 and "Nuevo" in r.text)
    check("marca las cuentas sin plan asignado", "plan sin asignar" in r.text)
    tok = csrf(cadm, "/admin/cuentas")
    r = cadm.post(f"/admin/cuentas/{cuenta_n}/plan",
                  data={"plan": "standard", "estado": "activa", "nota": "", "csrf_token": tok},
                  follow_redirects=False)
    d = SessionLocal()
    check("sin nota no cambia nada", d.get(Account, cuenta_n).plan == plans.PLAN_TRIAL)
    d.close()
    r = cadm.post(f"/admin/cuentas/{cuenta_n}/plan",
                  data={"plan": "trial", "estado": "activa", "extender_dias": "500",
                        "nota": "prueba", "csrf_token": tok}, follow_redirects=False)
    d = SessionLocal()
    check("una prueba no pasa de 180 días", d.get(Account, cuenta_n).trial_ends_at == fin_original)
    d.close()
    r = cadm.post(f"/admin/cuentas/{cuenta_n}/plan",
                  data={"plan": "standard", "estado": "activa", "nota": "Contrato 2026-014",
                        "csrf_token": tok}, follow_redirects=False)
    d = SessionLocal()
    a = d.get(Account, cuenta_n)
    check("con nota cambia el plan", a.plan == plans.PLAN_STANDARD)
    check("y lo deja asignado", a.plan_assigned_at is not None and a.plan_note == "Contrato 2026-014")
    ev = d.query(AccountPlanEvent).filter(AccountPlanEvent.account_id == cuenta_n).all()
    check("con su evento en el historial", len(ev) == 1 and ev[0].from_plan == "trial"
          and ev[0].to_plan == "standard")
    d.close()
    check("y en la bitácora", bool(auditado("cuenta.plan_cambiado")))
    r = cn.post("/api/owner/properties", json={"title": "Tercera"},
                headers={"x-csrf-token": csrf(cn, "/owner/proveedores")})
    check("ahora puede crecer", r.status_code == 201, f"-> {r.status_code}")
    r = co.post(f"/admin/cuentas/{cuenta_o}/plan",
                data={"plan": "enterprise_plus", "estado": "activa", "nota": "yo mismo",
                      "csrf_token": csrf(co, "/owner/proveedores")}, follow_redirects=False)
    d = SessionLocal()
    check("un propietario no se sube de plan solo", d.get(Account, cuenta_o).plan == plans.PLAN_TRIAL)
    d.close()

    print("\n== 14. Retencion de paquetes: se borran bytes, nunca el registro ==")
    d = SessionLocal()
    a = d.get(Account, cuenta_d)
    a.plan, a.status, a.trial_ends_at = plans.PLAN_STANDARD, plans.ESTADO_ACTIVA, None
    d.commit()
    previos = (d.query(FiscalExport)
               .filter(FiscalExport.account_id == cuenta_d, FiscalExport.tax_year == ANIO)
               .order_by(FiscalExport.id).all())
    ids_previos = [f.id for f in previos]
    rutas_previas = {f.id: f.stored_path for f in previos}
    d.close()
    check("ya hay varios paquetes del mismo anio", len(ids_previos) >= 3,
          f"-> {len(ids_previos)}")

    r = c.post("/owner/fiscal/exportar",
               data={"anio": ANIO, "confirmado": "si",
                     "csrf_token": csrf(c, "/owner/fiscal/exportar")}, follow_redirects=False)
    check("genera uno nuevo", r.status_code == 302, f"-> {r.status_code}")
    d = SessionLocal()
    todos = (d.query(FiscalExport)
             .filter(FiscalExport.account_id == cuenta_d, FiscalExport.tax_year == ANIO)
             .order_by(FiscalExport.id).all())
    nuevo_id = todos[-1].id
    d.close()
    base_exp = os.environ["EXPORT_DIR"]
    vivos = [f.id for f in todos if os.path.isfile(os.path.join(base_exp, f.stored_path))]
    check("solo quedan 2 archivos de ese anio", len(vivos) == 2, f"-> {len(vivos)}")
    check("y son los dos mas recientes", nuevo_id in vivos and max(ids_previos) in vivos)
    check("NINGUNA fila se borro", len(todos) == len(ids_previos) + 1,
          f"-> {len(todos)} vs {len(ids_previos) + 1}")
    viejo = ids_previos[0]
    check("el archivo del mas viejo desaparecio",
          not os.path.isfile(os.path.join(base_exp, rutas_previas[viejo])))
    d = SessionLocal()
    fila_vieja = d.get(FiscalExport, viejo)
    check("pero su registro conserva lo que llevaba dentro",
          fila_vieja is not None and fila_vieja.expense_count is not None
          and fila_vieja.sha256)
    d.close()
    lista = c.get("/owner/fiscal/exportaciones").text
    check("la lista lo muestra como archivo retirado", "archivo retirado" in lista)
    check("y ya no ofrece descargarlo",
          f"/owner/fiscal/exportaciones/{viejo}/descargar" not in lista)
    r = c.get(f"/owner/fiscal/exportaciones/{viejo}/descargar")
    check("pedirlo a mano da 404, no un archivo roto", r.status_code == 404,
          f"-> {r.status_code}")
    check("la purga queda en la bitacora", bool(auditado("fiscal.export_purgado")))
    r = c.get(f"/owner/fiscal/exportaciones/{nuevo_id}/descargar")
    check("el paquete nuevo sigue descargandose", r.status_code == 200, f"-> {r.status_code}")

print(f"\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
