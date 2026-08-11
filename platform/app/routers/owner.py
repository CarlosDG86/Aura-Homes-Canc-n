"""Owner router — property list/edit scoped to the current user only.

Gated to role=owner or role=admin (per CEO instruction: admin can do
anything an owner can). El filtrado por pertenencia ya no se escribe aquí:
vive en `scoping.py` (`owned_properties` / `get_owned_property_or_404`), que
es lo que evita que un propietario vea las casas de otro. Antes ese filtro
estaba copiado en las cinco rutas de este archivo; una copia olvidada bastaba
para abrir una fuga.

`owned_properties` filtra por `owner_id == current_user.id` **también para un
admin**: la capacidad de admin de verlo todo vive en `admin.py`, no aquí.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import require_role
from ..db import get_db
from ..mockmode import owner_property_manage_enabled
from ..models import Property, RoleEnum, User
from ..schemas import PropertyIn, PropertyOut
from ..scoping import get_owned_property_or_404, owned_properties

router = APIRouter(prefix="/api/owner", tags=["owner"])

_owner_or_admin = require_role("owner", "admin")


def _require_manage_enabled(user: User) -> None:
    """Aplica la bandera del CEO en el servidor (DESIGN.md §4).

    Ocultar el botón en la interfaz no es protección: cualquiera puede armar la
    petición a mano. Con la bandera apagada, solo el admin da de alta o borra
    propiedades — que es justo el motivo de la bandera (deben cumplir
    requisitos antes de publicarse).
    """
    if owner_property_manage_enabled():
        return
    if user.role == RoleEnum.admin:
        return
    raise HTTPException(
        status_code=403,
        detail="El alta y baja de propiedades la realiza el administrador.",
    )


@router.get("/properties", response_model=List[PropertyOut])
def list_my_properties(db: Session = Depends(get_db), current_user: User = Depends(_owner_or_admin)):
    return owned_properties(db, current_user).order_by(Property.id).all()


@router.post("/properties", response_model=PropertyOut, status_code=status.HTTP_201_CREATED)
def create_my_property(
    payload: PropertyIn, db: Session = Depends(get_db), current_user: User = Depends(_owner_or_admin)
):
    _require_manage_enabled(current_user)
    # owner_id sale de la sesión, nunca del payload (DESIGN.md §11): si viniera
    # del cliente, cualquiera podría crear propiedades a nombre de otro.
    data = payload.model_dump()
    data.pop("owner_id", None)
    prop = Property(owner_id=current_user.id, **data)
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


@router.get("/properties/{property_id}", response_model=PropertyOut)
def get_my_property(
    property_id: int, db: Session = Depends(get_db), current_user: User = Depends(_owner_or_admin)
):
    return get_owned_property_or_404(db, current_user, property_id)


@router.put("/properties/{property_id}", response_model=PropertyOut)
def update_my_property(
    property_id: int,
    payload: PropertyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_owner_or_admin),
):
    prop = get_owned_property_or_404(db, current_user, property_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        # owner_id no se reasigna desde aquí: cambiar de dueño es una acción de
        # admin, auditada, que además debe revisar los tickets abiertos.
        if field == "owner_id":
            continue
        setattr(prop, field, value)
    db.commit()
    db.refresh(prop)
    return prop


@router.delete("/properties/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_property(
    property_id: int, db: Session = Depends(get_db), current_user: User = Depends(_owner_or_admin)
):
    _require_manage_enabled(current_user)
    prop = get_owned_property_or_404(db, current_user, property_id)
    db.delete(prop)
    db.commit()
    return None
