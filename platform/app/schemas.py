"""Pydantic request/response models shared by the admin and owner routers."""
from decimal import Decimal
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .models import PropertyStatusEnum, RoleEnum


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    phone: Optional[str] = None
    role: RoleEnum


class UserCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    password: str
    role: RoleEnum


class PropertyIn(BaseModel):
    title: str
    zone: Optional[str] = None
    city: Optional[str] = "Cancún"
    price_amount: Optional[Decimal] = None
    price_currency: Optional[str] = "MXN"
    status: Optional[PropertyStatusEnum] = PropertyStatusEnum.available
    bedrooms: Optional[int] = None
    bathrooms: Optional[Decimal] = None
    area_m2: Optional[Decimal] = None
    description: Optional[str] = None


class PropertyAdminIn(PropertyIn):
    owner_id: int


class PropertyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    title: str
    zone: Optional[str] = None
    city: Optional[str] = None
    price_amount: Optional[Decimal] = None
    price_currency: Optional[str] = None
    status: PropertyStatusEnum
    bedrooms: Optional[int] = None
    bathrooms: Optional[Decimal] = None
    area_m2: Optional[Decimal] = None
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
