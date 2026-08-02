# Fase 2 — Propietarios y Tickets de Mantenimiento (propuesta de diseño)

> **Estado: PROPUESTA para revisión del CEO. No es código construido.**
> Describe cómo enrutar tickets de mantenimiento a cada propietario y cómo
> darles seguimiento. Se apoya en lo que YA existe en `platform/app/models.py`
> y marca con claridad qué cambios/campos nuevos harían falta.
> Alineado con `docs/phase2/PLAN.md` (2b va con gating de Legal).

Fecha: 2026-08-02

---

## 0. Contexto en una línea

Cada **Casa** (`Property`) ya está ligada a un **Propietario** (`owner_id`).
Cada **Ticket** (`MaintenanceTicket`) ya tiene `property_id`, así que un ticket
llega a su propietario **a través de la casa**. La pieza que falta no es el
modelo base, sino: (a) el enrutamiento/notificación al crear el ticket, (b) una
vía de entrada abierta (sin login) que vincule por teléfono + propiedad, y
(c) el portal de owners para dar seguimiento.

---

## 1. Modelo de datos

### Qué YA existe (verificado en `models.py`)

- **`User`** con `role` (`RoleEnum`: admin/owner/tenant), `name`, `email`,
  `phone` (nullable), `password_hash`. Un mismo `users` para los tres roles.
- **`Property`** con `owner_id` (FK→users, NOT NULL), `site_ref` (liga al id
  del sitio público, p. ej. `AUR-001`), `title`, `zone`, `status`, etc.
  Relación `Property.owner` ↔ `User.properties`.
- **`MaintenanceTicket`** (`maintenance_tickets`): `id`, `property_id` (FK),
  `reported_by_user_id` (FK→users, **NOT NULL**), `title`, `description`,
  `status` (`TicketStatusEnum`: open/in_progress/resolved), `created_at`,
  `updated_at`.
- **`Lease`** (`leases`): liga `tenant_id` ↔ `property_id` con `status`
  (active/ended). Es el puente natural "qué inquilino vive en qué casa".

La cadena de propiedad ya es sólida:
`Ticket.property_id → Property.owner_id → User (owner)`.
Identificar al propietario de un ticket es una sola consulta; no requiere
cambios de esquema.

### Qué CAMBIOS / CAMPOS NUEVOS harían falta (gap actual → requerido)

1. **Teléfono del inquilino en el ticket (vía abierta).** Hoy
   `MaintenanceTicket.reported_by_user_id` es **NOT NULL** y asume que quien
   reporta es un usuario logueado. Para la vía abierta (sin login) no hay
   usuario. Cambios propuestos:
   - Hacer `reported_by_user_id` **nullable**.
   - Añadir `reporter_name` (String, nullable) y `reporter_phone` (String,
     nullable) para capturar el contacto del inquilino no logueado.
   - Añadir `source` (Enum: `tenant_portal` / `open_form`) para saber por qué
     vía entró.

2. **Estado de asignación / fallback.** Añadir a `MaintenanceTicket`:
   - `assigned_owner_id` (FK→users, nullable) — el propietario resuelto al que
     se enrutó. NULL cuando el matching falla y el ticket cae con el CEO.
   - `assignment_status` (Enum: `auto_assigned` / `unassigned_ceo_review` /
     `manually_assigned`) — para que el CEO vea de un vistazo qué tickets
     necesitan asignación manual.

3. **Teléfono normalizado para hacer match.** El match de la vía abierta es por
   teléfono. Conviene almacenar un teléfono canónico (solo dígitos / E.164)
   para comparar sin ruido de formato:
   - Opción A: `User.phone_normalized` (String, nullable, index) además del
     `phone` legible.
   - Opción B: normalizar al vuelo en la consulta (más simple, sin migración,
     pero menos robusto). Recomendación: Opción A si el volumen crece.
   Ya existe la regex de normalización de WhatsApp en `site_content.py`
   (`WHATSAPP_RE`, normalización a E.164) — se puede reutilizar el mismo
   criterio.

4. **Relación explícita inquilino↔casa para la vía logueada.** Se resuelve por
   `Lease` (tenant_id + property_id, status=active). No requiere campo nuevo,
   pero **2b/Legal debe habilitar** el alta real de inquilinos y leases (hoy
   `tenant` es un rol definido pero sin flujo, y `Lease` es solo shape).

5. **Contacto del propietario para notificar.** `User.phone` ya existe; para
   WhatsApp conviene el mismo teléfono normalizado del punto 3. El correo ya
   está en `User.email`.

