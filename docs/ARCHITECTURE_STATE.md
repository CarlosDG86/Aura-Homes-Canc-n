# Estado de la Arquitectura — Aura Homes Cancún

> **Actualizar en el mismo commit que cualquier entrega futura.**
> Este documento es la única fuente de verdad del estado ACTUAL del código.
> Todo lo aquí escrito fue verificado contra el código fuente (no supuesto).
> Nota: la plantilla de Drive (`docs/REPORT_TEMPLATE.md`) no estaba disponible,
> así que se usa una estructura lógica limpia.

Fecha de verificación del código: 2026-08-02

---

## 1. Resumen

El repositorio contiene **dos aplicaciones independientes** que no comparten
código, configuración ni pipeline de despliegue:

1. **Sitio escaparate estático** (`data/`, `build.py`, `dist/`).
   - Generador estático en Python puro (stdlib) — `build.py` lee
     `data/site.json` (marca + tabla de strings i18n ES/EN) y
     `data/properties.json` (contenido de propiedades) y genera `dist/`.
   - Bilingüe con una carpeta por idioma (`/es`, `/en`), español por defecto.
   - Sin login, sin base de datos, sin servidor en tiempo de ejecución.
   - **Vivo** como artefacto generado; **no desplegado** en ningún lado.

2. **Plataforma FastAPI (Fase 2)** (`platform/`).
   - App Python separada con su propio `requirements.txt` y su propia
     base de datos SQLite local (`platform/data/platform.db`).
   - **Fase 2a: VIVA y funcional localmente** — login, dashboards por rol,
     gestión de usuarios/propietarios, CRUD de propiedades (tanto la tabla
     interna SQLite como el contenido real del sitio en `data/properties.json`),
     ajustes de marca (WhatsApp/correo), y correo de onboarding vía SMTP.
   - **Fase 2b (inquilinos) y 2c (pagos): solo ANDAMIADAS** — los routers
     `/api/tenant` y `/api/payments` devuelven `501` en todas sus rutas y no
     tocan ninguna tabla. Las tablas 2b/2c existen en `models.py` solo como
     forma (shape), sin CRUD que las lea o escriba.
   - **No desplegada** en ningún lado.

Regla de separación (verificada): `build.py` / `data/*.json` / `dist/` es el
mundo completo del sitio público y sigue funcionando sin modificar. La
plataforma sí LEE `data/properties.json` y `data/site.json` y sí ejecuta
`build.py` como subproceso desde el router `site_content.py` (para que el CEO
edite el contenido real del sitio desde el panel), pero el sitio estático no
importa nada de `platform/`.

---

## 2. Modelo de datos actual (`platform/app/models.py`)

ORM: SQLAlchemy 2.0 sobre SQLite (un solo archivo local). No hay Alembic;
las tablas se crean con `Base.metadata.create_all()` al arrancar, más una
micro-migración manual para `site_ref` (ver §5 y `main.py`).

### Enums (todos `str, enum.Enum`)

| Enum | Valores |
|---|---|
| `RoleEnum` | `admin`, `owner`, `tenant` |
| `PropertyStatusEnum` | `available`, `rented` |
| `LeaseStatusEnum` | `active`, `ended` |
| `TicketStatusEnum` | `open`, `in_progress`, `resolved` |
| `PaymentStatusEnum` | `received`, `pending_review` |
| `DocTypeEnum` | `contract`, `id_verification`, `policy`, `receipt`, `other` |
| `VisitStatusEnum` | `scheduled`, `completed`, `cancelled` |

### Tablas 2a — modeladas y en uso por `admin.py` / `owner.py` / `pages.py`

**`User`** (tabla `users`) — es a la vez el Administrador, el Propietario y
(a futuro) el Inquilino; se distinguen por `role`.

| Campo | Tipo | Notas |
|---|---|---|
| `id` | Integer, PK | |
| `name` | String, NOT NULL | |
| `email` | String, unique, NOT NULL, index | identificador de login (se guarda en minúsculas) |
| `phone` | String, nullable | |
| `password_hash` | String, NOT NULL | bcrypt (nunca texto plano) |
| `role` | Enum(`RoleEnum`), NOT NULL | admin / owner / tenant |
| `created_at` | DateTime | `server_default=now()` |
| `updated_at` | DateTime | `onupdate=now()` |

