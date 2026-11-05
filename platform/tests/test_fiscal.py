"""Pruebas E13 — libro de gastos y panel fiscal.

Base desechable, NUNCA toca platform.db real.

La comprobación que más importa de todo este archivo es la de la sección 5:
**cuando falta el tipo de cambio, el importe convertido va vacío y no suma**.
Un reporte que rellena ese hueco con un cero o con una conversión inventada se
entrega sin que nadie lo revise, y el error aparece en marzo delante de un
auditor.
"""
import os, sys, re, io, tempfile, pathlib
from decimal import Decimal

TMP = tempfile.mkdtemp(prefix="aura_fiscal_")
DB = os.path.join(TMP, "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["APP_ENV"] = "dev"
os.environ["DATA_MODE"] = "mock"
os.environ["UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["SEED_ADMIN_EMAIL"] = "admin@test.local"
os.environ["SEED_ADMIN_PASSWORD"] = "TestPass123!"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from datetime import date

from fastapi.testclient import TestClient

from app import cuentas as _cuentas
from app import fiscal, fiscal_catalog
from app.auth import hash_password
from app.db import SessionLocal
from app.main import app
from app.models import (Document, Expense, FiscalYearClosure, FxRate,
                        MaintenanceTicket, Property, RoleEnum, TicketStatusEnum,
                        User)

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


ANIO = 2025
print(f"DB de prueba: {DB}\n")

with TestClient(app) as boot:
    d = SessionLocal()
    duenio = User(name="Dueña", email="duenia@test.local",
                  password_hash=hash_password("Pass123456!"), role=RoleEnum.owner)
    otro = User(name="Otro", email="otro@test.local",
                password_hash=hash_password("Pass123456!"), role=RoleEnum.owner)
    inq = User(name="Inquilino", email="inq@test.local",
               password_hash=hash_password("Pass123456!"), role=RoleEnum.tenant)
    d.add_all([duenio, otro, inq]); d.flush()
    _cuentas.asegurar_cuenta_de_usuario(d, duenio)
    _cuentas.asegurar_cuenta_de_usuario(d, otro)
    _cuentas.asegurar_cuenta_de_usuario(d, inq, creado_por=duenio)
    d.commit()
    did, oid, iid = duenio.id, otro.id, inq.id
    casa = Property(owner_id=did, account_id=duenio.account_id, title="Casa")
    ajena = Property(owner_id=oid, account_id=otro.account_id, title="Casa ajena")
    d.add_all([casa, ajena]); d.commit()
    casa_id, ajena_id = casa.id, ajena.id
    tk = MaintenanceTicket(property_id=casa_id, reported_by_user_id=iid,
                           title="Fuga", status=TicketStatusEnum.open)
    d.add(tk); d.commit(); tkid = tk.id
    d.close()

    c = TestClient(app); entrar(c, "duenia@test.local")
    ca = TestClient(app); entrar(ca, "otro@test.local")
    ci = TestClient(app); entrar(ci, "inq@test.local")

    def crear(cl=None, **extra):
        cl = cl or c
        datos = {"property_id": casa_id, "expense_date": f"{ANIO}-03-15",
                 "category_code": "mantenimiento", "amount": "1000.00",
                 "currency": "MXN", "csrf_token": csrf(cl, "/owner/gastos/nuevo")}
        datos.update(extra)
        return cl.post("/owner/gastos", data=datos, follow_redirects=False)

    print("== 1. El catálogo es puente, no dos catálogos ==")
    check("tiene 15 categorías activas", len(fiscal_catalog.activas()) == 15,
          f"-> {len(fiscal_catalog.activas())}")
    check("cada una mapea a SAT y a IRS",
          all(c_.sat_concepto or c_.irs_schedule_e
              for c_ in fiscal_catalog.activas() if c_.code != "otro"))
    check("el mapeo cambia con la jurisdicción",
          fiscal_catalog.mapeo("predial", "MX") != fiscal_catalog.mapeo("predial", "US"))
    check("una mejora capitalizable se deprecia aunque la categoría sea mantenimiento",
          fiscal_catalog.mapeo("mantenimiento", "US", is_capital=True) == "18 Depreciation")
    check("un código desconocido no rompe nada",
          fiscal_catalog.etiqueta("no_existe") == "no_existe")
    check("hay descargo legal y versión de catálogo",
          "asesoría fiscal" in fiscal_catalog.DESCARGO
          and fiscal_catalog.CATALOG_VERSION)

    print("\n== 2. Alta de gasto (punto 2.4) ==")
    r = crear()
    check("se crea y lleva al detalle", r.status_code == 302, f"-> {r.status_code}")
    d = SessionLocal()
    g = d.query(Expense).first()
    check("queda guardado", g is not None)
    check("el año fiscal se deriva de la fecha, no se pide", g.tax_year == ANIO)
    check("se sella el modo en que nació", g.data_mode == "mock")
    check("nace confirmado", g.status == fiscal.CONFIRMADO)
    gid = g.id
    d.close()

    print("\n== 3. Misma moneda: conversión directa ==")
    d = SessionLocal(); g = d.get(Expense, gid)
    check("la tasa es 1", g.fx_rate == 1)
    check("el convertido iguala al capturado", g.amount_base == g.amount)
    d.close()

    print("\n== 4. Un importe mal escrito no revienta ==")
    for malo in ("", "abc", "-50", "0"):
        r = crear(amount=malo)
        check(f"«{malo or '(vacío)'}» se rechaza con 400", r.status_code == 400,
              f"-> {r.status_code}")
    r = crear(amount="1,250.50")
    check("pero «1,250.50» sí se entiende", r.status_code == 302)

    print("\n== 5. Sin tipo de cambio NO se inventa una conversión ==")
    r = crear(currency="USD", amount="200.00")
    check("el gasto en otra moneda se crea igual", r.status_code == 302)
    d = SessionLocal()
    usd = d.query(Expense).filter(Expense.currency == "USD").first()
    check("pero el convertido queda VACÍO, no en cero", usd.amount_base is None,
          f"-> {usd.amount_base}")
    check("y sin tasa ni origen", usd.fx_rate is None and usd.fx_source is None)
    ids = [casa_id]
    tot = fiscal.totales_del_anio(d, ids, ANIO)
    check("el hueco se cuenta", tot["sin_conversion"] == 1, f"-> {tot['sin_conversion']}")
    check("y NO suma en el total", Decimal(tot["total"]) == Decimal("2250.50"),
          f"-> {tot['total']} (si sumara el USD sería distinto)")
    d.close()
    html = c.get(f"/owner/fiscal?anio={ANIO}").text
    check("el panel avisa del hueco ANTES de los totales",
          html.index("sin tipo de cambio") < html.index("Total del año"))

    print("\n== 6. Cargar la tasa completa lo que faltaba ==")
    r = c.post("/owner/fiscal/tipos-de-cambio",
               data={"currency_from": "USD", "currency_to": "MXN",
                     "rate_date": f"{ANIO}-03-01", "rate": "17.50",
                     "source": "DOF", "csrf_token": csrf(c, "/owner/fiscal/tipos-de-cambio")},
               follow_redirects=False)
    check("la tasa se guarda", r.status_code == 302, f"-> {r.status_code}")
    d = SessionLocal()
    usd = d.query(Expense).filter(Expense.currency == "USD").first()
    check("el gasto en USD ya tiene conversión", usd.amount_base is not None)
    check("con el importe correcto", Decimal(usd.amount_base) == Decimal("3500.00"),
          f"-> {usd.amount_base}")
    check("y guarda de dónde salió la tasa", usd.fx_source == "DOF")
    d.close()

    print("\n== 7. Una tasa sin origen se rechaza ==")
    r = c.post("/owner/fiscal/tipos-de-cambio",
               data={"currency_from": "USD", "currency_to": "MXN",
                     "rate_date": f"{ANIO}-04-01", "rate": "18.00", "source": "  ",
                     "csrf_token": csrf(c, "/owner/fiscal/tipos-de-cambio")},
               follow_redirects=False)
    check("sin declarar la fuente da 400", r.status_code == 400, f"-> {r.status_code}")

    print("\n== 8. No se busca una tasa del futuro ==")
    d = SessionLocal()
    t_futura = fiscal.buscar_tasa(d, duenio.account_id if False else
                                  d.get(User, did).account_id,
                                  "USD", "MXN", date(ANIO, 1, 1))
    check("para enero no sirve una tasa de marzo", t_futura is None,
          "-> usar una tasa posterior al gasto no se puede explicar")
    d.close()

    print("\n== 9. Gasto ligado a un reporte (punto 2.4) ==")
    r = c.post(f"/owner/tickets/{tkid}/gastos",
               data={"expense_date": f"{ANIO}-05-01", "category_code": "mantenimiento",
                     "amount": "800", "currency": "MXN",
                     "csrf_token": csrf(c, f"/owner/tickets/{tkid}")},
               follow_redirects=False)
    check("se crea desde el ticket", r.status_code == 302, f"-> {r.status_code}")
    d = SessionLocal()
    lig = d.query(Expense).filter(Expense.ticket_id == tkid).first()
    check("queda ligado al reporte", lig is not None)
    check("y la casa se deriva del ticket, no del formulario",
          lig.property_id == casa_id)
    d.close()

    print("\n== 10. Un ticket de otra propiedad no se puede colgar ==")
    d = SessionLocal()
    otro_tk = MaintenanceTicket(property_id=ajena_id, reported_by_user_id=iid,
                                title="Ajeno", status=TicketStatusEnum.open)
    d.add(otro_tk); d.commit(); otro_tkid = otro_tk.id; d.close()
    r = crear(ticket_id=otro_tkid)
    check("un ticket ajeno da 404", r.status_code == 404, f"-> {r.status_code}")

    print("\n== 11. Una casa ajena no existe ==")
    r = crear(property_id=ajena_id)
    check("crear un gasto en casa ajena da 404", r.status_code == 404, f"-> {r.status_code}")
    check("y no se ve su detalle",
          ca.get(f"/owner/gastos/{gid}").status_code == 404)

    print("\n== 12. El inquilino no ve ningún gasto ==")
    d = SessionLocal()
    from app.scoping import scoped_expenses
    check("su consulta de gastos sale vacía",
          scoped_expenses(d, d.get(User, iid)).count() == 0)
    d.close()
    check("y la pantalla lo manda a la suya",
          ci.get("/owner/gastos", follow_redirects=False).status_code == 302)

    print("\n== 13. No hay borrado: se anula con motivo ==")
    r = c.post(f"/owner/gastos/{gid}/actualizar",
               data={"accion": "anular", "motivo": "",
                     "csrf_token": csrf(c, f"/owner/gastos/{gid}")},
               follow_redirects=False)
    d = SessionLocal()
    check("sin motivo no se anula", d.get(Expense, gid).voided_at is None)
    d.close()
    c.post(f"/owner/gastos/{gid}/actualizar",
           data={"accion": "anular", "motivo": "Duplicado",
                 "csrf_token": csrf(c, f"/owner/gastos/{gid}")}, follow_redirects=False)
    d = SessionLocal()
    g = d.get(Expense, gid)
    check("con motivo sí se anula", g.voided_at is not None)
    check("la fila NO se borra", g is not None)
    check("y guarda por qué", g.voided_reason == "Duplicado")
    tot = fiscal.totales_del_anio(d, [casa_id], ANIO)
    check("un gasto anulado deja de sumar", tot["anulados"] == 1)
    d.close()

    print("\n== 14. Cerrar el año bloquea la escritura ==")
    r = c.post("/owner/fiscal/cierre",
               data={"accion": "cerrar", "anio": ANIO,
                     "csrf_token": csrf(c, f"/owner/fiscal?anio={ANIO}")},
               follow_redirects=False)
    check("se cierra", r.status_code == 302, f"-> {r.status_code}")
    r = crear()
    check("crear un gasto de ese año da 409", r.status_code == 409, f"-> {r.status_code}")
    r = crear(expense_date=f"{ANIO + 1}-01-10")
    check("pero otro año sigue abierto", r.status_code == 302, f"-> {r.status_code}")

    print("\n== 15. Reabrir exige motivo escrito ==")
    r = c.post("/owner/fiscal/cierre",
               data={"accion": "reabrir", "anio": ANIO, "motivo": "",
                     "csrf_token": csrf(c, f"/owner/fiscal?anio={ANIO}")},
               follow_redirects=False)
    d = SessionLocal()
    check("sin motivo no se reabre",
          d.query(FiscalYearClosure).filter(
              FiscalYearClosure.tax_year == ANIO,
              FiscalYearClosure.reopened_at.is_(None)).count() == 1)
    d.close()
    c.post("/owner/fiscal/cierre",
           data={"accion": "reabrir", "anio": ANIO, "motivo": "Faltó una factura",
                 "csrf_token": csrf(c, f"/owner/fiscal?anio={ANIO}")},
           follow_redirects=False)
    d = SessionLocal()
    fila = d.query(FiscalYearClosure).filter(FiscalYearClosure.tax_year == ANIO).first()
    check("con motivo se reabre", fila.reopened_at is not None)
    check("y el motivo queda registrado", fila.reopen_reason == "Faltó una factura")
    d.close()
    check("y se puede volver a escribir", crear().status_code == 302)

    print("\n== 16. Una tasa nueva NO toca un año cerrado ==")
    d = SessionLocal()
    cerrado = Expense(account_id=d.get(User, did).account_id, property_id=casa_id,
                      expense_date=date(2023, 6, 1), tax_year=2023,
                      category_code="predial", amount=Decimal("100"),
                      currency="USD", base_currency="MXN", data_mode="mock")
    d.add(cerrado); d.add(FiscalYearClosure(account_id=d.get(User, did).account_id,
                                            property_id=None, tax_year=2023))
    d.commit(); cid = cerrado.id
    cuenta_id = d.get(User, did).account_id
    tasa = FxRate(account_id=cuenta_id, currency_from="USD", currency_to="MXN",
                  rate_date=date(2023, 1, 1), rate=Decimal("19"), source="DOF")
    d.add(tasa); d.commit()
    fiscal.recalcular_por_tasa_nueva(d, cuenta_id, tasa)
    d.commit()
    check("el gasto de un año cerrado sigue sin conversión",
          d.get(Expense, cid).amount_base is None,
          "-> cambiarle las cifras después de cerrar anularía el cierre")
    d.close()

    print("\n== 17. El reporte CSV dice lo que falta ==")
    r = c.get(f"/owner/fiscal/reporte?anio={ANIO}")
    check("descarga CSV", r.headers.get("content-type", "").startswith("text/csv"))
    cuerpo = r.text
    check("empieza con BOM", cuerpo.startswith("﻿"))
    check("lleva el descargo legal", "asesoría fiscal" in cuerpo)
    check("lleva la versión del catálogo", fiscal_catalog.CATALOG_VERSION in cuerpo)
    check("y la jurisdicción", "Jurisdicción" in cuerpo)
    check("no lleva datos del inquilino",
          "Inquilino" not in cuerpo and "inq@test.local" not in cuerpo)

    print("\n== 18. Comprobante adjunto al gasto ==")
    d = SessionLocal()
    vivo = d.query(Expense).filter(Expense.voided_at.is_(None)).first()
    vid = vivo.id
    d.close()
    r = c.post(f"/owner/gastos/{vid}/actualizar",
               data={"accion": "adjuntar", "csrf_token": csrf(c, f"/owner/gastos/{vid}")},
               files=[("comprobante", ("factura.pdf", b"%PDF-1.4\n" + b"x" * 300,
                                       "application/pdf"))],
               follow_redirects=False)
    check("se adjunta", r.status_code == 302, f"-> {r.status_code}")
    d = SessionLocal()
    doc = d.query(Document).filter(Document.expense_id == vid).first()
    check("queda ligado al gasto", doc is not None)
    check("con su año fiscal materializado", doc and doc.fiscal_year is not None)
    docid = doc.id if doc else 0
    d.close()
    r = c.get(f"/owner/gastos/{vid}/comprobante/{docid}")
    check("se descarga como archivo",
          "attachment" in r.headers.get("content-disposition", ""))
    check("nunca inline", "inline" not in r.headers.get("content-disposition", ""))
    check("un propietario ajeno no lo descarga",
          ca.get(f"/owner/gastos/{vid}/comprobante/{docid}").status_code == 404)

    print("\n== 19. La puerta legal alcanza a la nota del gasto ==")
    r = crear(note="Llámalo al 9981234567", expense_date=f"{ANIO + 1}-02-02")
    check("un teléfono en la nota se rechaza en pruebas", r.status_code == 400,
          f"-> {r.status_code}")

    print("\n== 20. Reportes por pestañas (orden del CEO 2026-10-14) ==")
    base = c.get(f"/owner/fiscal?anio={ANIO}")
    check("el panel abre en Resumen", base.status_code == 200 and 'class="tabs"' in base.text)
    for clave, titulo in (("categorias", "Por categoría"), ("propiedades", "Por casa"),
                          ("meses", "Mes a mes")):
        r = c.get(f"/owner/fiscal?anio={ANIO}&tab={clave}")
        check(f"la pestaña «{clave}» abre y trae lo suyo",
              r.status_code == 200 and titulo in r.text, f"-> {r.status_code}")
    check("una pestaña inventada cae en Resumen, no en un error",
          c.get(f"/owner/fiscal?anio={ANIO}&tab=loquesea").status_code == 200)
    check("hay gráfica y no es JavaScript",
          "<svg" in c.get(f"/owner/fiscal?anio={ANIO}&tab=categorias").text)
    # La regla de oro del módulo, ahora en cuatro pantallas en vez de una.
    # Se fabrica el hueco a mano: a estas alturas de la suite ya hay tasas
    # para todo el par USD/MXN, así que por formulario ya no se puede crear
    # un gasto sin convertir. La fila simula lo que pasa cuando falta la tasa.
    d = SessionLocal()
    d.add(Expense(account_id=d.get(User, did).account_id, property_id=casa_id,
                  expense_date=date(ANIO, 1, 15), tax_year=ANIO,
                  category_code="mantenimiento", amount=Decimal("80"),
                  currency="USD", base_currency="MXN", data_mode="mock"))
    d.commit(); d.close()
    d = SessionLocal()
    hueco = fiscal.totales_del_anio(d, [casa_id], ANIO)["sin_conversion"]
    d.close()
    check("hay al menos un gasto sin conversión para la comprobación", hueco >= 1,
          f"-> {hueco}")
    for clave in ("resumen", "categorias", "propiedades", "meses"):
        cuerpo = c.get(f"/owner/fiscal?anio={ANIO}&tab={clave}").text
        check(f"«{clave}» avisa del hueco", "sin tipo de cambio" in cuerpo)
        if "Total del año" in cuerpo:
            check(f"«{clave}» lo avisa ANTES de la cifra",
                  cuerpo.index("sin tipo de cambio") < cuerpo.index("Total del año"))

    print("\n== 21. Los nuevos cortes suman igual que el total ==")
    d = SessionLocal()
    ids = [casa_id]
    tot = fiscal.totales_del_anio(d, ids, ANIO)
    por_prop = fiscal.totales_por_propiedad(d, ids, ANIO)
    por_mes = fiscal.totales_por_mes(d, ids, ANIO)
    d.close()
    check("por casa suma lo mismo que el total del año",
          sum((r["total"] for r in por_prop), Decimal("0")) == tot["total"],
          f"-> {sum((r['total'] for r in por_prop), Decimal('0'))} vs {tot['total']}")
    check("por mes suma lo mismo que el total del año",
          sum((m["total"] for m in por_mes), Decimal("0")) == tot["total"])
    check("salen los doce meses, también los vacíos", len(por_mes) == 12)
    check("un mes sin gastos va en cero, no desaparece",
          any(m["n"] == 0 and m["total"] == 0 for m in por_mes))

print(f"\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
