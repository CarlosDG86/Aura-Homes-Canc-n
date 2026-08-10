"""SQLAlchemy models for the Phase 2 platform (2a fully wired; 2b/2c tables
exist as minimal schema shape only — no working CRUD reads/writes them yet).

Field shapes follow docs/phase2/DB_SCHEMA.md, adapted to a single SQLite
file via SQLAlchemy.
"""
import enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
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

    # --- Seguridad de acceso (E1 · docs/phase2/SECURITY.md §1.2, §5) ---
    # is_active permite dar de baja sin borrar: un DELETE arrastraría el
    # historial de propiedades y tickets asociado (SECURITY.md §9).
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    # Teléfono que ve el inquilino, distinto del personal (`phone`). Decisión
    # del CEO 2026-08-08: proteger el celular privado del propietario y poder
    # retirarlo sin borrar su contacto real.
    contact_phone = Column(String, nullable=True)
    failed_login_count = Column(Integer, nullable=False, default=0, server_default="0")
    locked_until = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    must_change_password = Column(Boolean, nullable=False, default=False, server_default="0")
    # Quién dio de alta esta cuenta (un propietario que registra a su inquilino).
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    properties = relationship(
        "Property", back_populates="owner", cascade="all, delete-orphan"
    )


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Link to the public showcase property (data/properties.json "id", e.g.
    # "AUR-001"). NULL for properties created only inside the platform. The
    # site JSON stays the source of truth for public content; this row is a
    # management-side mirror, refreshed by the "sync site properties" action.
    site_ref = Column(String, nullable=True, unique=True, index=True)
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
# Seguridad transversal (E1). No pertenecen a ninguna fase: son la base sobre
# la que se apoyan 2a, 2b y 2c por igual.
# ---------------------------------------------------------------------------


class LoginAttempt(Base):
    """Cada intento de acceso, para limitar fuerza bruta (SECURITY.md §5).

    Se guarda el correo tal cual se tecleó (aunque no exista la cuenta): sin
    eso no se puede detectar a alguien probando una lista de correos.
    """

    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=True, index=True)
    ip = Column(String, nullable=True, index=True)
    success = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now(), index=True)

    # Consulta caliente: "fallos de esta IP en la última ventana".
    __table_args__ = (Index("ix_login_attempts_ip_created", "ip", "created_at"),)


class PlatformSetting(Base):
    """Ajustes internos de la plataforma, en la base de datos.

    Deliberadamente **separado de `data/site.json`**, que es el contenido del
    sitio público y se publica tal cual en el sitio estático. Un dato bancario
    guardado ahí quedaría visible para cualquiera que abra la página. Aquí
    viven los ajustes que solo debe ver el administrador: método de cobro,
    referencias, instrucciones de pago.
    """

    __tablename__ = "platform_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class UserSession(Base):
    """Sesión activa, para poder revocarla desde el servidor (SECURITY.md §3).

    Hasta ahora la sesión vivía solo en una cookie firmada. Eso basta para
    saber quién eres, pero tiene un límite serio: **no se puede invalidar**.
    Si a alguien le roban el portátil o se despide a un colaborador, su cookie
    sigue siendo válida hasta que caduque sola. Con una fila por sesión, el
    servidor decide en cada petición si sigue viva.

    La cookie ya no lleva el `user_id`: lleva un `sid` opaco que apunta aquí.
    Así, revocar es marcar una fila — no hay que esperar a que expire nada.
    """

    __tablename__ = "sessions"

    # `sid` aleatorio, no autoincremental: un id secuencial sería adivinable.
    sid = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    last_seen_at = Column(DateTime, server_default=func.now())
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    revoked_at = Column(DateTime, nullable=True, index=True)
    # Motivo de la revocación: distinguir un cierre de sesión normal de una
    # baja o un cambio de contraseña es lo que hace útil la bitácora después.
    revoked_reason = Column(String, nullable=True)


class Message(Base):
    """Mensaje 1:1 entre propietario e inquilino (DESIGN.md §5.6).

    La bandeja interna es la vía recomendada frente a WhatsApp precisamente
    porque queda registrada: si más adelante hay una disputa sobre qué se pidió
    y cuándo, existe evidencia. WhatsApp no deja rastro en la plataforma.
    """

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    recipient_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=True)
    ticket_id = Column(Integer, ForeignKey("maintenance_tickets.id"), nullable=True)
    subject = Column(String, nullable=True)
    body = Column(Text, nullable=False)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class Announcement(Base):
    """Comunicado de un propietario a varios inquilinos (DESIGN.md §5.5)."""

    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True)
    author_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    send_email = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now(), index=True)

    recipients = relationship(
        "AnnouncementRecipient", back_populates="announcement", cascade="all, delete-orphan"
    )


