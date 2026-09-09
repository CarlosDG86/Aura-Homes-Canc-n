# Fase 2.1 · Esquema unificado y plan de migración

**Fecha:** 2026-09-08 · **Estado:** cerrado, listo para construir
**Fuente:** fusión de los cinco diseños de área (A–E). Resuelve 12 conflictos entre ellos.

> Este documento manda sobre el modelo de datos que aparezca en cualquier documento de área.
> Donde un área diga otra cosa, vale lo escrito aquí.

---

## Esquema unificado — Fase 2b/2c ampliada

Convenciones aplicadas a todo lo de abajo, verificadas contra el repo:
- Tabla **nueva** → nace de `Base.metadata.create_all()` (main.py:227) y **sí admite NOT NULL**.
- Columna **añadida por ALTER** → obligatoriamente nullable, **o** NOT NULL con DEFAULT constante (precedente real: `main.py:162` ejecuta `ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1`).
- Ningún `Enum()` de SQLAlchemy en columnas nuevas: todas VARCHAR validadas en Python.
- `PRAGMA foreign_keys = 0` verificado en ambas bases → las `ForeignKey()` son declarativas, no imponen nada.

---

### 1. Tablas NUEVAS (12)

#### 1.1 `accounts` — área A (raíz de aislamiento D-013)
| columna | tipo | null | notas |
|---|---|---|---|
| id | INTEGER PK | no | |
| name | VARCHAR | no | |
| plan | VARCHAR | no, default `'trial'` | lista blanca al escribir; desconocido al leer degrada a `trial` |
| status | VARCHAR | no, default `'activa'` | activa\|suspendida\|cerrada; desconocido degrada a `suspendida` |
| trial_days | INTEGER | no, default 90 | |
| trial_started_at / trial_ends_at | DATETIME | sí | `trial_ends_at` **materializado** |
| trial_property_id | INTEGER | sí | 7.1: la prueba es de UNA casa |
| properties_max_override | INTEGER | sí | |
| is_operator | BOOLEAN | no, default 0 | única cuenta que puede escribir `site_ref` |
| primary_user_id | INTEGER | sí | |
| country | VARCHAR | sí, default `'MX'` | |
| default_tax_jurisdiction | VARCHAR | sí, default `'MX'` | **área B, fundida aquí** — MX\|US\|BOTH |
| base_currency | VARCHAR | sí, default `'MXN'` | **área B, fundida aquí** |
| plan_assigned_at / plan_assigned_by_user_id | DATETIME / INTEGER | sí | |
| plan_note | VARCHAR(500) | sí | rechaza secuencias de 13-19 dígitos |
| created_in_db | VARCHAR | sí | basename del archivo de base |
| created_by_user_id | INTEGER | sí | |
| created_at / updated_at | DATETIME | | |

**PROHIBIDO por diseño:** cualquier columna de importe, moneda de cobro, ciclo, IBAN, CLABE, tarjeta, RFC, EIN o domicilio fiscal.

#### 1.2 `account_plan_events` — área A (append-only)
`id PK · account_id INTEGER NOT NULL idx · from_plan/to_plan VARCHAR NULL · from_trial_ends_at/to_trial_ends_at DATETIME NULL · from_status/to_status VARCHAR NULL · note TEXT NULL · actor_user_id INTEGER NULL · created_at DATETIME`

#### 1.3 `providers` — área C (**absorbe la tabla que el área B llamaba `vendors`**)
`id PK · account_id INTEGER NOT NULL idx · name VARCHAR NOT NULL · contact_name VARCHAR NULL · trade VARCHAR NULL · phone VARCHAR NULL · email VARCHAR NULL (sin UNIQUE) · tax_id VARCHAR NULL · notes TEXT NULL · is_active BOOLEAN NOT NULL default 1 · archived_at DATETIME NULL · redacted_at DATETIME NULL · created_by_user_id INTEGER NULL · created_at/updated_at DATETIME`

`trade` se valida en Python contra los 7 nombres de `TicketCategoryEnum` (models.py:361-368) + `'otro'`. Prohibidos CLABE, cuenta bancaria y domicilio.

#### 1.4 `ticket_quotes` — área C (andamiaje del 7.4)
`id PK · account_id INTEGER NOT NULL idx · ticket_id INTEGER NOT NULL idx · provider_id INTEGER NULL · provider_name_snapshot VARCHAR NOT NULL · status VARCHAR NOT NULL default 'borrador' · source VARCHAR NOT NULL default 'manual' · amount NUMERIC(14,2) NULL · currency VARCHAR(3) default 'MXN' · valid_until DATE NULL · scope_notes TEXT NULL · attachment_id INTEGER NULL · requested_at/responded_at/decided_at DATETIME NULL · requested_by_user_id/decided_by_user_id INTEGER NULL`

Cambio respecto al diseño C: `document_id` → **`attachment_id`** (ver 1.6). `amount` a NUMERIC(14,2) para cuadrar con `expenses`.

#### 1.5 `expenses` — **áreas B + C fundidas** (esta es la fusión más cara si se equivoca)
| columna | tipo | null | quién la pidió |
|---|---|---|---|
| id | INTEGER PK | no | B |
| account_id | INTEGER idx | **sí** (DDL) | A/B/C — ver nota |
| property_id | INTEGER idx | no | B/C |
| ticket_id | INTEGER idx | sí | B/C |
| expense_date | DATE | no | B/C |
| **tax_year** | INTEGER idx | no | B (**gana** sobre `fiscal_year` de C) |
| category_code | VARCHAR(40) | no | B |
| **provider_id** | INTEGER (sin FK) | sí | C (**gana** sobre `vendor_id` de B) |
| **provider_name_snapshot** | VARCHAR(160) | sí | C (**gana** sobre `vendor_name_raw` de B) |
| tax_doc_ref | VARCHAR(64) | sí | B |
| amount | NUMERIC(14,2) | no | B (**gana** sobre 12,2 de C) |
| currency | VARCHAR(3) | no, default 'MXN' | B/C |
| base_currency | VARCHAR(3) | no | B |
| amount_base | NUMERIC(14,2) | sí | B — vacío antes que inventado |
| fx_rate / fx_rate_date / fx_source | NUMERIC(18,8) / DATE / VARCHAR(40) | sí | B |
| is_capital | BOOLEAN | no, default 0 | B |
| payment_method | VARCHAR(30) | sí | B |
| note | TEXT | sí | B |
| status | VARCHAR(16) | no, default 'confirmado' | B |
| adjusts_expense_id | INTEGER | sí | B |
| data_mode | VARCHAR(8) | no | B (sello D-016) |
| voided_at / voided_by_user_id / voided_reason | DATETIME / INTEGER / VARCHAR(200) | sí | B — no hay DELETE |
| created_by_user_id / created_at / updated_at | | | B/C |

