"""Owner router — property list/edit scoped to the current user only.

Gated to role=owner or role=admin (per CEO instruction: admin can do
anything an owner can). Scoping is deliberately by current_user.id in every
query, regardless of role — this is what actually prevents an owner (or an
admin exercising this router) from ever seeing another owner's properties;
admin's "see everything" ability lives in admin.py, not here.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import require_role
from ..db import get_db
from ..models import Property, User
from ..schemas import PropertyIn, PropertyOut

router = APIRouter(prefix="/api/owner", tags=["owner"])

_owner_or_admin = require_role("owner", "admin")


@router.get("/properties", response_model=List[PropertyOut])
def list_my_properties(db: Session = Depends(get_db), current_user: User = Depends(_owner_or_admin)):
    return (
        db.query(Property)
        .filter(Property.owner_id == current_user.id)
        .order_by(Property.id)
        .all()
    )


@router.post("/properties", response_model=PropertyOut, status_code=status.HTTP_201_CREATED)
def create_my_property(
    payload: PropertyIn, db: Session = Depends(get_db), current_user: User = Depends(_owner_or_admin)
):
    prop = Property(owner_id=current_user.id, **payload.model_dump())
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


@router.get("/properties/{property_id}", response_model=PropertyOut)
def get_my_property(
    property_id: int, db: Session = Depends(get_db), current_user: User = Depends(_owner_or_admin)
):
    prop = (
        db.query(Property)
        .filter(Property.id == property_id, Property.owner_id == current_user.id)
        .first()
    )
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


@router.put("/properties/{property_id}", response_model=PropertyOut)
def update_my_property(
    property_id: int,
    payload: PropertyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(_owner_or_admin),
):
    prop = (
        db.query(Property)
        .filter(Property.id == property_id, Property.owner_id == current_user.id)
        .first()
    )
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(prop, field, value)
    db.commit()
    db.refresh(prop)
    return prop


@router.delete("/properties/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_property(
    property_id: int, db: Session = Depends(get_db), current_user: User = Depends(_owner_or_admin)
):
    prop = (
        db.query(Property)
        .filter(Property.id == property_id, Property.owner_id == current_user.id)
        .first()
    )
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    db.delete(prop)
    db.commit()
    return None