> Ninguno de estos cambios rompe el shape actual: son columnas nullable
> añadidas y un aflojamiento de un NOT NULL. Como no hay Alembic, se aplicarían
> con el mismo patrón de micro-migración idempotente que
> `_ensure_property_site_ref()` en `main.py`.

---

## 2. Enrutamiento de tickets

Al crear un ticket, el sistema:

1. Toma `property_id` del ticket.
2. Resuelve la casa y su `owner_id` → obtiene al **Propietario**.
3. **Notifica directo al propietario** (correo y, a futuro, WhatsApp).
4. **El CEO (admin) siempre recibe copia** de toda notificación de ticket.

### Mecanismo de notificación

- **Correo — reutilizar `email_utils.py`.** Ya existe el patrón: composición
  de mensaje + envío por `smtplib`, configurado por `SMTP_*`, con modo dev
  cuando no hay SMTP (no envía, solo registra) y sin lanzar excepción ante
  fallos. Se añadiría una función `send_ticket_notification(...)` análoga a
  `send_temp_password_email(...)`, con destinatarios = propietario + copia al
  correo del CEO (de `data/site.json → brand.email`, o de una variable
  `CEO_NOTIFY_EMAIL`).
- **WhatsApp — integración PENDIENTE.** Hoy el sitio solo usa **deep links**
  `wa.me` (ver `build.py`, `wa_link()`), que abren una conversación pero **no
  envían automáticamente**. Enviar un WhatsApp saliente sin intervención humana
  requiere la WhatsApp Business API (o un proveedor tipo Twilio/Meta), que es
  costo + alta + revisión aparte. Propuesta por fases:
  - **Ahora:** notificar por correo; en el panel del ticket, mostrar un botón
    `wa.me` prellenado hacia el teléfono del inquilino/propietario (deep link,
    igual que el sitio) para que el propietario responda con un toque.
  - **Después (opcional):** WhatsApp saliente automático vía Business API,
    como decisión separada de Infra + CEO (costo recurrente).

---

## 3. Dos vías de entrada

### (a) Inquilino logueado — identidad y casa conocidas

- El inquilino inicia sesión (rol `tenant`, 2b).
- Su casa se conoce por su `Lease` activo (`tenant_id` + `property_id`,
  `status=active`).
- El ticket se crea con `reported_by_user_id` = inquilino, `property_id` = su
  casa, `source=tenant_portal`, y se enruta **directo** al propietario de esa
  casa. `assignment_status=auto_assigned`.
- Es el camino limpio: sin ambigüedad, sin matching.

### (b) Formulario abierto sin login — selección de propiedad + teléfono

Pensado para el inquilino que aún no tiene cuenta (o que no quiere loguearse).

- **La propiedad se SELECCIONA de una lista (dropdown), no texto libre.** La
  lista se arma de las propiedades reales (`data/properties.json` / la tabla
  espejo `properties`), mostrando título y zona. Esto garantiza que el ticket
  siempre trae un `property_id` válido y evita errores de tipeo. **Nunca**
  campo de texto libre para la propiedad.
- **El inquilino da su teléfono** (obligatorio) y su nombre.
- **Lógica de matching (vincular por teléfono + propiedad):**
  1. Se tiene ya el `property_id` (del dropdown) y por tanto el `owner_id`.
  2. Se normaliza el teléfono capturado.
  3. Se busca un `Lease` activo en esa propiedad cuyo inquilino tenga ese
     teléfono normalizado:
     - **Match:** se vincula `reported_by_user_id` al inquilino encontrado,
       `assignment_status=auto_assigned`, y se enruta al propietario de la casa.
     - **Sin match de inquilino, pero propiedad válida:** igual se conoce el
       `owner_id` (la propiedad lo determina), así que **se enruta al
       propietario** con los datos de contacto capturados
       (`reporter_name` / `reporter_phone`), `assignment_status=auto_assigned`.
       El propietario decide si es un inquilino legítimo.
  4. **Fallback / red de seguridad:** si por alguna razón no se puede resolver
     un propietario (p. ej. propiedad sin `owner_id`, dato inconsistente, o
     regla de negocio que exija verificación), el ticket se guarda con
     `assigned_owner_id=NULL` y `assignment_status=unassigned_ceo_review`, y
     **cae con el CEO (admin)** para asignación manual. El CEO nunca pierde un
     ticket: siempre recibe copia y ve la cola de "por asignar".