**Nota sobre `account_id`:** el DDL lo deja nullable (el área B lo exigía así para no acoplar el orden de construcción), pero el **escritor siempre lo rellena** desde `user.account_id` y `scoped_expenses()` devuelve **503 diagnosticable** si `user.account_id IS NULL` (semántica de fallo cerrado que exigía el área C). No lleva columna `locked`: el bloqueo se deriva de `fiscal_year_closures`.

#### 1.6 `attachments` — **áreas B + C fundidas; tabla NUEVA que sustituye a las dos propuestas**
El área C quería reutilizar `documents`; el área B quería crear `expense_receipts`. Ninguna de las dos: ver `conflictos` #3.

`id PK · account_id INTEGER NULL idx · kind VARCHAR(10) NOT NULL ('imagen'|'pdf'|'xml') · purpose VARCHAR(20) NOT NULL ('factura'|'cotizacion'|'recibo'|'garantia'|'otro') · ticket_id INTEGER NULL idx · expense_id INTEGER NULL idx · provider_id INTEGER NULL · property_id INTEGER NULL · stored_path VARCHAR NOT NULL · file_name VARCHAR(200) NULL · content_type VARCHAR(80) NOT NULL · bytes INTEGER NOT NULL · sha256 VARCHAR(64) NOT NULL · recoded BOOLEAN NOT NULL default 0 · doc_date DATE NULL · tax_year INTEGER NULL idx · uploaded_by_user_id INTEGER NULL · deleted_at DATETIME NULL · created_at DATETIME`

`tenant_id` **no existe** aquí, deliberadamente (minimización: el comprobante del plomero no arrastra la identidad del inquilino a la exportación del contador). `account_id` presente pese a la regla del área A porque la tabla cuelga de **tres** padres distintos y la exportación fiscal filtra por `(account_id, tax_year)`.

#### 1.7 `fx_rates` — área B
`id PK · account_id INTEGER NULL · currency_from/currency_to VARCHAR(3) NOT NULL · rate_date DATE NOT NULL · rate NUMERIC(18,8) NOT NULL · kind VARCHAR(16) NOT NULL · tax_year INTEGER NULL · source VARCHAR(40) NOT NULL · note VARCHAR(200) NULL · entered_by_user_id INTEGER NULL · created_at DATETIME · UNIQUE(account_id,currency_from,currency_to,rate_date,kind)`

#### 1.8 `fiscal_year_closures` — área B
`id PK · account_id INTEGER NULL · property_id INTEGER NULL · tax_year INTEGER NOT NULL · closed_at DATETIME NOT NULL · closed_by_user_id INTEGER NULL · reopened_at DATETIME NULL · reopened_by_user_id INTEGER NULL · reopen_reason VARCHAR(300) NULL · export_sha256 VARCHAR(64) NULL · UNIQUE(account_id,property_id,tax_year)`

#### 1.9 `fiscal_exports` — área B (soporte de D-015)
`id PK · account_id INTEGER NULL · owner_user_id INTEGER NOT NULL idx · tax_year INTEGER NOT NULL · property_id INTEGER NULL · stored_path VARCHAR NOT NULL · bytes INTEGER NOT NULL · sha256 VARCHAR(64) NOT NULL · includes_ticket_photos BOOLEAN NOT NULL default 0 · expense_count/receipt_count/missing_fx_count/excluded_other_mode_count INTEGER · catalog_version VARCHAR(16) · data_mode VARCHAR(8) NOT NULL · created_by_user_id INTEGER NULL · created_at DATETIME`

#### 1.10 `expense_recurrences` — área B (solo modelo, sin rutas)
`id PK · account_id INTEGER NULL · property_id INTEGER NOT NULL idx · category_code VARCHAR(40) NOT NULL · amount NUMERIC(14,2) NOT NULL · currency VARCHAR(3) NOT NULL · provider_id INTEGER NULL · frequency VARCHAR(12) NOT NULL · day_of_month/month_of_year INTEGER NULL · next_run_date DATE NOT NULL · active BOOLEAN NOT NULL default 1 · note VARCHAR(200) NULL · created_by_user_id INTEGER NULL · created_at DATETIME`
(`vendor_id` renombrada a `provider_id` por coherencia.)

#### 1.11 `password_reset_tokens` — área E
`id PK · user_id INTEGER NOT NULL · token_hash VARCHAR(64) NOT NULL UNIQUE · user_email_at_issue VARCHAR NOT NULL · created_at DATETIME · expires_at DATETIME NOT NULL · used_at DATETIME NULL · consumed_reason VARCHAR NULL · requested_ip VARCHAR(64) NULL · requested_user_agent VARCHAR(300) NULL · used_ip VARCHAR(64) NULL`

#### 1.12 `outbox_emails` — área E
`id PK · to_email VARCHAR NOT NULL · subject VARCHAR NOT NULL · body TEXT NULL · kind VARCHAR NULL · user_id INTEGER NULL · created_at DATETIME · sent_at DATETIME NULL · error VARCHAR(300) NULL`
Regla dura: `body` solo se rellena si `mockmode.is_mock()`.

---

### 2. Columnas AÑADIDAS a tablas existentes (ALTER)

| tabla | columna | DDL exacto | área |
|---|---|---|---|
| users | account_id | `ALTER TABLE users ADD COLUMN account_id INTEGER` | A |
| users | password_changed_at | `ALTER TABLE users ADD COLUMN password_changed_at DATETIME` | E |
| properties | account_id | `ALTER TABLE properties ADD COLUMN account_id INTEGER` | A |
| properties | tax_jurisdiction | `ALTER TABLE properties ADD COLUMN tax_jurisdiction VARCHAR` | B |
| maintenance_tickets | provider_id | `ALTER TABLE maintenance_tickets ADD COLUMN provider_id INTEGER` | C |
| ticket_photos | phase | `ALTER TABLE ticket_photos ADD COLUMN phase VARCHAR NOT NULL DEFAULT 'report'` | C |
| ai_usage | account_id | `ALTER TABLE ai_usage ADD COLUMN account_id INTEGER` | C |
| login_attempts | kind | `ALTER TABLE login_attempts ADD COLUMN kind VARCHAR` | E |
| accounts | default_tax_jurisdiction, base_currency | ALTER solo si `accounts` ya existía sin ellas | B |

