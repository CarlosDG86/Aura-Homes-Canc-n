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
    #: Añadido el 2026-11-04 para la columna que pidió el CEO en el tablero.
    #: Añadir un miembro es seguro —lo viejo se sigue leyendo—; renombrar o
    #: quitar no lo es. Ver `app/tablero.py` para el riesgo al revertir.
    esperando_cliente = "esperando_cliente"
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
    # E12: comprobantes del trabajo de mantenimiento. Solo se APENDIZA, jamás
    # se renombra — los enums se guardan por nombre. Es seguro incluso ante
    # una reversión porque hoy ningún router lee `Document`.
    invoice = "invoice"
    quote = "quote"


class VisitStatusEnum(str, enum.Enum):
    scheduled = "scheduled"
    completed = "completed"
    cancelled = "cancelled"


# ---------------------------------------------------------------------------
# 2a — fully modeled and used by admin.py / owner.py
# ---------------------------------------------------------------------------


class Account(Base):
    """La empresa administradora. Raíz de aislamiento del SaaS (D-013).

    Antes de esta tabla, la frontera entre clientes era `Property.owner_id`:
    un usuario. Eso servía cuando la plataforma administraba las casas del
    propio CEO, pero D-010 la convirtió en un producto que se vende a otras
    administradoras, y una administradora tiene más de una persona.

    Qué significa cada cosa:

    - `plan` y `trial_*` son **datos administrativos**: la plataforma registra
      QUÉ plan tiene la cuenta, nunca CUÁNTO cuesta (D-019). Cualquier importe
      aquí sería el primer ladrillo de facturación, y la facturación cae bajo
      la puerta legal de pagos, hoy cerrada.
    - `is_operator` marca a las cuentas de Aura: son las únicas que pueden
      escribir `site_ref`, es decir publicar en el sitio escaparate.
    - `trial_ends_at` se materializa al arrancar la prueba en vez de calcularse
      al leer, para que cambiar `trial_days` no mueva la fecha de vencimiento
      de una prueba ya empezada.

    **Prohibido por diseño en esta tabla:** importes, moneda de cobro, ciclo de
    facturación, CLABE, IBAN, tarjeta, RFC, EIN o domicilio fiscal.
    """

    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

    # Texto validado en Python, no Enum() de SQLAlchemy: añadir un plan no debe
    # exigir tocar la base, y un valor desconocido leído de disco no debe
    # reventar el ORM (degrada a 'trial', ver plans.py).
    plan = Column(String, nullable=False, default="trial", server_default="trial")
    status = Column(String, nullable=False, default="activa", server_default="activa")

    # Prueba gratuita (D-019: 90 días, una sola casa).
    trial_days = Column(Integer, nullable=False, default=90, server_default="90")
    trial_started_at = Column(DateTime, nullable=True)
    trial_ends_at = Column(DateTime, nullable=True)
    trial_property_id = Column(Integer, nullable=True)

    # Excepción comercial puntual sin inventar un plan nuevo.
    properties_max_override = Column(Integer, nullable=True)

    is_operator = Column(Boolean, nullable=False, default=False, server_default="0")
    primary_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    country = Column(String, nullable=True, default="MX", server_default="MX")
    # Jurisdicción fiscal por omisión de las propiedades de la cuenta (E13).
    default_tax_jurisdiction = Column(String, nullable=True, default="MX", server_default="MX")
    base_currency = Column(String, nullable=True, default="MXN", server_default="MXN")

    # NULL = «plan sin asignar»: es como quedan las cuentas migradas, para que
    # el administrador vea que nadie ha decidido todavía su plan comercial.
    plan_assigned_at = Column(DateTime, nullable=True)
    plan_assigned_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    plan_note = Column(String(500), nullable=True)

    # Cable trampa mock↔real: nombre del archivo de base donde nació la fila.
    # Si una cuenta creada en la base de pruebas aparece en la real, algo se
    # copió que no debía.
    created_in_db = Column(String, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AccountPlanEvent(Base):
    """Historial comercial de una cuenta. Solo se añade, nunca se modifica.

    Existe aparte de `audit_log` por una razón concreta: la bitácora la escribe
    `security.audit()` y **ninguna plantilla la lee** todavía, así que un
    historial que solo viviera ahí sería un historial que nadie puede
    consultar. Este sí se muestra en la ficha de la cuenta.
    """

    __tablename__ = "account_plan_events"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    from_plan = Column(String, nullable=True)
    to_plan = Column(String, nullable=True)
    from_trial_ends_at = Column(DateTime, nullable=True)
    to_trial_ends_at = Column(DateTime, nullable=True)
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=True)
    note = Column(Text, nullable=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


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

    # --- Segundo factor (E2 · SECURITY.md §1.3) ---
    # Obligatorio para administradores: en internet, una contraseña sola no
    # basta para la cuenta que lo ve todo. El secreto se guarda cifrado por el
    # propio TOTP estándar (base32) y solo sirve junto al dispositivo.
    totp_secret = Column(String, nullable=True)
    totp_enabled = Column(Boolean, nullable=False, default=False, server_default="0")
    totp_confirmed_at = Column(DateTime, nullable=True)

    # --- Acceso con Google (E2 · SECURITY.md §1.1) ---
    # `sub` es el identificador PERMANENTE de la cuenta de Google. Se vincula
    # por aquí y no por correo, porque un correo puede cambiar de dueño.
    google_sub = Column(String, nullable=True, unique=True, index=True)

    # --- Cuenta a la que pertenece (E9 · D-013) ---
    # Nullable a propósito: SQLite no admite añadir una columna NOT NULL sin
    # default a una tabla con filas, y sobre todo porque un NULL debe caer en
    # la rama heredada del aislamiento (filtrar por `owner_id`), que es
    # estrictamente más estrecha. Fallar estrecho, nunca ancho.
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)

    # E10: cuándo se cambió la contraseña por última vez. Sirve para tres
    # cosas: mostrárselo al usuario, invalidar tokens de recuperación emitidos
    # antes del cambio, y responder al auditor cuándo se tocó la credencial.
    password_changed_at = Column(DateTime, nullable=True)

    properties = relationship(
        "Property", back_populates="owner", cascade="all, delete-orphan"
    )


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # De qué cliente son estos datos (E9 · D-013). EXPLÍCITA a propósito, en
    # vez de derivarla del dueño: hay tres rutas que reasignan `owner_id`
    # (pages.py, la sincronización del sitio y la API JSON de admin), y si la
    # cuenta se dedujera del dueño, esas rutas moverían en silencio los
    # tickets, las fotos del interior de una vivienda y los futuros
    # comprobantes fiscales de un cliente a otro. Con la columna explícita,
    # cruzar la frontera deja de ser un efecto colateral y pasa a ser una
    # acción propia, auditada y bloqueable.
    #
    # El precio es que dos columnas pueden desincronizarse y SQLite no lo
    # impide (`PRAGMA foreign_keys` devuelve 0). Lo sostienen tres cosas: un
    # escritor único, el verificador de integridad del arranque y una prueba
    # con deriva inyectada a propósito.
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    #: Jurisdicción fiscal de ESTA casa (E13). NULL hereda la de la cuenta y,
    #: si tampoco la hay, 'MX'. Va por propiedad y no solo por cuenta porque
    #: una misma administradora puede tener casas a los dos lados.
    tax_jurisdiction = Column(String, nullable=True)
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

    # Qué clase de intento fue (E10). NULL = intento de acceso, que es lo que
    # son todas las filas anteriores a esta columna. `reset` = solicitud de
    # recuperación; `reset_token` = intento de canjear un enlace.
    #
    # No es opcional: sin ella, el freno por IP contaría las solicitudes de
    # recuperación como fallos de acceso, y once peticiones a /recuperar
    # dejarían sin /login a toda una oficina o a un rango de móvil durante un
    # minuto. Sería una negación de servicio trivial contra usuarios reales.
    kind = Column(String, nullable=True)

    # Consulta caliente: "fallos de esta IP en la última ventana".
    __table_args__ = (Index("ix_login_attempts_ip_created", "ip", "created_at"),)