> Decisión de producto abierta (ver §6): en la vía abierta, ¿el propietario
> siempre puede ver un ticket de una persona que dice ser su inquilino aunque
> el teléfono no coincida, o esos casos van primero al CEO para filtrar? La
> propuesta anterior asume "sí al propietario, porque la propiedad ya lo
> determina", con el CEO en copia.

---

## 4. Portal de owners (seguimiento de SUS tickets)

- **Login** con el rol `owner` (ya existe en `RoleEnum`, separado del
  Administrador). El propietario ya puede iniciar sesión hoy (2a).
- **Ver y dar seguimiento a SUS propios tickets**, con el **mismo patrón de
  scoping que `owner.py`**: toda consulta filtra por el propietario logueado.
  Para tickets, el filtro es
  `MaintenanceTicket.property_id IN (casas del owner)` — equivalente a
  `Property.owner_id == current_user.id`. Este scoping por `owner_id` es
  exactamente lo que hoy impide la fuga entre propietarios en `/api/owner/*` y
  en el dashboard `/owner`.
- **Acciones del propietario sobre un ticket:** cambiar `status`
  (open → in_progress → resolved), leer descripción y contacto del inquilino,
  y (deep link `wa.me`) responder por WhatsApp.
- **El Administrador (CEO)** ve todos los tickets, incluida la cola
  `unassigned_ceo_review`, y puede reasignar — mismo patrón que hoy usa
  `pages.py` para reasignar propiedades a un usuario
  (`/admin/users/{id}/properties`).

---

## 5. Fases y gating

- Esto pertenece a **Fase 2b** (portal de inquilino + tickets de mantenimiento)
  según `docs/phase2/PLAN.md`, y se construye **EN PARALELO** sin bloquear el
  lanzamiento de **Fase 1** (sitio escaparate estático + botón/deep link de
  WhatsApp), que es independiente y no toca la base de datos.
- **Gating de Legal (obligatorio):** 2b introduce **PII de inquilinos**
  (nombre, teléfono, relación con una casa). Conforme a `PLAN.md` y a
  `CLAUDE.md`:
  - Se puede **andamiar el módulo y el esquema ahora** (columnas nuevas,
    routers, lógica de matching), como ya se hizo con `tenant.py`/`Lease`.
  - **NO** almacenar PII real de inquilinos ni ir a producción con cuentas o
    tickets reales **hasta que Legal apruebe** (LFPDPPP). El andamiaje actual
    (`/api/tenant` → 501, sin lógica que escriba datos) es precisamente lo que
    garantiza que no se filtre nada por accidente.
  - La vía abierta (formulario sin login) también captura PII (teléfono del
    inquilino), así que **queda bajo el mismo gating de Legal** — no se activa
    con datos reales antes del visto bueno.
- La aprobación de este documento NO es luz verde para lanzar 2b con datos
  reales; eso requiere una confirmación explícita adicional del CEO una vez que
  Legal firme.

---

## 6. Decisiones que el CEO debe tomar

1. **Canal de notificación al propietario:** ¿basta con correo por ahora (vía
   `email_utils`) + botón `wa.me` para que el propietario responda, o el CEO
   quiere WhatsApp saliente automático (Business API, costo recurrente + alta
   aparte) desde el inicio?
2. **Copia al CEO:** ¿el admin recibe copia de **todos** los tickets, o solo de
   los que caen en la cola `unassigned_ceo_review`? (La propuesta asume: de
   todos.)
3. **Vía abierta sin match de inquilino:** cuando el teléfono no coincide con
   ningún inquilino de esa casa, ¿se enruta igual al propietario (con el CEO en
   copia) o va primero al CEO para filtrar antes de pasarlo al propietario?
4. **Verificación del reportante en la vía abierta:** ¿se requiere algún dato
   extra (p. ej. número interior/depto, o los últimos 4 dígitos de un
   contrato) para reducir tickets falsos, o basta teléfono + propiedad?
5. **Correo del CEO para copias:** ¿usar `brand.email` de `data/site.json`
   (`hola@aurahomescancun.com`) o un correo interno distinto
   (`CEO_NOTIFY_EMAIL`) que no sea el público de contacto?
6. **Modelo de inquilino (depende de Legal):** ¿el inquilino tiene cuenta con
   login (rol `tenant`, vía logueada completa) o, para minimizar PII, se ofrece
   SOLO la vía abierta por formulario hasta que Legal apruebe cuentas de
   inquilino?
7. **Alcance de estado del ticket para el propietario:** ¿el propietario puede
   marcar `resolved` por sí mismo, o solo el CEO cierra tickets?