Relación: `User.properties` → `Property` (`back_populates="owner"`,
`cascade="all, delete-orphan"`). Borrar un usuario borra sus propiedades.

**`Property`** (tabla `properties`).

| Campo | Tipo | Notas |
|---|---|---|
| `id` | Integer, PK | |
| `owner_id` | Integer, FK→`users.id`, NOT NULL, index | dueño de la propiedad |
| `site_ref` | String, **nullable, unique, index** | liga a la propiedad del sitio público (`data/properties.json` "id", p. ej. `"AUR-001"`). NULL si la propiedad se creó solo dentro de la plataforma. El JSON del sitio sigue siendo la fuente de verdad del contenido público; esta fila es un espejo del lado de gestión, refrescado por la acción "sync site properties". |
| `title` | String, NOT NULL | |
| `zone` | String, nullable | |
| `city` | String, default `"Cancún"` | |
| `price_amount` | Numeric(12,2), nullable | |
| `price_currency` | String, default `"MXN"` | |
| `status` | Enum(`PropertyStatusEnum`), default `available` | |
| `bedrooms` | Integer, nullable | |
| `bathrooms` | Numeric(3,1), nullable | |
| `area_m2` | Numeric(8,2), nullable | |
| `description` | Text, nullable | |
| `created_at` / `updated_at` | DateTime | |

Relaciones: `Property.owner` → `User`; `Property.images` → `PropertyImage`
(cascade delete-orphan); `Property.team_members` → `PropertyTeamMember`
(cascade delete-orphan).

**`PropertyImage`** (tabla `property_images`): `id`, `property_id`
(FK→`properties.id`), `url` (String, NOT NULL), `sort_order` (Integer,
default 0). Existe modelada pero **no la usa ningún router hoy** — el sitio
público guarda las fotos como archivos en `dist/assets/img/<id>/`, no aquí.

**`PropertyTeamMember`** (tabla `property_team_members`): `id`, `property_id`
(FK→`properties.id`), `user_id` (FK→`users.id`), `role_description` (String,
nullable). Junta "personas a las que el propietario delega la gestión".
Modelada pero **sin CRUD todavía**.

### Tablas 2b / 2c — existen solo como forma (shape), sin CRUD

Ningún router las lee ni escribe; `tenant.py` y `payments.py` devuelven `501`
en cada ruta. Se conservan para que la forma del módulo exista en paralelo a
la revisión de Legal, conforme al plan.

- **`Lease`** (`leases`): `id`, `property_id` (FK), `tenant_id` (FK→users),
  `start_date`, `end_date`, `monthly_rent` (Numeric), `status`
  (`LeaseStatusEnum`, default `active`).
- **`MaintenanceTicket`** (`maintenance_tickets`): `id`, `property_id` (FK),
  `reported_by_user_id` (FK→users), `title` (NOT NULL), `description` (Text),
  `status` (`TicketStatusEnum`, default `open`), `created_at`, `updated_at`.
- **`Payment`** (`payments`): `id`, `lease_id` (FK), `amount` (Numeric),
  `currency` (default `MXN`), `payment_date`, `status` (`PaymentStatusEnum`,
  default `pending_review`), `receipt_document_id` (FK→`documents.id`, nullable).
- **`Document`** (`documents`): `id`, `property_id` (FK, nullable), `owner_id`
  (FK→users, nullable), `tenant_id` (FK→users, nullable), `file_name`,
  `file_url`, `doc_type` (`DocTypeEnum`, nullable), `meta` (String),
  `uploaded_at`.
- **`Visit`** (`visits`): `id`, `property_id` (FK), `prospect_name`,
  `prospect_contact`, `scheduled_at`, `status` (`VisitStatusEnum`, default
  `scheduled`).

> Nota: `DB_SCHEMA.md` (propuesta) menciona además `notifications` y
> `messages`; esas tablas **no** están implementadas en `models.py` todavía.

---