class AnnouncementRecipient(Base):
    """Entrega individual de un comunicado.

    Se materializa una fila por destinatario para poder mostrar entregado y
    leído. Si el correo falla, `delivered_email_at` queda nulo y el comunicado
    ya está en la bandeja: el mensaje no se pierde por un problema de SMTP.
    """

    __tablename__ = "announcement_recipients"

    id = Column(Integer, primary_key=True)
    announcement_id = Column(Integer, ForeignKey("announcements.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    delivered_inbox_at = Column(DateTime, server_default=func.now())
    delivered_email_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)

    announcement = relationship("Announcement", back_populates="recipients")


class AiUsage(Base):
    """Consumo del agente AI, para aplicar el tope mensual de gasto.

    Sin esta tabla el costo del asistente sería invisible hasta la factura.
    """

    __tablename__ = "ai_usage"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    ticket_id = Column(Integer, ForeignKey("maintenance_tickets.id"), nullable=True)
    model = Column(String, nullable=True)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    image_count = Column(Integer, default=0)
    cost_usd = Column(Numeric(10, 6), default=0)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class AuditLog(Base):
    """Quién hizo qué, cuándo y desde dónde (SECURITY.md §9).

    Solo lectura desde la interfaz: una bitácora que la propia aplicación
    puede editar no sirve como evidencia.
    """

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    actor_role = Column(String, nullable=True)
    actor_ip = Column(String, nullable=True)
    action = Column(String, nullable=False, index=True)
    object_type = Column(String, nullable=True)
    object_id = Column(Integer, nullable=True)
    meta = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)


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
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class TicketCategoryEnum(str, enum.Enum):
    plomeria = "plomeria"
    electrico = "electrico"
    electrodomestico = "electrodomestico"
    estructural = "estructural"
    plagas = "plagas"
    area_comun = "area_comun"
    otro = "otro"


class TicketPriorityEnum(str, enum.Enum):
    baja = "baja"
    media = "media"
    alta = "alta"
    emergencia = "emergencia"


class TicketSourceEnum(str, enum.Enum):
    ai_agent = "ai_agent"
    form = "form"
    staff = "staff"


class TicketEventTypeEnum(str, enum.Enum):
    created = "created"
    status_changed = "status_changed"
    comment = "comment"
    photo_added = "photo_added"
    assigned = "assigned"
    resolved = "resolved"
    reopened = "reopened"


class MaintenanceTicket(Base):
    __tablename__ = "maintenance_tickets"

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False, index=True)
    reported_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TicketStatusEnum), default=TicketStatusEnum.open)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # --- 2b: campos de DESIGN.md §7.4 ---
    # Referencia legible para que inquilino y propietario hablen del mismo
    # ticket sin recitar un id de base de datos.
    public_ref = Column(String, nullable=True, unique=True, index=True)
    lease_id = Column(Integer, ForeignKey("leases.id"), nullable=True)
    category = Column(Enum(TicketCategoryEnum), default=TicketCategoryEnum.otro)
    priority = Column(Enum(TicketPriorityEnum), default=TicketPriorityEnum.media)
    location_in_unit = Column(String, nullable=True)
    created_via = Column(Enum(TicketSourceEnum), default=TicketSourceEnum.form)
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text, nullable=True)
    # Qué entendió el agente AI y con cuánta seguridad. Se guarda para poder
    # auditar sus clasificaciones, no para confiar ciegamente en ellas.
    ai_summary = Column(Text, nullable=True)
    ai_confidence = Column(Numeric(3, 2), nullable=True)

    photos = relationship("TicketPhoto", back_populates="ticket", cascade="all, delete-orphan")
    events = relationship("TicketEvent", back_populates="ticket", cascade="all, delete-orphan")


class TicketPhoto(Base):
    """Foto de un ticket. El archivo vive fuera del árbol web (SECURITY.md §6).

    `stored_path` es relativo al directorio de subidas: guardar rutas absolutas
    ataría la base al equipo donde se creó y complicaría mover el volumen.
    """

    __tablename__ = "ticket_photos"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("maintenance_tickets.id"), nullable=False, index=True)
    stored_path = Column(String, nullable=False)
    original_name = Column(String, nullable=True)
    content_type = Column(String, nullable=True)
    bytes = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    sha256 = Column(String, nullable=True)
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # Se re-codifica siempre al subir, lo que elimina EXIF (incluidas
    # coordenadas GPS: revelar dónde vive un inquilino es una fuga de datos).
    exif_stripped = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now())

    ticket = relationship("MaintenanceTicket", back_populates="photos")


class TicketEvent(Base):
    """Historial del ticket: comentarios, cambios de estado, asignaciones.

    Append-only por diseño — es lo que permite reconstruir qué pasó y cuándo
    si hay una disputa entre inquilino y propietario.
    """

    __tablename__ = "ticket_events"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("maintenance_tickets.id"), nullable=False, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    event_type = Column(Enum(TicketEventTypeEnum), nullable=False)
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=True)
    body = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    ticket = relationship("MaintenanceTicket", back_populates="events")


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