**Verificado hoy:** `ticket_photos` y `ai_usage` **no existen en `platform.db`** (11 tablas frente a 19). Ahí `create_all()` las crea completas y estos dos ALTER **no llegan a ejecutarse nunca**; solo actúan sobre `platform-mock.db`. Ambas funciones deben empezar con `if not cols: return`.

---

### 3. Tablas que NO cambian (decisión explícita, para que nadie las "aproveche")

| tabla | decisión |
|---|---|
| `documents` | **Queda muerta.** No se le añade ninguna columna y `DocTypeEnum` **no se amplía** (se retira la propuesta de C de apendizar `invoice`/`quote`). Verificado: existe en ambas bases con 0 filas y su DDL real es `doc_type VARCHAR(15)` **sin CHECK**, pero `Payment.receipt_document_id` (models.py:485) la reserva para 2c. |
| `leases`, `messages`, `maintenance_tickets`, `ticket_events` | **no reciben `account_id`** (regla del área A: cuelgan de una propiedad y los joins ya están en scoping.py). |
| `platform_settings` | una sola clave global nueva: `schema_version='C1'`. No se usa para plan, cierre fiscal ni permisos: es clave/valor **global** (models.py:198-212). |

---

### 4. Índices (todos `CREATE INDEX IF NOT EXISTS`, nativamente idempotente)

**Deuda E1/E2 que este lote paga (verificado hoy sobre `data/platform.db`):**
| índice | por qué | comprobación previa obligatoria |
|---|---|---|
| `ix_properties_site_ref` **UNIQUE** | models.py:128 declara `unique=True, index=True` y en `platform.db` **no existe** (solo está `ix_properties_owner_id`). En mock sí existe. | verificado 3 filas / 3 site_ref distintos → seguro |
| `ix_maintenance_tickets_property_id` | models.py:398 lo declara; `PRAGMA index_list` devuelve `[]` en platform.db | 0 filas |
| `ix_maintenance_tickets_reported_by_user_id` | models.py:399 | 0 filas |
| `ix_maintenance_tickets_public_ref` **UNIQUE** | models.py:409 | crear **después** de `_ensure_ticket_columns` |

**Nuevos:**
`ix_users_account_id(account_id)` · `ix_properties_account_id(account_id)` · `ix_account_plan_events_account_id(account_id)` (A)
`ix_leases_property_status(property_id, status)` · `ix_leases_tenant_status(tenant_id, status)` (D — **sustituyen** a los `ix_leases_property_id`/`ix_leases_tenant_id` sueltos que pedía A: por prefijo izquierdo los cubren)
`ix_tickets_property_status(property_id, status)` · `ix_tickets_provider(provider_id)` (D, C)
`ix_providers_account(account_id, is_active)` · `ix_ticket_quotes_ticket(ticket_id)` · `ix_ticket_photos_phase(ticket_id, phase)` (C)
`ix_attachments_ticket(ticket_id)` · `ix_attachments_expense(expense_id)` · `ix_attachments_account_year(account_id, tax_year)` (C+B fundidos)
`ix_expenses_property_year(property_id, tax_year)` · `ix_expenses_account_year(account_id, tax_year)` · `ix_expenses_ticket(ticket_id)` · `ix_fx_lookup(currency_from, currency_to, rate_date)` (B)
`ux_password_reset_tokens_hash` UNIQUE(token_hash) · `ix_password_reset_tokens_user(user_id, used_at)` · `ix_outbox_emails_created(created_at)` (E)

`create_all(checkfirst=True)` **salta las tablas existentes y no crea índices sobre columnas añadidas por ALTER** — por eso todos van explícitos.

---

## Conflictos entre áreas y su resolución

Los cinco diseños se hicieron sin verse entre sí. Estos son los choques reales que se detectaron al fundirlos:

1. **#1 — Misma tabla, dos nombres: `providers` (área C) vs `vendors` (área B).** El área C diseña el CRUD completo del punto 5 sobre `providers`; el área B reserva `expenses.vendor_id` «para la tabla vendors cuando llegue». Son la misma entidad. RESOLUCIÓN: gana `providers`, con la definición completa del área C (es quien la construye, la audita y la redacta para ARCO). El área B renombra `vendor_id` → `provider_id` y `vendor_name_raw` → `provider_name_snapshot`. Coste de no resolverlo: dos tablas de proveedores, y la exportación fiscal citando una que el ticket no conoce.

2. **#2 — `expenses` definida dos veces con formas incompatibles.** El área C exige `fiscal_year`, `amount NUMERIC(12,2)`, `document_id`, `account_id NOT NULL`; el área B define `tax_year`, `amount NUMERIC(14,2)`, sin `document_id`, `account_id NULL`, más 20 columnas que C no contempla (fx, cierre, anulación, data_mode). Es exactamente el choque que la propia área C avisó que obliga a **reconstruir la tabla en SQLite**, la operación más cara del stack. RESOLUCIÓN: manda la forma del área B, que es el superconjunto y la dueña del módulo fiscal, con tres correcciones: (a) `tax_year` como nombre único, también en `attachments` y en `fiscal_*`; (b) `provider_id`/`provider_name_snapshot` con el vocabulario de C; (c) `account_id` **nullable en el DDL** (postura de B, no bloquea el orden de construcción) pero **siempre escrito por el servidor y con lectura que devuelve 503 si `user.account_id IS NULL`** (fallo cerrado, postura de C). `document_id` desaparece: el vínculo va al revés, `attachments.expense_id`.