## 3. La segunda app / API que ya corre

Entrypoint: `platform/app/main.py`, ejecutable con
`uvicorn app.main:app --reload --port 8010` desde `platform/`.
Routers montados en `main.py`: `auth` (prefijo `/api/auth`), `admin`,
`owner`, `tenant`, `payments`, `pages`, `site_content`.

`GET /` redirige a `/login`. `GET /api/health` devuelve `{"status": "ok"}`.

### API JSON

| Ruta | Método | Auth / rol | Estado |
|---|---|---|---|
| `/api/auth/login` | POST | pública (valida credenciales) | vivo |
| `/api/auth/logout` | POST | sesión | vivo |
| `/api/auth/me` | GET | logueado | vivo |
| `/api/admin/properties` | GET | admin | vivo |
| `/api/admin/properties` | POST | admin | vivo (exige `owner_id` con rol owner) |
| `/api/admin/properties/{id}` | GET | admin | vivo |
| `/api/admin/properties/{id}` | PUT | admin | vivo |
| `/api/admin/properties/{id}` | DELETE | admin | vivo |
| `/api/admin/owners` | GET | admin | vivo (lista users con rol owner) |
| `/api/admin/users` | GET | admin | vivo |
| `/api/admin/users` | POST | admin | vivo (crea usuario con rol; 409 si el correo existe) |
| `/api/owner/properties` | GET | owner o admin | vivo (scope `owner_id == current_user.id`) |
| `/api/owner/properties` | POST | owner o admin | vivo |
| `/api/owner/properties/{id}` | GET | owner o admin | vivo (scoped) |
| `/api/owner/properties/{id}` | PUT | owner o admin | vivo (scoped) |
| `/api/owner/properties/{id}` | DELETE | owner o admin | vivo (scoped) |
| `/api/tenant` y `/api/tenant/{path}` | GET/POST/PUT/DELETE/PATCH | — | **stub 501** (2b, pendiente Legal) |
| `/api/payments` y `/api/payments/{path}` | GET/POST/PUT/DELETE/PATCH | — | **stub 501** (2c, pendiente Legal) |

Todas las rutas de `/api/admin/*` están gateadas a nivel de router con
`dependencies=[Depends(require_role("admin"))]`.

### Páginas server-rendered (Jinja2, `include_in_schema=False`)

Fuente: `routers/pages.py` (login, dashboards, alta de propietario, sync,
administración de usuarios) y `routers/site_content.py` (contenido real del
sitio + ajustes de marca). El gating de páginas usa redirecciones (a `/login`
o al home del rol) en vez de lanzar 401/403.

| Ruta | Método | Auth / rol | Estado |
|---|---|---|---|
| `/login` | GET | pública | vivo (redirige si ya hay sesión) |
| `/login` | POST | pública | vivo (fija cookie, redirige por rol) |
| `/logout` | GET | sesión | vivo |
| `/admin` | GET | admin | vivo (dashboard: propiedades, owners, users, filas de sync del sitio) |
| `/admin/owners` | POST | admin | vivo (alta de propietario + correo de clave temporal) |
| `/admin/sync-site-properties` | POST | admin | vivo (sync selectivo por checkbox de casas del sitio a un owner elegido) |
| `/admin/users/{id}` | GET | admin | vivo (formulario de edición de usuario) |
| `/admin/users/{id}` | POST | admin | vivo (actualiza datos+rol; bloquea degradar al último admin) |
| `/admin/users/{id}/password` | POST | admin | vivo (restablece clave, correo opcional) |
| `/admin/users/{id}/properties` | POST | admin | vivo (reasigna propiedades a un usuario) |
| `/owner` | GET | owner o admin | vivo (scope `owner_id == user.id`) |
| `/admin/properties` | GET | admin | vivo (lista de propiedades REALES del sitio, `data/properties.json`) |
| `/admin/properties/new` | GET/POST | admin | vivo (alta con fotos + rebuild) |
| `/admin/properties/{id}/edit` | GET/POST | admin | vivo (edición con fotos + rebuild) |
| `/admin/properties/{id}/delete` | POST | admin | vivo (elimina + rebuild) |
| `/admin/site-settings` | GET/POST | admin | vivo (edita WhatsApp + correo en `data/site.json`, luego rebuild) |