class PasswordResetToken(Base):
    """Enlaces de «olvidé mi contraseña» (E10 · punto 3.2 del CEO).

    **El token nunca se guarda**: se guarda su SHA-256. Quien lea la base no
    puede fabricar un enlace válido.

    SHA-256 y no bcrypt a propósito: el token tiene 32 bytes de entropía, no
    hay nada que ralentizar por fuerza bruta, y un hash determinista permite
    buscarlo por igualdad con índice único en vez de recorrer la tabla
    comparando fila por fila.

    `user_email_at_issue` cierra un agujero que la base no puede cerrar: con
    `PRAGMA foreign_keys = 0`, borrar un usuario deja sus tokens huérfanos, y
    SQLite reutiliza el rowid máximo. Un token viejo podría acabar apuntando a
    un id que después ocupa otra persona. Se compara el correo al validar.
    """

    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(64), nullable=False)
    user_email_at_issue = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    # VARCHAR y no Enum: un valor desconocido en un Enum rompe la lectura del
    # ORM, y este es justo el flujo que no puede romperse.
    consumed_reason = Column(String, nullable=True)
    requested_ip = Column(String(64), nullable=True)
    requested_user_agent = Column(String(300), nullable=True)
    used_ip = Column(String(64), nullable=True)

    __table_args__ = (
        Index("ux_password_reset_tokens_hash", "token_hash", unique=True),
        Index("ix_password_reset_tokens_user", "user_id", "used_at"),
    )