3. **#3 — Almacén de comprobantes: reutilizar `documents` (área C) vs crear `expense_receipts` (área B).** El área C quiere añadir 12 columnas a `documents` argumentando «una sola tabla para la exportación fiscal»; el área B se niega porque `documents` lleva `tenant_id` y `doc_type=id_verification` (models.py:55-60) y `Payment.receipt_document_id` la reserva para 2c (models.py:485). RESOLUCIÓN: **ninguna de las dos — tabla nueva `attachments`**. Las dos razones de C (una sola tabla) y de B (no mezclar regímenes de acceso) se satisfacen a la vez, y hay un tercer argumento que ninguna área hizo y que verifiqué hoy: `documents` **existe en las dos bases** con 0 filas, así que la propuesta de C haría 12 ALTER sobre la base real, en el mismo arranque que ya carga 19 ALTER de deuda E1/E2, para una tabla vacía. `attachments` nace de `create_all()` con la forma final, sin un solo ALTER, en ambas bases. Efecto colateral: se **retira** el ítem de C de apendizar `invoice`/`quote` a `DocTypeEnum` (`attachments.purpose` lo cubre) y desaparece el conflicto de `documents.account_id` contra la regla del área A.

4. **#4 — Choque de ruta: `POST /owner/tickets/{id}/gastos` (área C, plural) vs `POST /owner/tickets/{id}/gasto` (área B, singular).** Son paths distintos, así que FastAPI registraría las DOS y habría dos caminos de escritura al mismo dato, con validaciones distintas. RESOLUCIÓN: una sola, `/gastos` (plural, coherente con la colección `/owner/gastos`), propiedad del módulo fiscal (área B). El área C aporta el enganche desde el detalle del ticket y el precargado con el proveedor asignado; no implementa la ruta.

5. **#5 — `account_id` en `attachments` contra la regla del área A.** El área A fija: «una tabla nueva lleva `account_id` propio SOLO si no cuelga de una propiedad», y lista explícitamente `documents` entre las que no lo llevan. Pero la exportación de D-015 filtra por `(cuenta, año fiscal)` y `attachments` cuelga de **tres** padres distintos (ticket, gasto, proveedor). RESOLUCIÓN: excepción documentada — `attachments` lleva `account_id` y `tax_year` denormalizados. El motivo de la regla de A es el coste de relleno, y aquí es cero: la tabla nace vacía. Mismo razonamiento aplica a `ai_usage.account_id`, que además no cuelga de ninguna propiedad y por tanto ni siquiera es excepción.

6. **#6 — Índices duplicados sobre `leases`: A pide `ix_leases_property_id` + `ix_leases_tenant_id`; D pide `ix_leases_property_status` + `ix_leases_tenant_status`.** Cuatro índices para dos consultas. RESOLUCIÓN: solo los dos **compuestos** de D; por prefijo izquierdo cubren íntegramente lo que A quería (`scoped_leases` en scoping.py:105-119 y el DISTINCT de `scoped_users`), y además sirven al GROUP BY de ocupación que los sueltos no sirven. Se ahorran dos índices en cada escritura de `leases`.

7. **#7 — Cuatro áreas editan `base.html` en el mismo lote.** A quiere el include `_account_banner.html`; C quiere la entrada «Proveedores» en el menú; B quiere «Gastos» y «Fiscal»; E renderiza `base.html` **deliberadamente sin `user`** en el camino de cambio forzado de contraseña. Y el hecho verificado es que Jinja 3.1 con `Undefined` por defecto **lanza `UndefinedError` al acceder a un atributo de una variable no inyectada**: un solo `{% if ctx.x %}` nuevo rompe las 27 plantillas y las 41 comprobaciones de test_ui.py. RESOLUCIÓN: `base.html` se edita **una sola vez, en la etapa E9**, añadiendo de golpe el banner y las cuatro entradas de menú de las etapas posteriores, y registrando en el entorno de Jinja los globales con valor por defecto (`ctx_cuenta`, `open_tickets`, `unread_messages`, `t`). Las etapas E10-E14 solo rellenan valores; ninguna vuelve a tocar la estructura.

8. **#8 — Dos módulos para las cadenas de D-014: `app/labels_es.py` (área D) vs `app/strings/es.py` (área C).** Mismo trabajo, dos sitios; si ambos aterrizan, tickets y gastos duplicarán las etiquetas de estado. RESOLUCIÓN: uno solo, **`app/strings/es.py`** (paquete, admite trocear por módulo después) con `t()` registrado como global de Jinja en E9, junto con el resto de globales del punto #7. El área D consume, no define.

9. **#9 — Tope de gasto del agente IA: global (código actual) vs por cuenta (área C) vs por plan (área A).** Verificado: `ai_agent.py:26` define `MONTHLY_BUDGET_USD` como constante de entorno y `budget_exhausted()` (ai_agent.py:113-115) suma **todas** las filas de `ai_usage` del mes sin filtrar por nadie. Con varias cuentas, la cotización automática de una administradora agota el presupuesto de todas. RESOLUCIÓN: el área C aporta **solo la columna** `ai_usage.account_id` y su relleno; la fórmula del tope por plan la fija el área A y se implementa en E14, no antes. Hasta entonces el tope sigue siendo global, que es correcto mientras el agente esté desconectado (`created_via` siempre `'form'`).

10. **#10 — El área A justifica «ninguna ruta JSON de cuentas» apoyándose en el agujero de `POST /api/auth/login`; el área E lo cierra.** No es una contradicción de esquema, pero sí de razonamiento: una vez que E8 extraiga `resolve_session_user()` y retire las tres rutas JSON, el argumento de A pierde fuerza. RESOLUCIÓN: la decisión de A **se mantiene por otro motivo** — no exponer lógica comercial en JSON reduce superficie que auditar en scoping — y así se documenta, para que nadie la revierta diciendo «ya está arreglado el login».

11. **#11 — Coherencia de la moneda entre `expenses` (área B) y `ticket_quotes` (área C).** C define `amount NUMERIC(12,2)` y `currency VARCHAR default 'MXN'` sin nada de tipo de cambio; B define `NUMERIC(14,2)` con `base_currency`/`amount_base`/`fx_*`. Una cotización aprobada que se convierte en gasto perdería precisión al copiarse. RESOLUCIÓN: `ticket_quotes.amount` pasa a `NUMERIC(14,2)` y `currency VARCHAR(3)`. La cotización **no** guarda tipo de cambio (no es un asiento fiscal); la conversión ocurre al crear el gasto.