Nota importante sobre las **dos CRUD de propiedades** (verificado):
- `routers/admin.py` (`/api/admin/properties*`) opera la **tabla SQLite
  `properties`** (el espejo de gestión, para trabajo futuro de cuentas 2b/2c).
- `routers/site_content.py` (`/admin/properties*`) opera el **contenido real
  del sitio público** en `data/properties.json`, escribe fotos en
  `dist/assets/img/<id>/` y re-ejecuta `build.py` en cada cambio (con reversión
  atómica: si el build falla, restaura el JSON previo y no deja fotos huérfanas).
  La tabla SQLite NO se toca desde este archivo.

`site_content.py` también valida el número de WhatsApp (10–15 dígitos, `+`
opcional, normalizado a E.164) y sirve, en modo solo-lectura, las fotos del
sitio en `/site-images` (montado en `main.py` desde `dist/assets/img`) para
las miniaturas del panel.

---

## 4. Autenticación y roles implementados (`platform/app/auth.py`)

- **Sesión:** cookie firmada del lado del servidor vía Starlette
  `SessionMiddleware` (nombre de cookie `aura_platform_session`,
  `same_site="lax"`, `secret_key` desde `SECRET_KEY`). No hay OAuth, JWT ni
  flujo de recuperación de contraseña por autoservicio (fuera de alcance 2a).
- **Hashing:** `passlib` con esquema `bcrypt` (`hash_password` /
  `verify_password`). Nunca se guarda texto plano.
- **`get_current_user`:** resuelve el usuario desde `request.session["user_id"]`,
  o lanza 401.
- **`require_role(*roles)`:** fábrica de dependencia FastAPI — 401 si no hay
  sesión, 403 si el rol no está permitido. Uso: `Depends(require_role("admin"))`.
- **Scoping del owner:** en `owner.py` y en el dashboard `/owner` de
  `pages.py`, TODA consulta filtra por `Property.owner_id == current_user.id`,
  incluso para el admin que use ese router. Esto es lo que realmente impide la
  fuga de datos entre propietarios; la capacidad del admin de "ver todo" vive
  en `admin.py`, no en `owner.py`.
- **Roles (`RoleEnum`):**
  - `admin` — **en uso**. Acceso total; se siembra uno al arrancar.
  - `owner` — **en uso**. Login, ve/gestiona solo sus propias propiedades.
  - `tenant` — **definido pero NO en uso**. No hay flujo de alta ni portal de
    inquilino (2b andamiado, `501`).
- **Semilla:** al arrancar, si no existe ningún admin, se crea uno
  (`SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`, por defecto
  `admin@aura-homes-cancun.local` / `ChangeMe123!`) e imprime las credenciales
  en consola. Debe cambiarse antes de cualquier despliegue real.

---

## 5. Estado de infraestructura y despliegue actual

> **Complementado por Infra (evaluación 2026-08-02).** Resumen desde el repo,
> con la evaluación del equipo Infra incorporada en las subsecciones al final
> (backups, brechas de despliegue, decisiones). Ver también
> `docs/phase2/INFRA_STACK.md`.

Resumen desde el código actual:

- **Base de datos:** SQLite local en `platform/data/platform.db` (gitignored,
  nunca commiteado). URL configurable por `DATABASE_URL`, con default a ese
  archivo. Acceso vía SQLAlchemy (portable a Postgres a futuro con cambio de
  config, no reescritura).
- **Micro-migración:** no hay Alembic. `_ensure_property_site_ref()` en
  `main.py` hace un `ALTER TABLE properties ADD COLUMN site_ref` idempotente
  (revisa `PRAGMA table_info` primero) para bases creadas antes de esa columna.
  Corre en el evento `startup` junto con `create_all()` y la semilla del admin.
- **Servidor:** uvicorn en el puerto **8010** (deliberado: el preview del
  sitio estático corre en el 8000, para poder correr ambos a la vez).
