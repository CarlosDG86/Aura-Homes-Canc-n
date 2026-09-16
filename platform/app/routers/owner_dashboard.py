"""Panel del propietario: indicadores, filtros y descarga (E11 · CEO 2.1 y 2.2).

Módulo propio y no una función más en `pages.py`, que ya pasa de 900 líneas y
mezcla acceso, segundo factor, alta de propietarios, administración de usuarios
y sincronización del sitio. El panel estaba ahí por accidente histórico y
duplicaba a mano el cálculo de las insignias del menú.

## Regla de oro: este módulo NO ESCRIBE NI UNA FILA

Todas sus rutas son GET. Ni para «reconciliar» una discrepancia, ni para
corregir el estatus publicado de una casa. Una pantalla de solo lectura no
puede ser el vector de un cambio no querido, y esa garantía es más barata de
auditar que cualquier permiso.

## Segunda regla: ningún CSV de aquí lleva datos del inquilino

Ni nombre, ni correo, ni teléfono, ni identificador. La ocupación se expresa
«ocupada» o «vacía», nunca «ocupada por Fulano». Un CSV sale de la plataforma
y llega a un tercero —un contador, un socio— que nunca aceptó el aviso de
privacidad.
"""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .. import filtros_owner as fo
from ..db import get_db
from ..mockmode import template_context
from ..models import RoleEnum
from ..security import audit, register_template_globals
from ..strings import t
from .pages import _current_user_or_none, _home_for

router = APIRouter(tags=["owner-dashboard"], include_in_schema=False)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))
register_template_globals(templates)
templates.env.globals["t"] = t


@router.get("/owner", response_class=HTMLResponse)
def owner_dashboard(request: Request, db: Session = Depends(get_db)):
    """Panel del propietario. Sustituye al que vivía en `pages.py`.

    Ojo al mover esto: `main.py` registra `pages.router` antes que este, y
    FastAPI resuelve por orden de registro. Si la definición vieja siguiera
    existiendo, ganaría ella y este módulo no se ejecutaría nunca — sin que
    nada fallara de forma visible. Por eso se borra en el mismo cambio y hay
    una prueba que exige que exista **una sola** ruta GET `/owner`.
    """
    user = _current_user_or_none(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.role not in (RoleEnum.owner, RoleEnum.admin):
        # Tiene sesión válida, solo no le toca esta pantalla: se le manda a la
        # suya y NO al formulario de acceso. Rebotar a `/login` a alguien que
        # ya inició sesión es lo que cerraba el bucle de redirecciones.
        return RedirectResponse(url=_home_for(user), status_code=302)

    datos = fo.componer(db, user, request.query_params)

    if (request.query_params.get("formato") or "").lower() == "csv":
        return _csv_cartera(db, request, user, datos)

    from ..routers.owner_portal import _nav_badges

    return templates.TemplateResponse(
        request=request, name="owner_dashboard.html",
        context={
            "active": "owner",
            "user": user,
            **_nav_badges(db, user),
            **datos,
            **template_context(),
        },
    )


def _csv_cartera(db, request: Request, user, datos) -> Response:
    """Descarga de la cartera con el filtro aplicado.

    No hay centro de reportes ni ruta aparte: dos URL que devuelven lo mismo
    es más superficie que auditar para una cartera de tres a siete casas. El
    reporte de tickets que ya existe se conserva tal cual.
    """
    if not fo.puede_exportar(user):
        return RedirectResponse(url="/owner", status_code=302)

    filas = datos["visibles"]
    if len(filas) > fo.TOPE_FILAS_CSV:
        request.session["owner_flash"] = {
            "kind": "error",
            "message": t("csv.tope", n=len(filas), tope=fo.TOPE_FILAS_CSV),
        }
        return RedirectResponse(url="/owner", status_code=302)

    descripcion = fo.descripcion_filtro(datos["filtros"], datos["zonas"])
    buf = io.StringIO()
    w = csv.writer(buf)

    # Cabecera de procedencia: sin ella, un CSV filtrado que llega a un tercero
    # parece la cartera completa.
    w.writerow(["Aura Homes Cancún — cartera del propietario"])
    w.writerow(["Generado", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")])
    w.writerow(["Usuario", fo.escapar_csv(user.name)])
    w.writerow(["Filtro", fo.escapar_csv(descripcion)])
    w.writerow(["Casas incluidas", len(filas)])
    w.writerow([])

    # Ni una columna con datos del inquilino. La ocupación es un estado de la
    # vivienda, no una persona.
    w.writerow(["ID", "Casa", "Zona", "Recámaras", "m²", "Estatus publicado",
                "Ocupación (contrato)", "Contratos vigentes", "Reportes abiertos",
                "Emergencias", "Coincide con el sitio"])
    for r in filas:
        p = r["prop"]
        w.writerow([
            p.id,
            fo.escapar_csv(p.title),
            fo.escapar_csv(p.zone or ""),
            p.bedrooms if p.bedrooms is not None else "",
            p.area_m2 if p.area_m2 is not None else "",
            p.status.value if p.status else "",
            r["ocupacion"],
            r["contratos"],
            r["abiertos"],
            r["emergencias"],
            "no" if r["ocupacion"] == "revisar" else "sí",
        ])
    w.writerow([])
    w.writerow(["TOTALES", len(filas), "", "", "", "", "",
                sum(r["contratos"] for r in filas),
                sum(r["abiertos"] for r in filas),
                sum(r["emergencias"] for r in filas), ""])

    audit(db, request, "owner.report.export", actor=user, object_type="report",
          meta=f"cartera; {descripcion}; filas={len(filas)}")

    sello = datetime.now(timezone.utc).strftime("%Y%m%d")
    # BOM al inicio: sin él, Excel en español destroza «Categoría» y «Cancún».
    return Response(
        content="﻿" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="cartera-{sello}.csv"'},
    )