12. **#12 — El despachador caliente `POST /owner/tickets/{id}/actualizar` debe seguir siendo urlencoded (área C) mientras B y C abren dos caminos de subida.** Verificado: el middleware CSRF lee el cuerpo multipart **completo en memoria dos veces** (security.py:194-207, `await request.body()` y luego `request.form()` con reinyección de `_receive`). RESOLUCIÓN: (a) `/actualizar` no gana `File(...)` en su firma — lo sostienen test_owner_portal.py:73,77,92 y test_ui.py:121,131; (b) fotos, documentos y gastos van en formularios propios con su `enctype`; (c) **prerrequisito bloqueante compartido**: guarda por `Content-Length` en el middleware CSRF devolviendo 413 antes del `await request.body()`, en la primera etapa que abra una subida (E12). Sin ella, dos subidas grandes simultáneas tumban el proceso en free-tier.

---

## Orden de migración

> **Trampa verificada:** el bloque de siembra de `main.py:240-243` hace `return` anticipado cuando ya existe
> un administrador. Cualquier función `_ensure_*` registrada **después** de ese bloque nunca se ejecutaría
> sobre `platform.db`, que es justamente la base que hay que migrar.

| # | Qué | Cómo | Riesgo |
|---|---|---|---|
| 0 | Instantánea previa obligatoria de data/platform.db y data/platform-mock.db | `from app.backup import _snapshot; _snapshot('data/platform.db', dst)` — backup.py:44-66 abre en `mode=ro`, usa `sqlite3.Connection.backup()` y corre `PRAGMA integrity_check` sobre la COPIA. Devuelve `{'bytes':…, 'tables':{nombre:filas}}`: ese dict se pega literalmente en la nota de despliegue. NUNCA `shutil.copy` (no verifica nada y copia páginas rotas si algo está escribiendo). No es una función de arranque: se ejecuta a mano antes de arrancar. | Si se salta, no hay vuelta atrás sobre los 3 usuarios y 3 propiedades reales. |
| 1 | `Base.metadata.create_all(bind=engine)` — ya existe en main.py:227, no se toca | Crea las 12 tablas nuevas. En `platform.db` crea además las 8 que le faltan (ai_usage, announcements, announcement_recipients, messages, platform_settings, sessions, ticket_events, ticket_photos), y las crea YA con sus columnas nuevas: por eso `_ensure_ticket_photo_phase` y `_ensure_ai_usage_account` no llegan a disparar ahí. | Ninguno nuevo: es la línea que ya corre hoy. |
| 2 | `_ensure_property_site_ref()` (main.py:132-149) — sin cambios | Ya registrada en main.py:228. | Ya ejecutada sobre platform.db en su día (site_ref aparece al final del CREATE TABLE): no-op. |
| 3 | `_ensure_user_security_columns()` (main.py:151-181) — se le AÑADE `password_changed_at` (área E) y `account_id` (área A) al diccionario `wanted` | Dos entradas más en el dict existente. Registrada ya en main.py:229. VERIFICADO HOY: en `platform.db` esta función nunca se ha ejecutado — a `users` le faltan contact_phone, must_change_password, created_by_user_id, totp_secret, totp_enabled, totp_confirmed_at y google_sub. El primer arranque real hará 7 ALTER de deuda E1 + los 2 nuevos. | ALTO por acumulación, no por las columnas nuevas. `must_change_password` entra con DEFAULT 0 → los 3 usuarios reales NO quedan atrapados por el middleware del área E. Confirmado, y es lo que impide dejar al CEO fuera. |
| 4 | `_ensure_ticket_columns()` (main.py:183-218) — se le AÑADE `provider_id` (área C) | Una línea más en el dict `wanted`. Registrada ya en main.py:230. VERIFICADO: en `platform.db` a `maintenance_tickets` le faltan las 11 columnas de E5 y a `leases` le falta `created_by_user_id`; el primer arranque real ejecuta 12 ALTER de deuda + 1 nuevo, sobre 0 filas. | Bajo (0 tickets, 0 leases en la base real), pero es el bloque de ALTER más grande del arranque. |
| 5 | `_ensure_account_columns()` — properties.account_id (users.account_id ya entró en el paso 3) | Función nueva, patrón calcado de main.py:183-215: `PRAGMA table_info(properties)` → `if not cols: return` → `ALTER TABLE properties ADD COLUMN account_id INTEGER`. **Se registra en main.py como línea 231, inmediatamente después de `_ensure_ticket_columns()` y ANTES del `if is_mock():` de main.py:232.** | Ninguno: columna nullable sobre 3 filas. |
| 6 | `_ensure_account_fiscal_columns()` — accounts.default_tax_jurisdiction, accounts.base_currency | `if not cols: return` primero, para que no reviente si `accounts` aún no existe (caso: el área B se construye antes que la A). En la práctica no dispara nunca porque las dos columnas van declaradas en el modelo `Account` desde el día uno y create_all las crea; existe solo para la base donde E9 se desplegó antes que E13. Registrada tras el paso 5. | Nulo. Es red de seguridad, no camino principal. |
| 7 | `_ensure_property_fiscal_columns()` — properties.tax_jurisdiction VARCHAR NULL | Mismo patrón. Sin UPDATE masivo: NULL hereda de `accounts.default_tax_jurisdiction` y, si falta, 'MX'. Registrada tras el paso 6. | Ninguno. |
| 8 | `_ensure_ticket_photo_phase()` — ticket_photos.phase VARCHAR NOT NULL DEFAULT 'report' | `if not cols: return`. `ALTER TABLE ticket_photos ADD COLUMN phase VARCHAR NOT NULL DEFAULT 'report'` — SQLite lo admite con DEFAULT constante; precedente literal en main.py:162. **Elimina el UPDATE de relleno.** Solo dispara sobre platform-mock.db: en platform.db la tabla no existe y create_all la crea completa. | Ninguno. |
| 9 | `_ensure_ai_usage_account()` — ai_usage.account_id INTEGER NULL | `if not cols: return`. Igual que el paso 8: solo actúa sobre mock. | Ninguno. |
| 10 | `_ensure_login_attempt_kind()` — login_attempts.kind VARCHAR NULL | Mismo patrón. Va acompañada EN EL MISMO COMMIT de añadir `LoginAttempt.kind.is_(None)` al filtro de `ip_is_rate_limited` (security.py:466-480). Sin esa línea, 11 peticiones a /recuperar dejan sin /login a una oficina entera (MAX_FAILS_PER_IP=10 en ventana de 1 minuto). | Medio si se olvida la línea del filtro: denegación de servicio de once peticiones. |
| 11 | `_ensure_missing_indexes()` — TODOS los índices, nuevos y de deuda E1 | Una sola función con `CREATE INDEX IF NOT EXISTS`. Va **la última de las de DDL** porque `ix_properties_account_id` y `ix_maintenance_tickets_public_ref` dependen de columnas que añaden los pasos 4 y 5. Para los DOS índices UNIQUE (`ix_properties_site_ref`, `ix_maintenance_tickets_public_ref`) se comprueba antes `SELECT COUNT(*), COUNT(DISTINCT col)`; si no coinciden se SALTA con un aviso ruidoso en consola en vez de reventar el arranque. Verificado hoy: platform.db tiene 3 propiedades con 3 site_ref distintos → el UNIQUE entra limpio. | Un CREATE UNIQUE INDEX que falla aborta `engine.begin()` y deja la app sin arrancar. De ahí la comprobación previa. |
| 12 | `_backfill_accounts()` — la ÚNICA función que escribe filas, no DDL | Corta en seco si `platform_settings['schema_version'] == 'C1'`. Todo en UNA transacción con rollback. Necesita `SessionLocal()`, así que **es la que más peligro corre**: si se registra después de main.py:240 nunca corre sobre platform.db, porque el `if existing_admin: return` de main.py:243 sale de `on_startup()` en cuanto encuentra el admin — y platform.db tiene exactamente 1 admin. Se registra como parte de `_migrar()` en la línea 231, con su propia `SessionLocal()` que se cierra en `finally`, sin reutilizar la de main.py:240. | ALTO si se coloca mal. Es el punto exacto de la trampa. |
| 13 | `_verificar_integridad_cuentas()` — solo lectura, imprime avisos | Cuenta `properties` cuyo `account_id` no coincide con el del `owner_id`, usuarios con `account_id NULL`, cuentas con propiedades y sin usuarios. No corrige nada, no lanza excepción, imprime. Es lo único que detecta la deriva con `PRAGMA foreign_keys = 0`. Registrada tras el paso 12. | Limitación declarada: ninguna plantilla lee audit_log hoy, así que este aviso vive solo en la consola del arranque hasta que exista la pantalla de bitácora. |
| 14 | `_set_schema_version('C1')` en platform_settings | Última línea de `_migrar()`. Hoy una base a medio migrar y una recién creada son indistinguibles; esta clave las separa. Cuesta un INSERT. | Ninguno. |