- **Dependencias (pinneadas, `platform/requirements.txt`):** `fastapi==0.115.0`,
  `uvicorn[standard]==0.32.0`, `sqlalchemy==2.0.35`, `passlib[bcrypt]==1.7.4`,
  `bcrypt==4.0.1` (pin explícito por incompatibilidad de passlib 1.7.4 con
  bcrypt≥4.1), `python-multipart==0.0.12`, `itsdangerous==2.2.0`, `jinja2==3.1.4`.
- **Configuración / secretos:** cargador `.env` mínimo en `main.py`
  (`_load_dotenv`, sin dependencia `python-dotenv`); lee `platform/.env` si
  existe y no pisa variables ya definidas en el entorno. `platform/.env` está
  gitignored. Variables relevantes: `SECRET_KEY`, `DATABASE_URL`,
  `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`, y las `SMTP_*`.
- **Correo (`email_utils.py`):** envío vía `smtplib` de la stdlib (sin nueva
  dependencia), configurado por `SMTP_HOST`, `SMTP_PORT` (default 587),
  `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS`. Sin `SMTP_HOST`
  corre en **modo dev**: no envía nada, registra/imprime el mensaje que se
  habría enviado y reporta `configured=False`. Nunca lanza excepción, así que
  un fallo de correo no rompe el alta de usuario.
- **Sitio estático:** `build.py` genera `dist/` desde `data/`. **No desplegado.**
  Objetivo declarado: hosting free-tier estático (Netlify/Vercel/Cloudflare).
- **Despliegue de la plataforma:** **ninguno.** Nada está desplegado,
  provisionado ni comprado. Recomendación de Infra (no ejecutada): Fly.io por
  la persistencia de volumen en free-tier que necesita SQLite. Cualquier
  despliegue requiere sign-off de QA y aprobación explícita del CEO.
- **Puertos:** plataforma en 8010, preview del sitio en 8000 (coexisten).
- **Runtime:** Python 3.12, venv en `platform/.venv` (gitignored).
- **Bandera de seguridad:** `SECRET_KEY` tiene default inseguro
  (`dev-insecure-secret-key-change-me`) que firma la cookie de sesión — debe
  reemplazarse por un valor real y fuera del repo antes de exponer la plataforma.

### Backups (evaluación de Infra)

- **No hay proceso formal de backup** de `platform.db` (sin cron, sin
  rotación, sin copia off-site).
- Existen respaldos **ad-hoc manuales** junto al `.db` activo (p. ej.
  `platform/data/platform.db.bak-20260728-003209`).
- Nota crítica: `platform.db` **ya contiene datos reales de owners del CEO** —
  hacer snapshot antes de cualquier prueba que escriba en la base.

### Qué falta para desplegar (evaluación de Infra)

- **Fase 1 — sitio estático (`dist/`):** elegir host free-tier
  (Netlify / Vercel / Cloudflare Pages), build reproducible desde clon limpio
  (`python build.py` → publicar `dist/`), dominio + DNS (acción del CEO).
  Pendientes de sitio a coordinar con Dev: headers de seguridad, sitemap/robots.
- **Fase 2 — plataforma:** definir host con **disco durable** para SQLite
  (tensión free-tier real, `INFRA_STACK.md` §5: Render free sin disco
  persistente vs. Fly.io con volumen en free-tier — recomendación de Infra:
  Fly.io, no ejecutada); `SECRET_KEY` real fuera del repo; cambiar credenciales
  seed del admin; SMTP productivo; decidir si se necesita Alembic antes de
  datos reales. Requiere QA sign-off + aprobación del CEO (y Legal para 2b/2c).

### Decisiones de infraestructura para el CEO

1. Host del sitio estático (Netlify / Vercel / Cloudflare Pages).
2. Dominio y DNS (compra y configuración — solo el CEO).
3. Host de la plataforma: **Fly.io** (volumen persistente en free-tier) vs.
   **Render** (BD efímera + backup manual) vs. plan de pago con disco durable.
   Afecta directamente la durabilidad de `platform.db`.
4. Política de backups de `platform.db` (frecuencia, destino off-site).
5. Proveedor SMTP productivo y quién lo administra.