class Provider(Base):
    """Proveedor de mantenimiento (E12 · punto 5 del CEO).

    **Es un dato de la cuenta, nunca una fila en `users`.** La tentación es
    obvia —ya hay tabla de personas— y es un error por tres motivos
    verificables: `users.email` es UNIQUE global, así que dos administradoras
    no podrían registrar al mismo plomero y el fallo solo aparecería con el
    segundo cliente; `password_hash` es NOT NULL, así que habría que
    inventarle una contraseña a alguien que no va a entrar; y entraría en
    `scoped_users`, apareciendo como persona asignable y como destinatario de
    mensajes.

    **Prohibido por diseño:** CLABE, cuenta bancaria y domicilio. Un dato
    bancario de un tercero es materia de pagos y cae tras otra puerta; el
    domicilio no aporta nada al ticket y sí es dato personal de alguien que no
    firmó nada.
    """

    __tablename__ = "providers"

    id = Column(Integer, primary_key=True)
    # NOT NULL: es tabla nueva, así que `create_all` la crea así sin problema,
    # y el aislamiento puede fallar cerrado desde el primer día.
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    contact_name = Column(String, nullable=True)
    # Oficio. VARCHAR validado en Python contra los nombres de
    # `TicketCategoryEnum` + 'otro'; no se crea un catálogo nuevo ni un Enum.
    trade = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    # Sin UNIQUE a propósito: el mismo plomero puede estar en dos cuentas.
    email = Column(String, nullable=True)
    tax_id = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    archived_at = Column(DateTime, nullable=True)
    # Sella una supresión de contacto conservando el nombre: responde a un
    # derecho de supresión del proveedor sin destruir el registro fiscal que
    # lo cita.
    redacted_at = Column(DateTime, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("ix_providers_account", "account_id", "is_active"),)