---

## Relleno de datos existentes (backfill)

**Dónde se registra todo.** Se envuelven los pasos 5-14 en una sola función `_migrar()` y se llama en `main.py` **línea 231**, es decir entre `_ensure_ticket_columns()` (main.py:230) y el `if is_mock():` (main.py:232). Esto es obligatorio y no negociable: el bloque de siembra abre `db = SessionLocal()` en main.py:240 y ejecuta `if existing_admin: return` en main.py:243, saliendo de `on_startup()`. `platform.db` tiene 1 admin (verificado), así que **cualquier función registrada después de la 243 jamás correría sobre la base real del CEO**. Las tres `_ensure_*` actuales (main.py:228-230) ya están del lado correcto; lo nuevo debe quedar junto a ellas, no al final del `on_startup`.

**Cómo se rellena `account_id`, en una sola transacción y en este orden:**
1. Cuenta operadora: `Account(name='Aura Enterprise Solutions', is_operator=1, plan='enterprise_plus', plan_assigned_at=NULL, trial_started_at=NULL)`. Todos los `users` con `role=admin` reciben su `account_id`.
2. Una cuenta por cada `user` con `role=owner` y `account_id IS NULL`: `name = user.name`, `plan='enterprise_plus'`, `plan_assigned_at=NULL` (así la ficha de admin los pinta como «plan sin asignar — migrada»), `trial_started_at=NULL` (nadie hereda un reloj de prueba ya empezado), `primary_user_id=user.id`, `created_in_db = basename(engine.url.database)`.
3. **`is_operator` de las cuentas de owner = 1 si alguna de sus propiedades tiene `site_ref IS NOT NULL`.** Verificado hoy: las 3 propiedades de platform.db tienen `site_ref`, repartidas entre el propietario #2 (2 casas) y el propietario #3 (1 casa). Si el relleno pusiera `is_operator=0`, la regla del área A («rechazar `site_ref` en cuentas con `is_operator=0`», POST /admin/sync-site-properties, pages.py:597-655) **rompería la sincronización del sitio público el primer día** para las tres casas que ya están publicadas.
4. `properties.account_id = ` la cuenta del `owner_id` de cada fila. En platform.db: 2 filas → cuenta del propietario #2, 1 fila → cuenta del propietario #3.
5. Inquilinos (`role=inquilino`): `account_id` = cuenta del dueño de la propiedad de su arrendamiento **activo**. Si hay 0 o más de 1 candidato, se deja NULL y se reporta. En platform.db es no-op: 0 arrendamientos, 0 inquilinos.
6. `ai_usage.account_id`: solo en mock, derivado del `user_id` de cada fila; lo que no resuelva queda NULL.
7. Todo lo demás (`expenses`, `providers`, `attachments`, `ticket_quotes`, …) nace vacío: **no hay nada que rellenar**.

**Fallo en seguro mientras `account_id` sea NULL.** `scoping.py` no cambia de predicado en este lote: `owned_properties` (scoping.py:59-69) sigue filtrando `Property.owner_id == user.id`, y `scoped_leases` (:105-119) y `scoped_tickets` (:126-146) ya hacen `join(Property)` y filtran por `Property.owner_id`, así que cuando el predicado sobre `Property` pase a la cuenta, los joins no se tocan. Un `account_id` NULL cae siempre a la rama heredada, que es **estrictamente más estrecha**, nunca más ancha. Las funciones nuevas (`account_properties()`, `account_user_ids()`, `scoped_providers()`, `scoped_expenses()`) devuelven **vacío o 503**, jamás «todo».

**Qué pasa con `platform.db` real — y es más de lo que dice el resumen de áreas.** Verificado hoy con `sqlite_master` sobre la base real:
- 11 tablas (faltan 8); 3 usuarios (1 admin + 2 owners); 3 propiedades, las tres con `site_ref` distinto; **0 leases, 0 tickets, 0 documents, 0 payments**; 1 fila en `audit_log` y 1 en `login_attempts`.
- `users` **carece de 7 columnas de E1**: contact_phone, must_change_password, created_by_user_id, totp_secret, totp_enabled, totp_confirmed_at, google_sub.
- `maintenance_tickets` **carece de las 11 columnas de E5**; `leases` carece de `created_by_user_id`.
- `properties` no tiene el índice UNIQUE `ix_properties_site_ref` que models.py:128 declara; `maintenance_tickets` no tiene **ningún** índice.

