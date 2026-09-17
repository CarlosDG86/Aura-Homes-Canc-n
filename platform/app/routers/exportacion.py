"""Exportación fiscal para el contador (E14 · D-015).

Tres pantallas y una descarga:

- `GET  /owner/fiscal/exportar` — **la pantalla intermedia**: qué va a salir,
  cuántos comprobantes, cuántos huecos y la casilla de fotos, desmarcada.
- `POST /owner/fiscal/exportar` — genera. Sin `confirmado=si`, que solo lleva
  el formulario de la pantalla intermedia, **no genera**: devuelve a ella.
- `GET  /owner/fiscal/exportaciones` — historial de lo que salió.
- `GET  /owner/fiscal/exportaciones/{id}/descargar`

## Lo que NO bloquea un plan ni una cuenta suspendida

Nada de esto. Exportar los propios datos fiscales está en todos los planes,
incluida la prueba vencida y la cuenta suspendida (D-018, AREA_A §4.5): si un
cliente no puede entregarle a su contador lo que le pide el SAT porque dejó de
pagarnos, el obstáculo somos nosotros.
"""
from __future__ import annotations

import os
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .. import exportacion, fiscal
from ..db import get_db
from ..mockmode import is_mock
from ..models import FiscalExport, Property
from ..scoping import get_owned_property_or_404, owned_properties
from ..security import audit, register_template_globals
from ..strings import t
from .fiscal import _cuenta_de, _flash, _guardia
from .owner_portal import _ctx, _nav_badges

router = APIRouter(tags=["exportacion"], include_in_schema=False)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))
register_template_globals(templates)
templates.env.globals["t"] = t


def _alcance(db, user, anio_crudo, prop_crudo):
    """Año y propiedades a exportar, siempre dentro de la cartera del usuario."""
    todas = owned_properties(db, user).order_by(Property.id).all()
    ids = [p.id for p in todas]
    anios = fiscal.anios_con_datos(db, ids)
    if anio_crudo and str(anio_crudo).isdigit():
        anio = int(anio_crudo)
    else:
        anio = anios[0] if anios else date.today().year
    unica = None
    if prop_crudo and str(prop_crudo).isdigit():
        # 404 para una casa ajena: ni siquiera se confirma que existe.
        unica = get_owned_property_or_404(db, user, int(prop_crudo))
    return anio, anios, todas, unica


@router.get("/owner/fiscal/exportar", response_class=HTMLResponse)
def exportar_confirmar(request: Request, db: Session = Depends(get_db)):
    user, resp = _guardia(request, db)
    if resp:
        return resp
    q = request.query_params
    anio, anios, todas, unica = _alcance(db, user, q.get("anio"), q.get("propiedad"))
    vista = exportacion.calcular(db, [unica] if unica else todas, anio)
    return templates.TemplateResponse(
        request=request, name="owner_exportar.html",
        context=_ctx(user, request, active="fiscal", **_nav_badges(db, user),
                     anio=anio, anios=anios or [anio], propiedades=todas,
                     unica=unica, vista=vista, tope_mb=exportacion.MAX_BYTES // (1024 * 1024),
                     datos_de_prueba=is_mock()),
    )


@router.post("/owner/fiscal/exportar")
def exportar_generar(request: Request, db: Session = Depends(get_db),
                     anio: str = Form(...), propiedad: str = Form(""),
                     incluir_fotos: str = Form(""), confirmado: str = Form(""),
                     csrf_token: str = Form("")):
    user, resp = _guardia(request, db)
    if resp:
        return resp
    anio_i, _, todas, unica = _alcance(db, user, anio, propiedad)
    volver = f"/owner/fiscal/exportar?anio={anio_i}" + (f"&propiedad={unica.id}" if unica else "")

    # La pantalla intermedia es obligatoria: una petición armada a mano que
    # se la salte vuelve a ella en vez de generar.
    if confirmado != "si":
        return RedirectResponse(url=volver, status_code=302)

    fotos = incluir_fotos == "si"
    cuenta = _cuenta_de(db, user)
    try:
        fila = exportacion.generar(db, user=user, propiedades=[unica] if unica else todas,
                                   anio=anio_i, incluir_fotos=fotos,
                                   propiedad_unica=unica, cuenta=cuenta)
    except exportacion.PaqueteDemasiadoGrande as e:
        _flash(request, "error", str(e))
        return RedirectResponse(url=volver, status_code=302)
    db.commit()

    audit(db, request, "fiscal.exportar", actor=user,
          object_type="property" if unica else "account",
          object_id=unica.id if unica else getattr(cuenta, "id", None),
          meta=f"anio={anio_i} export={fila.id} gastos={fila.expense_count} "
               f"docs={fila.receipt_count} sin_fx={fila.missing_fx_count} "
               f"fotos={'si' if fotos else 'no'}")
    if fotos:
        # Registro aparte y con nombre propio: es la respuesta el día que un
        # inquilino pregunte quién sacó fotos de su casa.
        audit(db, request, "fiscal.exportar_fotos_interior", actor=user,
              object_type="fiscal_export", object_id=fila.id,
              meta=f"anio={anio_i}")
    _flash(request, "ok", "Paquete generado. Descárgalo de la lista.")
    return RedirectResponse(url="/owner/fiscal/exportaciones", status_code=302)


def _mis_exportaciones(db, user):
    """Las del usuario Y de su cuenta. Las dos condiciones, no una.

    Solo por cuenta, un compañero de la misma administradora vería los
    paquetes de otro; solo por usuario, una fila que cruzó de cuenta seguiría
    visible.
    """
    q = db.query(FiscalExport).filter(FiscalExport.owner_user_id == user.id)
    aid = getattr(user, "account_id", None)
    if aid is None:
        return q.filter(FiscalExport.account_id.is_(None))
    return q.filter(FiscalExport.account_id == aid)


@router.get("/owner/fiscal/exportaciones", response_class=HTMLResponse)
def exportaciones_lista(request: Request, db: Session = Depends(get_db)):
    user, resp = _guardia(request, db)
    if resp:
        return resp
    filas = _mis_exportaciones(db, user).order_by(FiscalExport.id.desc()).limit(100).all()
    nombres = {p.id: p.title for p in owned_properties(db, user).all()}
    return templates.TemplateResponse(
        request=request, name="owner_exportaciones.html",
        context=_ctx(user, request, active="exportar", **_nav_badges(db, user),
                     filas=filas, nombres=nombres,
                     existe={f.id: _existe(f) for f in filas}),
    )


def _existe(fila) -> bool:
    try:
        return os.path.isfile(exportacion.ruta_absoluta(fila.stored_path))
    except HTTPException:
        return False


@router.get("/owner/fiscal/exportaciones/{export_id}/descargar")
def exportacion_descargar(export_id: int, request: Request, db: Session = Depends(get_db)):
    user, resp = _guardia(request, db)
    if resp:
        return resp
    fila = _mis_exportaciones(db, user).filter(FiscalExport.id == export_id).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Exportación no encontrada")
    ruta = exportacion.ruta_absoluta(fila.stored_path)
    if not os.path.isfile(ruta):
        raise HTTPException(status_code=404, detail="El archivo ya no está en el servidor")
    audit(db, request, "fiscal.export_download", actor=user,
          object_type="fiscal_export", object_id=fila.id)
    return FileResponse(
        ruta, media_type="application/zip",
        filename=exportacion.nombre_de_descarga(db, fila),
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )
