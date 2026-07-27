"""SQLAlchemy models for the Phase 2 platform (2a fully wired; 2b/2c tables
exist as minimal schema shape only — no working CRUD reads/writes them yet).

Field shapes follow docs/phase2/DB_SCHEMA.md, adapted to a single SQLite
file via SQLAlchemy.
"""
import enum

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from .db import Base


class RoleEnum(str, enum.Enum):
    admin = "admin"
    owner = "owner"
    tenant = "tenant"


class PropertyStatusEnum(str, enum.Enum):
    available = "available"
    rented = "rented"


class LeaseStatusEnum(str, enum.Enum):
    active = "active"
    ended = "ended"


class TicketStatusEnum(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"


class PaymentStatusEnum(str, enum.Enum):
    received = "received"
    pending_review = "pending_review"


class DocTypeEnum(str, enum.Enum):
    contract = "contract"
    id_verification = "id_verification"
    policy = "policy"
    receipt = "receipt"
    other = "other"


class VisitStatusEnum(str, enum.Enum):
    scheduled = "scheduled"
    completed = "completed"
    cancelled = "cancelled"


# ---------------------------------------------------------------------------
# 2a — fully modeled and used by admin.py / owner.py
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    phone = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(RoleEnum), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    properties = relationship(
        "Property", back_populates="owner", cascade="all, delete-orphan"
    )


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    zone = Column(String, nullable=True)
    city = Column(String, default="Cancún")
    price_amount = Column(Numeric(12, 2), nullable=True)
    price_currency = Column(String, default="MXN")
    status = Column(Enum(PropertyStatusEnum), default=PropertyStatusEnum.available)
    bedrooms = Column(Integer, nullable=True)
    bathrooms = Column(Numeric(3, 1), nullable=True)
    area_m2 = Column(Numeric(8, 2), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    owner = relationship("User", back_populates="properties")
    images = relationship(
        "PropertyImage", back_populates="property", cascade="all, delete-orphan"
    )
    team_members = relationship(
        "PropertyTeamMember", back_populates="property", cascade="all, delete-orphan"
    )


class PropertyImage(Base):
    __tablename__ = "property_images"

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    url = Column(String, nullable=False)
    sort_order = Column(Integer, default=0)

    property = relationship("Property", back_populates="images")


class PropertyTeamMember(Base):
    __tablename__ = "property_team_members"

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role_description = Column(String, nullable=True)

    property = relationship("Property", back_populates="team_members")


# ---------------------------------------------------------------------------
# 2b / 2c — minimal schema shape only. No router reads or writes these yet;
# tenant.py and payments.py return a 501 stub for every route. Kept here so
# the 2b/2c module shape exists in parallel with Legal review, per the plan.
# ---------------------------------------------------------------------------


class Lease(Base):
    __tablename__ = "leases"

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    monthly_rent = Column(Numeric(12, 2), nullable=True)
    status = Column(Enum(LeaseStatusEnum), default=LeaseStatusEnum.active)


class MaintenanceTicket(Base):
    __tablename__ = "maintenance_tickets"

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    reported_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TicketStatusEnum), default=TicketStatusEnum.open)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    lease_id = Column(Integer, ForeignKey("leases.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=True)
    currency = Column(String, default="MXN")
    payment_date = Column(Date, nullable=True)
    status = Column(Enum(PaymentStatusEnum), default=PaymentStatusEnum.pending_review)
    receipt_document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    tenant_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    file_name = Column(String, nullable=True)
    file_url = Column(String, nullable=True)
    doc_type = Column(Enum(DocTypeEnum), nullable=True)
    meta = Column(String, nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now())


class Visit(Base):
    __tablename__ = "visits"

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    prospect_name = Column(String, nullable=True)
    prospect_contact = Column(String, nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    status = Column(Enum(VisitStatusEnum), default=VisitStatusEnum.scheduled)