class Expense(Base):
    """Un gasto de una propiedad (E13 · puntos 2.3 y 2.4 del CEO).

    ## Lo que se captura y lo que se deriva

    `amount` + `currency` es **lo que se pagó** y no se sobrescribe jamás.
    `amount_base` es derivado y **congelado en la fila** junto con la tasa, su
    fecha y su origen: un total que cambia de cifra entre marzo y abril no
    sirve como evidencia ante nadie.

    Si no hay tasa disponible, `amount_base` queda **NULL** y la pantalla lo
    cuenta como hueco antes de los totales. En ninguna salida aparece un
    importe convertido sin origen: **un reporte visiblemente incompleto es
    infinitamente mejor que uno silenciosamente falso.**

    ## No hay DELETE

    Un gasto se **anula**, no se borra: `voided_at` más el motivo. Borrar la
    fila destruiría la constancia de que existió, que es justo lo que un
    auditor viene a revisar.

    ## No lleva columna `locked`

    El bloqueo por cierre de año se **deriva** consultando `fiscal_year_closures`
    al escribir. Una bandera denormalizada puede quedar desincronizada del
    cierre real; una consulta pequeña en un POST no cuesta nada.
    """

    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, nullable=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False, index=True)
    # Punto 2.4: un ticket puede tener varios gastos; un gasto puede no tener
    # ticket (el predial no nace de una avería).
    ticket_id = Column(Integer, ForeignKey("maintenance_tickets.id"), nullable=True, index=True)

    expense_date = Column(Date, nullable=False)
    #: Se deriva de `expense_date` al escribir, no se pide en el formulario.
    #: Materializado para que el índice compuesto sirva de verdad.
    tax_year = Column(Integer, nullable=False, index=True)

    #: VARCHAR contra `fiscal_catalog`, JAMÁS un Enum: los Enum se persisten
    #: con el nombre del miembro y un valor desconocido rompe la lectura del
    #: ORM. Un catálogo fiscal está condenado a crecer.
    category_code = Column(String(40), nullable=False)

    provider_id = Column(Integer, nullable=True)
    #: Instantánea de texto: sobrevive al borrado del proveedor y permite
    #: capturar sin haberlo dado de alta antes.
    provider_name_snapshot = Column(String(160), nullable=True)
    #: UUID del CFDI en México o número de factura en EE. UU. Una columna
    #: sirve a las dos. **Se teclea; no se extrae de ningún XML.**
    tax_doc_ref = Column(String(64), nullable=True)

    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="MXN", server_default="MXN")
    base_currency = Column(String(3), nullable=False, default="MXN", server_default="MXN")
    amount_base = Column(Numeric(14, 2), nullable=True)
    fx_rate = Column(Numeric(18, 8), nullable=True)
    fx_rate_date = Column(Date, nullable=True)
    fx_source = Column(String(40), nullable=True)

    #: Mejora capitalizable frente a gasto corriente: la única distinción que
    #: las dos jurisdicciones tratan igual de distinto.
    is_capital = Column(Boolean, nullable=False, default=False, server_default="0")
    payment_method = Column(String(30), nullable=True)
    note = Column(Text, nullable=True)
    #: `confirmado` | `borrador`. Todo lo que genere la automatización nacerá
    #: en borrador, para que nadie reporte una cifra que no revisó.
    status = Column(String(16), nullable=False, default="confirmado",
                    server_default="confirmado")
    #: Asiento de ajuste sobre un gasto de un año ya cerrado. Es lo que hace un
    #: contador cuando encuentra algo después de entregar.
    adjusts_expense_id = Column(Integer, nullable=True)
    #: Sello del modo en que nació la fila. Permite purgar con exactitud los
    #: datos de la época de pruebas al pasar a real.
    data_mode = Column(String(8), nullable=False, default="mock", server_default="mock")

    voided_at = Column(DateTime, nullable=True)
    voided_by_user_id = Column(Integer, nullable=True)
    voided_reason = Column(String(200), nullable=True)

    created_by_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_expenses_account_year", "account_id", "tax_year"),
        Index("ix_expenses_property_year", "property_id", "tax_year"),
    )


class FxRate(Base):
    """Tipos de cambio que el propietario carga a mano.

    **No hay consulta automática.** La objeción no es la dependencia técnica:
    es que una llamada saliente produce una cifra cuyo origen no se podría
    justificar ante un auditor, y añade un punto de fallo a algo que tiene que
    funcionar en marzo. El propietario elige la tasa y declara su fuente, y esa
    fuente se imprime en cada línea del reporte.

    `source` es NOT NULL a propósito: toda tasa debe poder responder «de dónde
    salió esto».
    """

    __tablename__ = "fx_rates"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, nullable=True)
    currency_from = Column(String(3), nullable=False)
    currency_to = Column(String(3), nullable=False)
    rate_date = Column(Date, nullable=False)
    rate = Column(Numeric(18, 8), nullable=False)
    kind = Column(String(16), nullable=False, default="diario")  # diario | promedio_anual
    tax_year = Column(Integer, nullable=True)
    source = Column(String(40), nullable=False)
    note = Column(String(200), nullable=True)
    entered_by_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ux_fx_rates", "account_id", "currency_from", "currency_to",
              "rate_date", "kind", unique=True),
    )