Es decir: `_ensure_property_site_ref()` sí corrió en su día contra esta base, pero `_ensure_user_security_columns()` y `_ensure_ticket_columns()` **nunca**. El primer arranque real ejecutará, antes de una sola línea de trabajo nuevo: create_all de 8 tablas + ~19 ALTER de deuda acumulada + 4 CREATE INDEX de deuda. **Ese, y no el `account_id`, es el momento peligroso de este lote.**

**Ensayo en seco, obligatorio antes de tocar nada.** Módulo nuevo `platform/app/migrate.py` con `python -m app.migrate --simular`:
1. `_snapshot('data/platform.db', tmp/copia.db)` (backup.py:44-66).
2. Captura `PRAGMA table_info` + `PRAGMA index_list` + `SELECT COUNT(*)` de cada tabla de la copia.
3. `DATABASE_URL=sqlite:///tmp/copia.db`, `APP_ENV=dev`, arranca la app con `TestClient` para disparar `on_startup`.
4. Vuelve a capturar y **imprime el diff**: tablas nuevas, columnas nuevas, índices nuevos, cuentas creadas, filas con `account_id` NULL restantes.
5. **Sale con código 1 si cambia el número de filas de `users` o de `properties`.** Una migración que mueve filas de esas dos tablas está mal.
6. Repite los pasos 3-4 **sobre la misma copia** y exige un diff vacío la segunda vez (idempotencia real, no declarada).
7. La original nunca se abre en modo escritura.

Solo cuando `--simular` pase dos veces seguidas se arranca contra `data/platform.db`, con la instantánea del paso 0 ya guardada y su dict de conteos anotado.

---

## Impacto en las pruebas

**Línea base reejecutada hoy por mí, no citada de memoria:** `platform/.venv/Scripts/python.exe tests/run_all.py` → **261 pasaron, 0 fallaron, en 10 suites** (test_e1 27 · test_e2 25 · test_inbox 21 · test_owner_portal 38 · test_scoping 27 · test_sessions 24 · test_sso 25 · test_tenant 33 · test_ui 41). `test_migrate.py` sale con código 0 pero `run_all.py` lo marca «sin resumen» y sus ~7 comprobaciones **no suman**: la expresión `RESULTADO:\\s*(\\d+)\\s*pasaron,\\s*(\\d+)\\s*fallaron` de run_all.py:19 no encuentra nada porque la suite no imprime esa línea. Ojo: sin el venv el ejecutor devuelve 0/0 con las 10 suites «ROTAS» por `ModuleNotFoundError` — no es un fallo de las pruebas.

**Nuevas comprobaciones por etapa (estimación de suites, no de asserts sueltos):**
| etapa | suite nueva | nuevas | acumulado |
|---|---|---|---|
| E8 | `test_acceso_api.py` | ~14 | 275 |
| E9 | `test_cuentas.py` (~29) + `test_migrate_cuentas.py` (~12) + los 7 de test_migrate.py que por fin suman | ~48 | 323 |
| E10 | `test_acceso.py` | ~38 | 361 |
| E11 | `test_owner_dashboard.py` | ~26 | 387 |
| E12 | `test_proveedores.py` + `test_ticket_archivos.py` | ~34 | 421 |
| E13 | `test_fiscal.py` | ~28 | 449 |
| E14 | `test_export_auditoria.py` | ~14 | 463 |

**Suites existentes que hay que MODIFICAR (no solo ampliar) — cuatro archivos, y conviene decirlo antes de empezar:**
1. **`test_migrate.py` (E9, obligatorio).** Verificado: línea 3 `REAL = r"C:\\Aura\\claude-code\\platform\\data\\platform.db"` y línea 4 apuntando a un scratchpad de una **sesión muerta** (`4c0c4031-…`). Pasa a rutas relativas con `pathlib` + `tempfile`, y gana la línea `RESULTADO:` para que sus 7 PASS cuenten. Hoy además **copia y arranca la app contra la base real del CEO en cada ejecución de run_all.py**: eso ya funciona, pero conviene que la copia viva en `tempfile.mkdtemp()`, no en una ruta fija.
2. **`test_ui.py` (E9 y luego cada etapa).** Línea 156 lee `r"C:\\Aura\\claude-code\\data\\site.json"` — misma corrección. Y el bucle de CSP de las líneas 90-93 se amplía en E10, E11, E12 y E13 con las URL nuevas.
3. **`test_tenant.py`, `test_owner_portal.py`, `test_ui.py` (E10, riesgo real de romper 112 comprobaciones a la vez).** El middleware de cambio forzado redirige a `/cambiar-contrasena` cuando `must_change_password` está activo, y `owner_portal.py:329` lo pone **a True para cada inquilino que se crea**. Las siembras de esas tres suites tienen que fijarlo explícitamente a False. Es un cambio de **siembra**, no de aserción: si alguien se ve tentado de ajustar una aserción, la semántica cambió y hay que parar.
4. **`test_scoping.py` (E9): NO se toca.** Es el contrato de la etapa: se ejecuta tal cual y debe dar los mismos 27 PASS. Si hay que editarlo, el aislamiento cambió de forma y el relleno de `account_id` no está fallando estrecho.

**Deuda de portabilidad que este lote paga de paso:** con esos dos archivos arreglados, las 10 suites dejan de tener rutas absolutas de Windows y [inferido, no lo he ejecutado en Linux] dejan de reventar en un CI que no sea esta máquina.

**Regla de aceptación por etapa:** ninguna etapa se da por entregada si `run_all.py` no acaba en `0 fallaron` y con un total **mayor o igual** al de la etapa anterior. Un total que baja significa que una suite dejó de imprimir su línea RESULTADO, que es exactamente el fallo silencioso que test_migrate.py lleva arrastrando.

---

## Riesgos principales

