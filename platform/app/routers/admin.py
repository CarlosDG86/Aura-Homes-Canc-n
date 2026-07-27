"""Admin router — full access. Gated to role=admin only.

- Properties: create/list/get/update/delete (any owner).
- Owners directory: list users with role=owner.
- Users/roles list: list all users, create a user with a role assignment
  (the "invite" flow the CEO said is fine to include for 2a).
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import hash_password, require_role
from ..db import get_db
from ..models import Property, RoleEnum, User
from ..schemas import PropertyAdminIn, PropertyIn, PropertyOut, UserCreate, UserOut

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_role("admin"))],
)


# --- Properties --------------------------------------------------------


@router.get("/properties", response_model=List[PropertyOut])
def list_properties(db: Session = Depends(get_db)):
    return db.query(Property).order_by(Property.id).all()


@router.post("/properties", response_model=PropertyOut, status_code=status.HTTP_201_CREATED)
def create_property(payload: PropertyAdminIn, db: Session = Depends(get_db)):
    owner = db.query(User).filter(User.id == payload.owner_id, User.role == RoleEnum.owner).first()
    if not owner:
        raise HTTPException(status_code=400, detail="owner_id must reference an existing user with role=owner")
    prop = Property(**payload.model_dump())
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


@router.get("/properties/{property_id}", response_model=PropertyOut)
def get_property(property_id: int, db: Session = Depends(get_db)):
    prop = db.get(Property, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


@router.put("/properties/{property_id}", response_model=PropertyOut)
def update_property(property_id: int, payload: PropertyIn, db: Session = Depends(get_db)):
    prop = db.get(Property, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(prop, field, value)
    db.commit()
    db.refresh(prop)
    return prop


@router.delete("/properties/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(property_id: int, db: Session = Depends(get_db)):
    prop = db.get(Property, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    db.delete(prop)
    db.commit()
    return None


# --- Owners directory ----------------------------------------------------


@router.get("/owners", response_model=List[UserOut])
def list_owners(db: Session = Depends(get_db)):
    return db.query(User).filter(User.role == RoleEnum.owner).order_by(User.id).all()


# --- Users / roles ---------------------------------------------------------


@router.get("/users", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        name=payload.name,
        email=email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