class FiscalYearClosure(Base):
    """Años fiscales cerrados.

    **Honestidad obligatoria:** esto es un control de la aplicación, no
    inmutabilidad criptográfica. Quien tenga el archivo de la base puede
    alterar cualquier fila. Lo que sí permite es demostrar que el paquete que
    recibió el contador no cambió, mediante su suma de verificación.

    Reabrir exige motivo escrito. La reversibilidad con huella es preferible a
    la irreversibilidad, que empuja a la gente a falsear datos.
    """

    __tablename__ = "fiscal_year_closures"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, nullable=True)
    #: NULL = el cierre aplica a toda la cuenta.
    property_id = Column(Integer, nullable=True)
    tax_year = Column(Integer, nullable=False)
    closed_at = Column(DateTime, nullable=False, server_default=func.now())
    closed_by_user_id = Column(Integer, nullable=True)
    reopened_at = Column(DateTime, nullable=True)
    reopened_by_user_id = Column(Integer, nullable=True)
    reopen_reason = Column(String(300), nullable=True)
    export_sha256 = Column(String(64), nullable=True)

    __table_args__ = (
        Index("ux_fiscal_closures", "account_id", "property_id", "tax_year",
              unique=True),
    )


class TicketQuote(Base):
    """Cotización de un proveedor para un ticket (E14 · punto 7.4 del CEO).

    Hoy se **registra a mano**: el propietario teclea lo que le pasaron por
    teléfono o WhatsApp. Eso no es infraestructura especulativa — comparar dos
    precios antes de aprobar es lo que un propietario con veinte casas hace el
    lunes, exista o no un agente de IA detrás.

    **Aprobar no notifica al proveedor, no agenda visita, no cambia el estado
    del ticket y no crea ningún pagadero.** El texto del CEO se corta
    exactamente ahí («Si el owner aprueba…») y no se inventa el final.

    Por eso `status` es VARCHAR y no un Enum: cuando el CEO cierre la frase,
    ampliar la máquina de estados no exigirá tocar la base ni arriesgará la
    lectura del ORM.
    """

    __tablename__ = "ticket_quotes"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, nullable=False, index=True)
    ticket_id = Column(Integer, ForeignKey("maintenance_tickets.id"),
                       nullable=False, index=True)
    provider_id = Column(Integer, nullable=True)
    #: Instantánea del nombre: la cotización tiene que poder decir de quién era
    #: aunque el proveedor se borre después.
    provider_name_snapshot = Column(String(160), nullable=False)
    status = Column(String(20), nullable=False, default="registrada",
                    server_default="registrada")
    #: `manual` hoy. `agente` el día que exista el flujo del 7.4.
    source = Column(String(20), nullable=False, default="manual",
                    server_default="manual")
    amount = Column(Numeric(14, 2), nullable=True)
    currency = Column(String(3), nullable=True, default="MXN")
    valid_until = Column(Date, nullable=True)
    scope_notes = Column(Text, nullable=True)
    attachment_id = Column(Integer, nullable=True)
    requested_at = Column(DateTime, nullable=True)
    responded_at = Column(DateTime, nullable=True)
    decided_at = Column(DateTime, nullable=True)
    requested_by_user_id = Column(Integer, nullable=True)
    decided_by_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (Index("ix_ticket_quotes_ticket", "ticket_id"),)