- **El primer arranque contra `platform.db` no es «añadir account_id»: es descargar toda la deuda de E1 y E5 de golpe.** Verificado hoy: a `users` le faltan 7 columnas (contact_phone, must_change_password, created_by_user_id, totp_secret, totp_enabled, totp_confirmed_at, google_sub), a `maintenance_tickets` le faltan las 11 de E5, a `leases` le falta created_by_user_id, y faltan 8 tablas enteras. `_ensure_property_site_ref()` sí corrió allí en su día; las otras dos **nunca**. El arranque hará create_all de 8 tablas + ~19 ALTER antes de una sola línea de trabajo nuevo. Mitigación: instantánea con `_snapshot()` (backup.py:44-66), `python -m app.migrate --simular` pasando dos veces, y salida con código 1 si cambia el conteo de filas de users o properties.
- **Registrar `_migrar()` en el sitio equivocado la deja sin ejecutar sobre la base real, en silencio.** `main.py:243` hace `if existing_admin: return` y sale de `on_startup()`; `platform.db` tiene 1 admin. Cualquier función colocada después de main.py:240 nunca corre allí — y peor: **sí corre sobre una base nueva y vacía**, así que las pruebas locales pasarían y solo la base del CEO quedaría sin migrar. Mitigación: la línea 231, más una comprobación de QA que arranque contra una copia CON admin y verifique que las columnas nuevas aparecen.
- **`is_operator` mal rellenado rompe el sitio público de las 3 casas ya publicadas.** Las 3 propiedades de platform.db tienen `site_ref`, repartidas entre el propietario #2 (2) y el #3 (1). La regla del área A rechaza asignar `site_ref` a cuentas con `is_operator=0` (POST /admin/sync-site-properties, pages.py:597-655). Si el relleno pone 0 en las cuentas de owner, la siguiente sincronización deja de publicar. Mitigación: `is_operator = 1` si alguna propiedad del owner tiene `site_ref`, con una comprobación de QA que sincronice después de migrar y verifique que siguen saliendo las tres.
- **Tres áreas definen la misma tabla con nombres y tipos distintos, y SQLite no permite arreglarlo barato.** `providers` vs `vendors`, `fiscal_year` vs `tax_year`, `NUMERIC(12,2)` vs `(14,2)`, `documents` reutilizada vs `expense_receipts`. Si E12 y E13 se escriben en semanas distintas sin haber congelado el DDL, la corrección exige reconstruir tablas (crear, copiar, borrar, renombrar) con datos dentro. Mitigación: `docs/phase2/DB_SCHEMA.md` fija la lista de columnas en **E9**, y QA compara el modelo entregado contra esa tabla nombre a nombre y tipo a tipo antes de aceptar E12 y E13.
- **`base.html` lo tocan cuatro áreas y Jinja 3.1 lanza `UndefinedError` al acceder a un atributo no inyectado.** Un solo `{% if ctx.plan %}` añadido sin registrar el global por defecto rompe las 27 plantillas y 41 comprobaciones de test_ui.py de una vez, incluidas `/admin` e `/inquilino`, que no tienen contexto de cuenta. Mitigación: una única edición en E9 con todos los globales por defecto registrados a la vez; las etapas siguientes solo rellenan valores. Comprobación de QA: `GET /admin`, `GET /owner` y `GET /inquilino` devuelven 200 tras el cambio.
- **Dos caminos de subida nuevos sobre un middleware CSRF que lee el cuerpo multipart entero en memoria dos veces** (security.py:194-207: `await request.body()` y después `request.form()` con reinyección de `_receive`). Con 8 MB por archivo y free-tier, dos subidas simultáneas tumban el proceso. Y `UPLOAD_DIR` **no se ramifica por `DATA_MODE`** (uploads.py:30) mientras la base sí (db.py:33-37): los ids de ticket colisionan entre mock y real, y la primera factura real aterrizaría en la misma carpeta que la basura de pruebas. Mitigación: ambas cosas son prerrequisito **bloqueante** dentro de E12, antes de la primera ruta que acepte un archivo.
- **El middleware de cambio forzado de contraseña (E10) es lo único de este lote que puede dejar a todo el mundo fuera, CEO incluido.** Verificado que el riesgo real es menor de lo que parece: `platform.db` **no tiene la columna** `must_change_password`, así que el ALTER la crea con `DEFAULT 0` y los 3 usuarios reales entran sin fricción. El riesgo vive en las pruebas y en los inquilinos: `owner_portal.py:329` la pone a True para cada inquilino creado. Mitigación: sembrar False en las suites afectadas, y una comprobación que verifique que `/logout`, `/login`, `/2fa`, `/static/platform.js` y `/api/health` siguen accesibles desde el estado atrapado.
- **`properties.site_ref` no tiene índice UNIQUE en la base real aunque models.py:128 declare `unique=True`.** Verificado: platform.db solo tiene `ix_properties_owner_id`; en mock sí existe `ix_properties_site_ref`. Hoy, en producción, nada impide dos propiedades con el mismo `site_ref`, y la sincronización del sitio escribiría dos veces sobre la misma ficha pública. Se paga en E9 (3 filas / 3 valores distintos verificados, entra limpio), con comprobación previa de duplicados: un `CREATE UNIQUE INDEX` que falla dentro de `engine.begin()` **aborta el arranque de la app**, así que ante duplicados se salta con aviso ruidoso en vez de reventar.
- **El tope de gasto del agente IA es mensual y GLOBAL** (`ai_agent.py:26` y `budget_exhausted` en :113-115 suman todas las filas de `ai_usage` sin filtrar). En cuanto haya más de una cuenta, la primera administradora que use cotización automática deja sin presupuesto a todas las demás — y `budget_exhausted()` devuelve False ante cualquier excepción, así que falla hacia el gasto. Mitigación: `ai_usage.account_id` entra en E12 pero el tope por cuenta y plan no se cablea hasta E14; mientras tanto el agente sigue desconectado (`created_via` siempre `'form'`) y `/cotizaciones/solicitar` devuelve 501, que es lo que hace aceptable el retraso.
- **Nada de esto se ve todavía: `security.audit()` escribe en `audit_log` y ninguna de las 27 plantillas la lee.** El aviso de deriva de cuentas, el rastro de las reasignaciones de propiedad, quién descargó qué comprobante y quién exportó un paquete fiscal con fotos del interior de una vivienda — todo queda escrito y nadie puede consultarlo salvo por SQL. La verificación de integridad del arranque imprime en una consola que en free-tier nadie mira. Es la carencia que este lote **no** resuelve y hay que decírselo al CEO: la pantalla de bitácora es una etapa aparte, y hasta que exista, la trazabilidad es teórica.
