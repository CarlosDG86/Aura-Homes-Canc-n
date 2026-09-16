"""Pruebas E12 — proveedores, comprobantes y cámara en móvil.

Base desechable, NUNCA toca platform.db real.

Lo que más se comprueba aquí no es que las cosas funcionen, sino que **no se
salgan de su sitio**: que un proveedor de otra cuenta no exista, que un
inquilino no pueda ver una factura, que un archivo disfrazado no entre, y que
nada se sirva de forma que el navegador quiera interpretarlo.
"""
import os, sys, re, io, tempfile, pathlib

TMP = tempfile.mkdtemp(prefix="aura_prov_")
DB = os.path.join(TMP, "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["APP_ENV"] = "dev"
os.environ["DATA_MODE"] = "mock"
os.environ["UPLOAD_DIR"] = os.path.join(TMP, "uploads")
os.environ["SEED_ADMIN_EMAIL"] = "admin@test.local"
os.environ["SEED_ADMIN_PASSWORD"] = "TestPass123!"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from PIL import Image

from app import docstore
from app.auth import hash_password
from app.db import SessionLocal
from app.main import app
from app.models import (Account, Document, MaintenanceTicket, Property, Provider,
                        RoleEnum, TicketPhoto, TicketStatusEnum, User)

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


def jpeg(px=40) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (px, px), (10, 110, 113)).save(buf, format="JPEG")
    return buf.getvalue()


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
    # Se siembra directo, sin pasar por las rutas, así que hay que darles
    # cuenta con la misma función que usa el alta real. Sin cuenta, el
    # aislamiento por cuenta responde 503 — que es justo lo que debe hacer.
    from app import cuentas as _cuentas
    _cuentas.asegurar_cuenta_de_usuario(d, duenio)
    _cuentas.asegurar_cuenta_de_usuario(d, otro)
    _cuentas.asegurar_cuenta_de_usuario(d, inq, creado_por=duenio)
    d.commit()
    did, oid, iid = duenio.id, otro.id, inq.id
    casa = Property(owner_id=did, title="Casa", city="Cancún")
    casa2 = Property(owner_id=oid, title="Casa ajena", city="Cancún")
    d.add_all([casa, casa2]); d.commit()
    tk = MaintenanceTicket(property_id=casa.id, reported_by_user_id=iid,
                           title="Fuga", status=TicketStatusEnum.open)
    d.add(tk); d.commit(); tkid = tk.id
    d.close()

    # La migración de cuentas corre al arrancar, así que ambos dueños ya tienen
    # cuenta propia. Es el requisito de `scoped_providers`.
    c = TestClient(app); entrar(c, "duenia@test.local")
    ca = TestClient(app); entrar(ca, "otro@test.local")
    ci = TestClient(app); entrar(ci, "inq@test.local")

    def crear_proveedor(cl, nombre, **extra):
        datos = {"accion": "crear", "name": nombre,
                 "csrf_token": csrf(cl, "/owner/proveedores")}
        datos.update(extra)
        return cl.post("/owner/proveedores", data=datos, follow_redirects=False)

    print("== 1. Alta de proveedor (punto 5) ==")
    r = crear_proveedor(c, "Plomería del Caribe", trade="plomeria")
    check("se crea y redirige", r.status_code == 302, f"-> {r.status_code}")
    d = SessionLocal()
    p = d.query(Provider).filter(Provider.name == "Plomería del Caribe").first()
    check("queda guardado", p is not None)
    check("con la cuenta del servidor, no del formulario",
          p.account_id == d.get(User, did).account_id)
    check("y activo", p.is_active is True)
    pid = p.id
    d.close()
    check("aparece en el directorio", "Plomería del Caribe" in c.get("/owner/proveedores").text)

    print("\n== 2. No es un usuario, es un dato de la cuenta ==")
    d = SessionLocal()
    check("no se creó ninguna fila en users",
          d.query(User).filter(User.name == "Plomería del Caribe").count() == 0)
    d.close()

    print("\n== 3. La puerta legal D-016 se aplica campo por campo ==")
    r = crear_proveedor(c, "Con correo real", email="plomero@gmail.com")
    check("un correo real se rechaza en pruebas", r.status_code == 400, f"-> {r.status_code}")
    r = crear_proveedor(c, "Con teléfono real", phone="+52 998 123 4567")
    check("un teléfono real se rechaza", r.status_code == 400, f"-> {r.status_code}")
    r = crear_proveedor(c, "Con RFC", tax_id="XAXX010101000")
    check("el RFC no se captura en pruebas", r.status_code == 400, f"-> {r.status_code}")
    # El agujero que el guard de texto libre viene a tapar.
    r = crear_proveedor(c, "Con nota", notes="Llámalo al 9981234567 y verás")
    check("un teléfono escondido en la nota también se rechaza",
          r.status_code == 400, f"-> {r.status_code}")
    r = crear_proveedor(c, "Con nota 2", notes="Escríbele a juan@gmail.com")
    check("un correo escondido en la nota también", r.status_code == 400)
    # Y el fallo que haría imposible dar de alta a nadie.
    r = crear_proveedor(c, "Sin correo ni teléfono")
    check("pero SIN correo sí se puede dar de alta", r.status_code == 302,
          f"-> {r.status_code} (validate_mock_email('') lanza 400)")

    print("\n== 4. Un proveedor ajeno no existe ==")
    r = ca.post("/owner/proveedores",
                data={"accion": "archivar", "proveedor_id": pid,
                      "csrf_token": csrf(ca, "/owner/proveedores")},
                follow_redirects=False)
    check("tocar uno ajeno da 404, no 403", r.status_code == 404, f"-> {r.status_code}")
    check("y no aparece en su directorio",
          "Plomería del Caribe" not in ca.get("/owner/proveedores").text)

    print("\n== 5. Archivar lo saca de los selectores, no del historial ==")
    c.post("/owner/proveedores", data={"accion": "archivar", "proveedor_id": pid,
                                       "csrf_token": csrf(c, "/owner/proveedores")},
           follow_redirects=False)
    # Se mira SOLO la tabla: el nombre aparece también en el aviso de que se
    # archivó, y eso no significa que siga en el directorio.
    tabla = c.get("/owner/proveedores").text.split("<tbody>")[1].split("</tbody>")[0]
    check("archivado no sale en la lista por omisión",
          "Plomería del Caribe" not in tabla)
    check("pero sí al pedir los archivados",
          "Plomería del Caribe" in c.get("/owner/proveedores?archivados=1").text)
    c.post("/owner/proveedores", data={"accion": "restaurar", "proveedor_id": pid,
                                       "csrf_token": csrf(c, "/owner/proveedores")},
           follow_redirects=False)

    print("\n== 6. Asignar proveedor a un ticket ==")
    r = c.post(f"/owner/tickets/{tkid}/actualizar",
               data={"accion": "asignar_proveedor", "proveedor_id": pid,
                     "csrf_token": csrf(c, f"/owner/tickets/{tkid}")},
               follow_redirects=False)
    check("se asigna", r.status_code == 302, f"-> {r.status_code}")
    d = SessionLocal()
    check("queda en el ticket", d.get(MaintenanceTicket, tkid).provider_id == pid)
    d.close()
    r = c.post(f"/owner/tickets/{tkid}/actualizar",
               data={"accion": "asignar_proveedor", "proveedor_id": 99999,
                     "csrf_token": csrf(c, f"/owner/tickets/{tkid}")},
               follow_redirects=False)
    check("un proveedor inexistente da 404", r.status_code == 404, f"-> {r.status_code}")

    print("\n== 7. Eliminar: borra si puede, archiva si no ==")
    d = SessionLocal()
    suelto = Provider(account_id=d.get(User, did).account_id, name="Sin referencias")
    d.add(suelto); d.commit(); sid = suelto.id; d.close()
    c.post("/owner/proveedores", data={"accion": "eliminar", "proveedor_id": sid,
                                       "csrf_token": csrf(c, "/owner/proveedores")},
           follow_redirects=False)
    d = SessionLocal()
    check("sin referencias se borra de verdad", d.get(Provider, sid) is None)
    d.close()
    # El de arriba SÍ está en un ticket.
    c.post("/owner/proveedores", data={"accion": "eliminar", "proveedor_id": pid,
                                       "csrf_token": csrf(c, "/owner/proveedores")},
           follow_redirects=False)
    d = SessionLocal()
    p = d.get(Provider, pid)
    check("con referencias NO se borra", p is not None)
    check("se archiva en su lugar", p is not None and p.is_active is False)
    d.close()
    check("y se explica por qué", "se archivó en vez de borrarse" in
          c.get("/owner/proveedores?archivados=1").text)

    print("\n== 8. Borrar contacto conserva el nombre ==")
    d = SessionLocal()
    pr = Provider(account_id=d.get(User, did).account_id, name="Electricista",
                  phone="+52 555 0111 2222", contact_name="Luis")
    d.add(pr); d.commit(); prid = pr.id; d.close()
    c.post("/owner/proveedores", data={"accion": "redactar", "proveedor_id": prid,
                                       "csrf_token": csrf(c, "/owner/proveedores")},
           follow_redirects=False)
    d = SessionLocal()
    pr = d.get(Provider, prid)
    check("el contacto desaparece", pr.phone is None and pr.contact_name is None)
    check("el nombre se conserva", pr.name == "Electricista")
    check("y queda sellado cuándo", pr.redacted_at is not None)
    d.close()

    print("\n== 9. Fotos del propietario (puntos 6.1 y 6.2) ==")
    r = c.post(f"/owner/tickets/{tkid}/fotos",
               data={"fase": "closing", "csrf_token": csrf(c, f"/owner/tickets/{tkid}")},
               files=[("fotos", ("cierre.jpg", jpeg(), "image/jpeg"))],
               follow_redirects=False)
    check("se sube una foto de cierre", r.status_code == 302, f"-> {r.status_code}")
    d = SessionLocal()
    fp = d.query(TicketPhoto).filter(TicketPhoto.ticket_id == tkid,
                                     TicketPhoto.phase == "closing").all()
    check("queda marcada con su fase", len(fp) == 1)
    check("y con el EXIF destruido", fp and fp[0].exif_stripped is True)
    d.close()
    html = c.get(f"/owner/tickets/{tkid}").text
    check("el formulario abre la cámara del móvil", 'capture="environment"' in html)
    check("y no usa JavaScript para ello", "getUserMedia" not in html)

    print("\n== 10. Se puede adjuntar DESPUÉS de resolver ==")
    c.post(f"/owner/tickets/{tkid}/actualizar",
           data={"accion": "resolver", "body": "Se cambió el empaque",
                 "csrf_token": csrf(c, f"/owner/tickets/{tkid}")}, follow_redirects=False)
    r = c.post(f"/owner/tickets/{tkid}/fotos",
               data={"fase": "closing", "csrf_token": csrf(c, f"/owner/tickets/{tkid}")},
               files=[("fotos", ("despues.jpg", jpeg(), "image/jpeg"))],
               follow_redirects=False)
    check("con el ticket resuelto sigue aceptando fotos", r.status_code == 302,
          f"-> {r.status_code}")

    print("\n== 11. Comprobantes: solo lo que se puede comprobar ==")
    def subir_doc(cl, nombre, contenido, tipo="invoice"):
        return cl.post(f"/owner/tickets/{tkid}/documentos",
                       data={"tipo": tipo, "csrf_token": csrf(cl, f"/owner/tickets/{tkid}")},
                       files=[("documento", (nombre, contenido, "application/pdf"))],
                       follow_redirects=False)

    r = subir_doc(c, "factura.pdf", b"%PDF-1.4\n" + b"x" * 400)
    check("un PDF de verdad entra", r.status_code == 302, f"-> {r.status_code}")
    r = subir_doc(c, "cfdi.xml", b'<?xml version="1.0"?><c:Comprobante/>')
    check("un XML entra", r.status_code == 302)
    # Lo que importa: el tipo sale de los BYTES, no del nombre ni del header.
    r = subir_doc(c, "trampa.pdf", b"Esto es texto plano disfrazado")
    check("un texto renombrado a .pdf se rechaza", r.status_code == 400, f"-> {r.status_code}")
    r = subir_doc(c, "virus.pdf", b"MZ\x90\x00" + b"\x00" * 200)
    check("un ejecutable renombrado a .pdf se rechaza", r.status_code == 400)
    r = subir_doc(c, "macro.docx", b"PK\x03\x04" + b"\x00" * 200)
    check("un Word/ZIP se rechaza a propósito", r.status_code == 400)
    check("la detección mira los bytes, no la extensión",
          docstore.detectar_tipo(b"%PDF-1.7") == "pdf"
          and docstore.detectar_tipo(b"cualquier cosa") is None)

    print("\n== 12. El archivo en disco no lleva el nombre recibido ==")
    d = SessionLocal()
    doc = d.query(Document).filter(Document.ticket_id == tkid).first()
    check("el nombre original se guarda aparte", doc.file_name == "factura.pdf")
    check("pero en disco es un uuid", "factura" not in doc.stored_path)
    check("se calcula el sha256", doc.sha256 and len(doc.sha256) == 64)
    check("se sella que nació en modo pruebas", doc.meta == "mock")
    check("file_url queda deprecada en NULL", doc.file_url is None)
    check("el año fiscal queda materializado", doc.fiscal_year is not None)
    docid = doc.id
    d.close()

    print("\n== 13. Entrega: siempre como descarga, jamás inline ==")
    r = c.get(f"/media/documentos/{docid}")
    check("descarga bien", r.status_code == 200, f"-> {r.status_code}")
    disp = r.headers.get("content-disposition", "")
    check("va como attachment", disp.startswith("attachment"), f"-> {disp}")
    check("NUNCA inline", "inline" not in disp)
    check("el tipo es opaco", r.headers.get("content-type") == "application/octet-stream")
    check("con nosniff", r.headers.get("x-content-type-options") == "nosniff")
    check("y en un entorno aislado", "sandbox" in (r.headers.get("content-security-policy") or ""))

    print("\n== 14. El inquilino no llega a la factura ==")
    r = ci.get(f"/media/documentos/{docid}")
    check("un inquilino recibe 404, no 403", r.status_code == 404, f"-> {r.status_code}")
    r = ca.get(f"/media/documentos/{docid}")
    check("otro propietario también 404", r.status_code == 404, f"-> {r.status_code}")
    check("el inquilino no ve el nombre del archivo en su ficha",
          "factura.pdf" not in ci.get(f"/inquilino/tickets/{tkid}").text)

    print("\n== 15. Retirar un comprobante borra los bytes, no la constancia ==")
    d = SessionLocal(); doc = d.get(Document, docid); ruta = doc.stored_path; d.close()
    completa = docstore.ruta_absoluta(ruta)
    check("el archivo está en disco", os.path.exists(completa))
    c.post(f"/owner/tickets/{tkid}/documentos/{docid}/eliminar",
           data={"csrf_token": csrf(c, f"/owner/tickets/{tkid}")}, follow_redirects=False)
    check("los bytes desaparecen", not os.path.exists(completa))
    d = SessionLocal(); doc = d.get(Document, docid)
    check("la fila se conserva con la fecha de retirada", doc is not None and doc.deleted_at is not None)
    d.close()
    check("y deja de descargarse", c.get(f"/media/documentos/{docid}").status_code == 404)

    print("\n== 16. Una ruta de descarga no sale del directorio ==")
    from fastapi import HTTPException
    for intento in ("../../../../etc/passwd", "..\\..\\..\\windows\\win.ini"):
        try:
            docstore.ruta_absoluta(intento); salio = True
        except HTTPException:
            salio = False
        check(f"«{intento[:22]}…» se rechaza", not salio)

    print("\n== 17. Los archivos de prueba no comparten carpeta con los reales ==")
    from app import uploads
    os.environ["DATA_MODE"] = "live"; os.environ.pop("UPLOAD_DIR")
    vivo = uploads._resolve_upload_dir()
    os.environ["DATA_MODE"] = "mock"
    prueba = uploads._resolve_upload_dir()
    os.environ["UPLOAD_DIR"] = os.path.join(TMP, "uploads")
    check("modo real y modo pruebas usan carpetas distintas", vivo != prueba,
          f"-> {vivo} vs {prueba}")

print(f"\nRESULTADO: {ok} pasaron, {fail} fallaron")
sys.exit(1 if fail else 0)