class FiscalExport(Base):
    """Un paquete de exportación generado (E14 · D-015).

    «Auditors View» es **esto**: un archivo que el propietario descarga y le
    entrega a su contador. No hay rol de auditor ni acceso de terceros — eso
    abriría una superficie nueva sobre datos de inquilinos y obligaría a
    rehacer las comprobaciones de aislamiento.

    `sha256` es lo que permite al contador demostrar que **lo que él recibió**
    no cambió. Es la única garantía real que se puede dar: el cierre de año es
    un control de la aplicación, no inmutabilidad criptográfica.
    """

    __tablename__ = "fiscal_exports"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, nullable=True, index=True)
    owner_user_id = Column(Integer, nullable=False, index=True)
    tax_year = Column(Integer, nullable=False)
    #: NULL = el paquete cubre toda la cartera.
    property_id = Column(Integer, nullable=True)
    stored_path = Column(String, nullable=False)
    bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    #: Nace en False siempre. Marcarlo exige una pantalla intermedia y queda
    #: en la bitácora: son fotos del interior de la vivienda de un inquilino.
    includes_ticket_photos = Column(Boolean, nullable=False, default=False,
                                    server_default="0")
    expense_count = Column(Integer, nullable=True)
    receipt_count = Column(Integer, nullable=True)
    missing_fx_count = Column(Integer, nullable=True)
    excluded_other_mode_count = Column(Integer, nullable=True)
    catalog_version = Column(String(16), nullable=True)
    data_mode = Column(String(8), nullable=False, default="mock",
                       server_default="mock")
    created_by_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class OutboxEmail(Base):
    """Todo correo que la plataforma intenta enviar.

    Resuelve dos cosas a la vez: hace **comprobable** un camino que hoy solo
    imprime por consola cuando no hay SMTP, y permite responder «¿le llegó o
    no?» cuando lo haya.

    La regla de `body` es dura: el cuerpo lleva el enlace con el token en
    claro, así que **solo se guarda en modo simulación**. Guardarlo con datos
    reales anularía el sentido de hashear el token.
    """

    __tablename__ = "outbox_emails"

    id = Column(Integer, primary_key=True)
    to_email = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=True)
    kind = Column(String, nullable=True)
    user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    sent_at = Column(DateTime, nullable=True)
    error = Column(String(300), nullable=True)


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
    #: Proveedor a cargo (E12). Va aparte de `assigned_to_user_id` y no lo
    #: sustituye: ese apunta a una persona con cuenta —el propietario o su
    #: inquilino—, y un proveedor no es ninguna de las dos cosas.
    #:
    #: Asignar un proveedor es una **anotación interna**: no le manda nada, no
    #: genera enlace y no le da acceso a la plataforma.
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=True, index=True)
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
    #: En qué momento se tomó: `report` (el inquilino al reportar), `work`
    #: (durante el trabajo) o `closing` (evidencia de cierre del propietario).
    #:
    #: Existe para separar cupos. El tope de 5 fotos por ticket era único y
    #: compartido, así que un ticket con 5 fotos del inquilino dejaba al
    #: propietario sin margen para la evidencia justo al cerrarlo.
    #:
    #: NOT NULL con DEFAULT constante: SQLite SÍ lo admite en ADD COLUMN
    #: —`main.py` ya lo hace con `is_active`— y eso evita un UPDATE de relleno.
    phase = Column(String, nullable=False, default="report", server_default="report")
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
    file_name = Column(String, nullable=True)   # nombre original recibido, saneado
    #: DEPRECADA. Se escribe NULL para siempre: su nombre promete una URL
    #: pública y estos archivos no se sirven en público jamás. No se borra
    #: porque SQLite no admite DROP COLUMN sin reconstruir la tabla, y
    #: reconstruir la de comprobantes fiscales para ahorrar una columna vacía
    #: no compensa el riesgo.
    file_url = Column(String, nullable=True)
    doc_type = Column(Enum(DocTypeEnum), nullable=True)
    meta = Column(String, nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now())

    # --- E12: lo que faltaba para adjuntar un comprobante a un ticket ---
    ticket_id = Column(Integer, ForeignKey("maintenance_tickets.id"), nullable=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    expense_id = Column(Integer, nullable=True)     # contrato con el área fiscal (E13)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=True)
    stored_path = Column(String, nullable=True)     # relativa a UPLOAD_DIR
    content_type = Column(String, nullable=True)    # distingue un PDF de un XML al entregarlo
    bytes = Column(Integer, nullable=True)
    sha256 = Column(String, nullable=True)
    # Responde «quién subió esto», que `owner_id`/`tenant_id` no responden:
    # ahí el usuario es el sujeto del documento, no quien lo cargó.
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    doc_date = Column(Date, nullable=True)          # fecha del comprobante, != uploaded_at
    #: Materializada y no calculada al vuelo: la exportación por año fiscal
    #: filtra por aquí, y un índice sobre columna es barato mientras que sobre
    #: una expresión de fecha no lo es.
    fiscal_year = Column(Integer, nullable=True, index=True)
    #: Los bytes desaparecen del disco; la constancia de que existieron, no.
    deleted_at = Column(DateTime, nullable=True)


class Visit(Base):
    __tablename__ = "visits"

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    prospect_name = Column(String, nullable=True)
    prospect_contact = Column(String, nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    status = Column(Enum(VisitStatusEnum), default=VisitStatusEnum.scheduled)
