<!-- Generado por el panel de diseño del 2026-09-08. Ganadora: B · Proveedores sin llave: terceros como datos, nunca como cuentas (riesgo) -->

> **Área C · Proveedores y ciclo de ticket ampliado**
> Fecha: 2026-09-08 · Estado: diseño cerrado, listo para construir
> Cubre los puntos 5, 6.1, 6.2, la parte de 2.4 que cuelga del ticket, y el ANDAMIAJE APAGADO del 7.4.
> Base ganadora: propuesta B (riesgo). Injertos de A (mínimo) y C (producto) marcados en §14.

---

## 1. Alcance

**Dentro:** CRUD manual de proveedores; asignar un proveedor a un ticket; adjuntar fotos y comprobantes *después* de resolver; captura desde la cámara del móvil; captura del gasto desde el ticket; esqueleto apagado del flujo de cotizaciones.

**Fuera, y no se construye ni se deja stub:** ingestión de correo entrante (primer paso del 7.4), envío de cualquier cosa a un proveedor, rol o cuenta de proveedor, exportación fiscal (área fiscal, D-015), tabla `expenses` (área fiscal), tabla `accounts` y `has_entitlement` (área de cuentas/planes).

**Premisas heredadas (no se discuten):** D-013 raíz de aislamiento = cuenta · D-014 español con cadenas extraídas · D-015 exportación por año fiscal, sin rol auditor · D-016 gastos, comprobantes y proveedores bajo la puerta DATA_MODE existente.

---

## 2. Las cinco decisiones que gobiernan todo lo demás

| # | Decisión | Por qué |
|---|---|---|
| C-1 | **El proveedor es un dato de la cuenta, nunca una fila en `users`.** | `users.email` es UNIQUE global (`models.py:79`): dos administradoras no podrían registrar al mismo plomero, y el fallo solo aparecería con el segundo cliente. Además `password_hash` es NOT NULL (`models.py:78`), entraría en `scoped_users` (`scoping.py:160-183`) y aparecería como persona asignable y como destinatario de mensajes. Se rechaza. |
| C-2 | **`accounts` (D-013) es la raíz. `providers.account_id` es NOT NULL y el aislamiento falla CERRADO.** | Es una tabla nueva, así que `create_all` la crea con NOT NULL sin problema. Si `user.account_id` viene NULL, las rutas devuelven **503 con mensaje diagnosticable**, nunca una lista vacía (que se lee como "desaparecieron mis proveedores") y nunca la lista completa. |
| C-3 | **`POST /owner/tickets/{id}/actualizar` NO se convierte en multipart.** | `CSRFMiddleware` lee el cuerpo completo en memoria y lo vuelve a parsear (`security.py:194-207`). Convertir el despachador caliente haría que cada comentario pagase ese coste, y las pruebas existentes le envían urlencoded (`test_owner_portal.py:73,77,92`, `test_ui.py:121,131`). Los adjuntos van en rutas propias. |
| C-4 | **La cámara del 6.2 se resuelve con el atributo HTML `capture`. Se rechaza `getUserMedia`.** | `capture` no es JS, no lo toca `script-src 'self'` y no lo gobierna `Permissions-Policy: camera=()` (`security.py:246`), que rige `getUserMedia`. La alternativa exigiría relajar esa cabecera, ~100 líneas de JS y dar a la página un flujo de vídeo EN VIVO del interior de la vivienda de un inquilino. Lo único que se pierde es el reescalado en cliente, y el servidor ya reescala a 1568 px y destruye el EXIF/GPS (`uploads.py:96-104`). |
| C-5 | **NO se añade ningún miembro a `TicketEventTypeEnum`.** | Ese enum lo lee la línea de tiempo en las DOS vistas (`owner_ticket_detail.html:31` y `tenant_ticket_detail.html:32`). Los enums se guardan por NOMBRE; una reversión de despliegue con filas nuevas ya escritas rompe la página entera para propietario e inquilino. Se reutilizan `assigned`, `photo_added` y `comment` con prefijo fijo en el cuerpo. Sí se amplía `DocTypeEnum` (§3.4), porque hoy NINGÚN router lee `Document` y por tanto no hay nada que romper hacia atrás. |

---

## 3. Modelo de datos

### 3.1 `providers` (nueva)

| Columna | Tipo | Notas |
|---|---|---|
| id | INTEGER PK | |
| account_id | INTEGER NOT NULL, index | FK lógica a `accounts` (D-013). SQLite no la impone: no hay `PRAGMA foreign_keys` en ninguna parte del código, verificado. |
| name | VARCHAR NOT NULL | Razón social o nombre comercial. |
| contact_name | VARCHAR NULL | |
| trade | VARCHAR NULL | Oficio. **VARCHAR validado en Python contra los 7 nombres de `TicketCategoryEnum` (`models.py:361-368`) + `otro`.** No es un Enum de SQLAlchemy y no se crea un catálogo nuevo. |
| phone | VARCHAR NULL | |
| email | VARCHAR NULL | Sin UNIQUE: el mismo plomero puede estar en dos cuentas. |
| tax_id | VARCHAR NULL | RFC/EIN. Solo se captura en `live` (§10). |
| notes | TEXT NULL | Pasa por el guard de texto libre en mock (§10). |
| is_active | BOOLEAN NOT NULL DEFAULT 1 | |
| archived_at | DATETIME NULL | |
| redacted_at | DATETIME NULL | Sella la supresión de contacto conservando el nombre. |
| created_by_user_id | INTEGER NULL | |
| created_at / updated_at | DATETIME | `server_default=func.now()` |

**Prohibido por diseño:** CLABE, cuenta bancaria y domicilio. Un dato bancario de un tercero es 2c y cae tras otra puerta; el domicilio no aporta nada al ticket y sí es PII de alguien que no firmó nada.

### 3.2 `ticket_quotes` (nueva)

| Columna | Tipo | Notas |
|---|---|---|
| id | INTEGER PK | |
| account_id | INTEGER NOT NULL, index | |
| ticket_id | INTEGER NOT NULL, index | |
| provider_id | INTEGER NULL | |
| provider_name_snapshot | VARCHAR NOT NULL | **Copia congelada al crear.** Una cotización aprobada en 2026 debe seguir diciendo a quién se aprobó aunque el proveedor se archive o se redacte en 2028. |
| status | VARCHAR NOT NULL DEFAULT 'borrador' | `borrador · solicitada · recibida · aprobada · rechazada · cancelada`. VARCHAR, **no Enum**: es una máquina de estados recién nacida que casi seguro gana miembros cuando el CEO cierre el 7.4. |
| source | VARCHAR NOT NULL DEFAULT 'manual' | `manual · agent`. |
| amount | NUMERIC(12,2) NULL | |
| currency | VARCHAR DEFAULT 'MXN' | |
| valid_until | DATE NULL | |
| scope_notes | TEXT NULL | |
| document_id | INTEGER NULL | Cotización en PDF, si la hay. |
| requested_at / responded_at / decided_at | DATETIME NULL | |
| requested_by_user_id / decided_by_user_id | INTEGER NULL | NULL en `requested_by` significaría "el agente"; hoy nunca ocurre. |

No hay importe pagado ni fecha de pago: eso es 2c.

### 3.3 `maintenance_tickets` (columna nueva)

| Columna | Tipo | Notas |
|---|---|---|
| provider_id | INTEGER NULL | **Convive con `assigned_to_user_id`, no lo sustituye ni lo anula.** "Responsable interno que lo persigue" y "quién hace el trabajo" son dos preguntas distintas; nada en el feedback del CEO pide que sean excluyentes, y anular una al fijar la otra destruye información. |

### 3.4 `documents` (columnas nuevas — se REUTILIZA el modelo existente, `models.py:487-498`)

Hoy tiene: `id, property_id, owner_id, tenant_id, file_name, file_url, doc_type, meta, uploaded_at`. **Cero filas, ningún router la toca.**

| Columna | Tipo | Notas |
|---|---|---|
| ticket_id | INTEGER NULL, index | Lo que faltaba para el 6.1. |
| account_id | INTEGER NULL, index | |
| expense_id | INTEGER NULL | Contrato con el área fiscal. |
| provider_id | INTEGER NULL | |
| stored_path | VARCHAR NULL | Ruta relativa dentro de `UPLOAD_DIR`, igual semántica que `TicketPhoto.stored_path` (`models.py:436`). |
| content_type | VARCHAR NULL | Imprescindible para distinguir un PDF de un XML al entregarlo. |
| bytes | INTEGER NULL | |
| sha256 | VARCHAR NULL | |
| uploaded_by_user_id | INTEGER NULL | Responde "quién subió esto", que `owner_id`/`tenant_id` no responden: ahí el usuario es el sujeto del documento, no quien lo cargó. |
| doc_date | DATE NULL | Fecha del comprobante, distinta de `uploaded_at`. |
| fiscal_year | INTEGER NULL, index | **Materializada, no calculada al vuelo.** La exportación por año fiscal (D-015) filtra por aquí y un índice sobre columna es barato; sobre expresión de fecha, no. |
| deleted_at | DATETIME NULL | Los bytes desaparecen del disco, la constancia de que existieron no. |

- **`file_name` YA EXISTE y se usa para el nombre original recibido.** No se añade `original_name`.
- **`file_url` queda deprecada y se escribe NULL para siempre.** Su nombre promete una URL pública y estos archivos jamás se sirven en público. SQLite no permite DROP COLUMN sin reconstruir la tabla, y reconstruir la tabla de comprobantes fiscales para ahorrar una columna vacía no vale el riesgo.
- **`DocTypeEnum` gana `invoice` y `quote`** (`models.py:55-60` ya tiene `contract, id_verification, policy, receipt, other`). Solo se apendiza; jamás se renombra. Es seguro incluso ante una reversión porque hoy ningún código lee `Document`.

### 3.5 `ticket_photos` (columna nueva)

| Columna | Tipo | Notas |
|---|---|---|
| phase | VARCHAR **NOT NULL DEFAULT 'report'** | Valores validados en Python: `report · work · closing`. |

**Corrección de hecho a las tres propuestas:** las tres afirman que en SQLite toda columna añadida por ALTER debe ser nullable y sin default. Es falso, y el propio repo lo desmiente: `main.py:162` ya ejecuta `ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1`. SQLite acepta NOT NULL en ADD COLUMN siempre que se dé un DEFAULT constante no nulo. Aprovecharlo aquí **elimina el UPDATE de backfill** que dos de las propuestas necesitaban.

Por qué la columna importa: `MAX_PHOTOS_PER_TICKET = 5` (`uploads.py:33`) es hoy un tope único compartido. Sin `phase`, un ticket con 5 fotos del inquilino deja al propietario sin margen para la evidencia de cierre **justo en el momento de cerrar**. Con `phase` hay dos cupos: 5 en `report` (inquilino, sin cambios) y 10 repartidos entre `work` y `closing` (propietario).

### 3.6 `ai_usage` (columna nueva)

| Columna | Tipo | Notas |
|---|---|---|
| account_id | INTEGER NULL, index | El tope de gasto es MENSUAL y GLOBAL (`ai_agent.py:26`, `budget_exhausted` en `ai_agent.py:113-115`). Con varias cuentas, la cotización automática de una administradora agotaría el presupuesto de todas. Esta área solo aporta la columna; la fórmula del tope por plan es del área de planes. |

### 3.7 `expenses` — contrato mínimo, NO se define aquí

La tabla es del **área fiscal**. Esta área solo exige que acepte, todas nullable salvo las dos primeras:
`property_id NOT NULL · account_id NOT NULL · ticket_id · provider_id · provider_name_snapshot · document_id · amount NUMERIC(12,2) · currency · expense_date DATE · fiscal_year INTEGER · created_by_user_id`.

Si al construir esta área la tabla aún no existe, la tarjeta de gasto **no se pinta** y `POST /owner/tickets/{id}/gastos` devuelve 501. Todo lo demás del área funciona igual. **Acordar estas columnas UNA vez con el área fiscal antes de escribir código:** definirlas dos veces con formas distintas obliga a reconstruir tablas en SQLite, que es la operación más cara del stack.

### 3.8 Índices

Todos con `CREATE INDEX IF NOT EXISTS`, que en SQLite es idempotente de forma nativa y no necesita el rodeo de `PRAGMA table_info`.

```
ix_providers_account        ON providers(account_id, is_active)
ix_documents_ticket         ON documents(ticket_id)
ix_documents_account_year   ON documents(account_id, fiscal_year)
ix_ticket_photos_phase      ON ticket_photos(ticket_id, phase)
ix_ticket_quotes_ticket     ON ticket_quotes(ticket_id)
ix_tickets_provider         ON maintenance_tickets(provider_id)
```

**Importante:** `create_all(checkfirst)` salta las tablas que ya existen y por tanto NO crea índices sobre columnas añadidas por ALTER. Los tres últimos hay que crearlos a mano.

---

## 4. Aislamiento — añadidos a `app/scoping.py`

Ni una consulta a `providers` fuera de este módulo. Regla vigente: lo ajeno devuelve **404, nunca 403** (`scoping.py:14-16`).

```python
def current_account_id(user) -> int:
    """Cuenta del usuario. Falla CERRADA y diagnosticable."""
    # 503, no lista vacía: una lista vacía se lee como "desaparecieron mis
    # proveedores"; el 503 dice exactamente qué falta.

def scoped_providers(db, user, include_archived=False) -> Query
def get_scoped_provider_or_404(db, user, provider_id) -> Provider
def assert_can_assign_provider(db, user, provider_id) -> Provider   # activo y de la cuenta, o 404
def scoped_documents(db, user) -> Query      # documento → ticket → scoped_tickets
def scoped_quotes(db, user) -> Query         # cotización → ticket → scoped_tickets
```

- `account_id` **jamás** se lee de un formulario, ni al crear ni al editar: un proveedor no puede migrarse de cuenta.
- `include_archived` es un único punto de decisión. Si una sola llamada olvida el parámetro, los archivados reaparecen en el desplegable y el propietario los vuelve a usar. Regla: **excluidos en toda lista de selección, incluidos en toda lectura histórica.**

---

## 5. Rutas

```
GET   /owner/proveedores                                   Directorio: listado, alta y filtros
POST  /owner/proveedores                                   CRUD por 'accion' ∈ {crear, editar, archivar,
                                                           restaurar, eliminar, redactar}
POST  /owner/tickets/{ticket_id}/actualizar                AMPLIADA: 'asignar_proveedor' y 'quitar_proveedor'
GET   /owner/tickets/{ticket_id}                           AMPLIADA: bloques Proveedor, Evidencia, Gasto,
                                                           Cotizaciones
POST  /owner/tickets/{ticket_id}/fotos                     Fotos de trabajo o cierre (multipart)
POST  /owner/tickets/{ticket_id}/documentos                Un comprobante por envío (multipart)
GET   /media/documentos/{documento_id}                     Descarga protegida, siempre attachment
POST  /owner/tickets/{ticket_id}/documentos/{doc_id}/eliminar   Retirar un comprobante mal subido
POST  /owner/tickets/{ticket_id}/gastos                    Gasto desglosado de este trabajo (punto 2.4)
POST  /owner/tickets/{ticket_id}/cotizaciones              'accion' ∈ {registrar, aprobar, rechazar}
POST  /owner/tickets/{ticket_id}/cotizaciones/solicitar    Esqueleto 7.4: hoy 403 o 501, nunca actúa
```

Todas exigen `_require_owner` (`owner_portal.py:70-77`, que admite owner y admin) salvo `GET /media/documentos/{id}`, que exige sesión viva y resuelve pertenencia por la cadena documento→ticket. **El inquilino no tiene ninguna ruta de documentos, ni de lectura ni de escritura.**

### 5.1 `POST /owner/proveedores` — el CRUD del punto 5

Una sola ruta despachada por el campo `accion`, mismo patrón que `owner_portal.py:219-280`.

- **crear / editar** — `account_id` y `created_by_user_id` del servidor. En `editar`, el id llega por formulario y se resuelve con `get_scoped_provider_or_404` (404 si es de otra cuenta).
- **archivar / restaurar** — `is_active` y `archived_at`. Deja de aparecer en todo selector; sigue resolviéndose en tickets, gastos y cotizaciones históricos.
- **eliminar** — el servidor cuenta referencias (tickets con `provider_id`, gastos, cotizaciones, documentos). **0 referencias → borrado físico real por la sesión del ORM. ≥1 → archiva y lo dice en pantalla con un mensaje explícito.** Así el botón "Eliminar" que pidió el CEO hace lo que él espera cuando puede, y nunca destruye la identidad de a quién se le pagó. Con `PRAGMA foreign_keys` apagado, SQLite no impediría dejar punteros muertos: **el conteo lo hace la aplicación porque la base no lo va a hacer.**
- **redactar** — borra `phone`, `email`, `tax_id`, `contact_name` y sella `redacted_at`; conserva `name`. Es la respuesta a una supresión ARCO del proveedor sin destruir el registro fiscal que lo cita. Irreversible, con `data-confirm`.

Todas dejan `audit(...)` con `action = "provider.<accion>"`.

### 5.2 `POST /owner/tickets/{ticket_id}/actualizar` — dos acciones nuevas

Sigue siendo **urlencoded**, sin `enctype`, sin `File(...)` en la firma.

- El id del proveedor llega en un **campo propio `proveedor_id`**, no sobrecargando `body` como hace hoy `asignar` (`owner_portal.py:254-268`). Esa sobrecarga es frágil y no se propaga.
- `assert_can_assign_provider` → 404 si es ajeno o está archivado.
- Deja `TicketEvent(event_type=assigned, body="Proveedor: <nombre>")`. Ningún miembro nuevo de enum (C-5).
- **No envía nada al proveedor, no genera enlace, no le da acceso.** La asignación es una anotación interna.

### 5.3 `POST /owner/tickets/{ticket_id}/fotos` — puntos 6.1 y 6.2

`multipart/form-data`. `get_scoped_ticket_or_404` **antes de leer un solo byte**. Reutiliza `save_ticket_photo` (`uploads.py:64-122`) sin tocar una línea: valida por bytes con Pillow, re-codifica a JPEG y destruye EXIF/GPS — que es exactamente el control que hace segura una foto tomada con la cámara del móvil.

- `phase` = `work` o `closing` según el campo del formulario.
- Topes: **3 archivos por petición**, 8 MB por archivo (`MAX_BYTES`), **10 fotos del propietario por ticket** entre las dos fases.
- Funciona **en cualquier estado, también después de resolver**, que es lo que pidió el CEO.
- Deja un solo `TicketEvent(photo_added, body="N foto(s) del trabajo")`.

### 5.4 `POST /owner/tickets/{ticket_id}/documentos` — el punto 6.1

`multipart/form-data`, **UN archivo por petición**. Módulo nuevo `app/docstore.py` (§6).

- Tipos: PDF, XML, JPG, PNG. **Word, Excel y ZIP quedan fuera a propósito:** son vectores de macro y no hay forma de sanearlos.
- Tope 5 MB, máximo 5 documentos por ticket.
- `account_id`, `property_id` y `provider_id` se derivan del ticket **en servidor**.
- Deja `TicketEvent(comment, body="Comprobante adjuntado por el propietario.")` — **sin nombre de archivo y sin importe**, porque esa línea de tiempo también la ve el inquilino (`tenant_ticket_detail.html:32`).

### 5.5 `GET /media/documentos/{documento_id}` — entrega endurecida

Calcada de `tenant.py:271-296`, con tres endurecimientos obligatorios en **todas** las respuestas:

```
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="<nombre saneado a ASCII>"
X-Content-Type-Options: nosniff
Content-Security-Policy: sandbox
```

**Nunca `inline`.** Un PDF servido inline se abre en el visor del navegador con el MISMO origen que la aplicación, donde `default-src 'self'` ya no protege nada. Un documento con `deleted_at` da 404. Un inquilino autenticado da 404, **no 403**: un 403 confirmaría que la factura existe.

*(Nota: la propuesta A temía una colisión con `/media/tickets/{ticket_id}/{photo_id}`. No existe — un parámetro de ruta nunca cruza `/`, así que un patrón de 3 segmentos no puede casar una URL de 4. Aun así se usa `/media/documentos/{id}`, que es más claro.)*

### 5.6 `POST /owner/tickets/{ticket_id}/gastos` — punto 2.4, la parte que cuelga del ticket

Solo propietario y admin. **Nunca el inquilino, nunca el proveedor.**

- `property_id` se toma de `ticket.property_id` **en servidor aunque el formulario mande otro**, misma regla que `tenant.py:174-176`.
- `provider_id` pasa por `assert_can_assign_provider` y se copia `provider_name_snapshot`.
- Precargado con el proveedor asignado, la fecha de hoy y `Property.price_currency` (`models.py:133`).
- Admite adjuntar el comprobante en la misma petición; si lo lleva, es multipart y guarda también la fila de `Document` con `expense_id`.
- **No deja `TicketEvent`**: el importe no debe aparecer en una línea de tiempo que ve el inquilino. La trazabilidad va por `audit()`.
- Si la tabla `expenses` aún no existe: 501 y la tarjeta no se pinta.

### 5.7 Cotizaciones — andamiaje del 7.4

`POST /owner/tickets/{id}/cotizaciones`, despachada por `accion`:

- **registrar** — alta MANUAL: el propietario teclea lo que le pasaron por teléfono o WhatsApp. `source='manual'`. **Disponible hoy y en todos los planes.** No es infraestructura especulativa: comparar dos precios antes de aprobar es la función que un propietario con veinte casas usa el lunes, exista o no la IA.
- **aprobar** — sella `status='aprobada'`, `decided_at`, `decided_by_user_id`; deja `TicketEvent(assigned, "Cotización aprobada: <proveedor>")`; y **solo si el ticket no tiene proveedor todavía**, fija `provider_id` \[supuesto: es la inferencia mínima y reversible; el CEO decide en §15 si debe hacer algo más\].
- **rechazar** — sella el estado.

**Aprobar NO notifica al proveedor, NO agenda visita, NO cambia el estado del ticket y NO crea ningún pagadero.** El texto del CEO se corta exactamente ahí ("Si el owner aprueba...") y no se inventa el final. Por eso `status` es VARCHAR y no Enum: cuando el CEO cierre la frase, ampliar la máquina de estados no requiere DDL ni arriesga la lectura del ORM.

`POST /owner/tickets/{id}/cotizaciones/solicitar` — **cuatro cerrojos, todos comprobados en servidor**, no pintando el botón deshabilitado (`mockmode.py:52-58` ya deja escrito por qué):

1. entitlement `quotes.auto_agent` de la cuenta → si falta, **403** con mensaje comercial.
2. bandera `QUOTES_AGENT_ENABLED` (por defecto `false`).
3. `ai_agent.is_configured()` (`ai_agent.py:91-93`) y `not ai_agent.budget_exhausted(db)`.
4. `DATA_MODE=live` con `LEGAL_CLEARANCE_REF`.

Con el entitlement pero cualquiera de los otros tres apagado → **501**, mismo precedente que `payments.py:154-159`. **En esta fase la ruta no intenta ninguna llamada saliente y no escribe `AiUsage`.** Existe para que la puerta esté probada antes de que haya algo detrás.

---

## 6. `app/docstore.py` — la única superficie realmente nueva

Los PDF y los XML **no se pueden re-codificar**: Pillow no los toca (`uploads.py:96-104` solo sirve para imágenes). Es el único punto del sistema donde se guarda un archivo tal como llegó, y por eso toda la seguridad se traslada a la validación de entrada y a las cabeceras de entrega.

1. **Sniff por bytes mágicos**, jamás por extensión ni por `Content-Type`: `%PDF-` para PDF; `<?xml` o `<` tras BOM/espacios para XML; JPEG/PNG por Pillow reutilizando el camino de imágenes.
2. **Extensión derivada del tipo detectado**, nunca del nombre recibido.
3. **Nombre en disco = uuid**. El nombre original va a `documents.file_name`, saneado, y solo se usa para mostrar y para el `filename` de la descarga.
4. Tope 5 MB. Rechazo temprano por `Content-Length` antes de leer el cuerpo.
5. Guardado en `UPLOAD_DIR/docs/{ticket_id}/`, con `os.makedirs(exist_ok=True)` en el primer guardado (mismo patrón que `uploads.py:105-107`). Fuera del árbol web y ya cubierto por `.gitignore`.
6. **El XML se guarda como bytes opacos y NO se parsea jamás.** Eso evita XXE y expansión de entidades por construcción. Si algún día hace falta leerlo: `defusedxml`, y solo `defusedxml`.
7. Se calcula y guarda `sha256`.

**Debe quedar escrito en `SECURITY.md`:** si alguien cambia la entrega a `inline` "para previsualizar", se abre el agujero entero.

---

## 7. Pantallas

Regla transversal, fácil de olvidar y silenciosa: **toda vista nueva debe inyectar `**_nav_badges(db, user)`** en su contexto (`owner_portal.py:83-99`) o los contadores del menú lateral desaparecen en esa pantalla.

| Pantalla | Plantilla | Contenido | CSP |
|---|---|---|---|
| Directorio de proveedores | `owner_providers.html` (nueva) | Tabla: Nombre · Oficio · Teléfono · Correo · Último trabajo · Trabajos · Estado · Acciones. Formulario de alta en `.form-grid`. Filtro de oficio como `<select>` dentro de un `<form method=get>`. "Ver archivados" es un enlace con `?archivados=1`, no un toggle de JS. Fila `.empty-row` con texto de arranque cuando no hay nada. | Cero JS y cero CSS en línea. Confirmación con `data-confirm`, ya cableado en `platform.js:17-24` — es un atributo de datos, no un manejador, así que no dispara la comprobación de `test_ui.py:92-93`. |
| Alta/edición de proveedor | `owner_provider_form.html` (nueva) | Bloques: Identificación · Contacto · Fiscal · Notas. En mock, **bajo** los campos de contacto se muestra el rango admitido y el motivo, no solo el error después de fallar. | `mock_mode` ya llega por `template_context()` (`mockmode.py:122-128`). |
| Detalle de ticket — Proveedor | `owner_ticket_detail.html` (se amplía tras la línea 57) | Junto al bloque "Responsable" que ya existe, un `<select>` de proveedores activos **ordenado en el servidor para poner primero los del oficio del ticket**, y "— Sin proveedor —". Texto fijo: *"Asignar un proveedor es una anotación interna. El proveedor no recibe acceso, ni enlace, ni fotos."* | Formulario POST propio con `{{ csrf_input(request) }}`, urlencoded, hacia `/actualizar`. El orden por oficio se resuelve en Python, no con script. |
| Detalle de ticket — Evidencia | idem | Dos formularios multipart separados: "Fotos del trabajo" y "Comprobante o factura". Galería `.photo-grid` separada en Reportado / Trabajo / Cierre. Lista de documentos con nombre, tipo, tamaño, quién y cuándo; el enlace **descarga**, no abre. | `enctype="multipart/form-data"` + `csrf_input`. Máximo 3 archivos por envío por el doble parseo del cuerpo. |
| Detalle de ticket — Gasto | idem | Concepto, importe, moneda, fecha, proveedor, deducible sí/no, adjunto. | — |
| Detalle de ticket — Cotizaciones | idem | Tabla (proveedor · importe · vigencia · estado · fecha) con Aprobar/Rechazar por fila, y alta manual. Debajo, "Pedir cotización automática" con el atributo **`disabled` real** y la leyenda del plan. | El `disabled` es un atributo, no una clase con JS; y el servidor devuelve 403/501 igualmente si alguien construye la petición a mano. |
| Lista de reportes | `owner_tickets.html` | Columna Proveedor y marca **"sin gasto"** en los resueltos, más filtro por proveedor junto a los de estado y propiedad (`owner_portal.py:110-138`). Esa marca es lo que impide llegar a marzo con veinte trabajos hechos y ningún importe capturado. | Filtro por GET, como los actuales. |
| Reportar un problema (inquilino) | `tenant_ticket_new.html` (junto a la línea 33) | **Dos** inputs de archivo con el MISMO `name="photos"`: "Tomar foto" con `capture="environment"` y "Elegir de la galería" sin `capture`. El input actual (múltiple) **se conserva sin cambios**: poner `capture` sobre él anularía `multiple` en varios navegadores y sería una regresión. | Cero cambios de servidor: `create_ticket` ya recibe `List[UploadFile]` (`tenant.py:164`) y ambos inputs con el mismo nombre llegan a la misma lista. Se **mantiene** `accept="image/jpeg,image/png,image/webp"` y no se abre a `image/*`: el accept restringido es lo que empuja a iOS a transcodificar HEIC a JPEG \[supuesto: verificar en un iPhone real\]. |
| Menú lateral | `base.html` (grupo Mantenimiento del rol owner, líneas 51-61) | Entrada "Proveedores" con `active == 'providers'`. Sin contador. \[toco archivo compartido: coordinar con las demás altas de menú de este lote\] | Un `<a>` más dentro de `.nav-group`. |

**Clases CSS:** usar solo las que EXISTEN — `.card`, `table`, `.btn`, `.btn-primary`, `.btn-primary-inline`, `.btn-ghost-inline`, **`.btn-danger-inline`** (`platform.css:322,348`), `.btn-disabled` (493), `.form-grid`, `.photo-grid` (494), `.timeline`, `.hint` (503), `.empty-row` (263), `.alert-*`, `.mock-banner`, `.inline-form`, `.actions-cell`. **NO usar `.btn-danger`, `.filters`, `.actions`, `.meta`, `.section-head` ni `.flash-ok`: no existen en el CSS.** Que `owner_ticket_detail.html:5,67` ya las use es deuda previa; se anota y no se propaga. Envolver la tabla del directorio en un contenedor con desbordamiento horizontal para el corte de 860 px.

### 7.1 Cadenas (D-014)

Todas las cadenas visibles **nuevas** salen de la plantilla a un diccionario plano `app/strings/es.py`, expuesto como global de Jinja `t('proveedores.titulo')` desde `register_template_globals` (`security.py:155-169`). Español, sin traducir nada, sin negociación de idioma, sin i18n. **Las 27 plantillas existentes NO se tocan**: reescribirlas ahora es riesgo sin beneficio. El patrón queda establecido con las nuevas. Los valores de `phase`, `status` y `source` se muestran a través de ese diccionario, no en crudo.

---

## 8. La cámara en móvil (punto 6.2) — recomendación cerrada

**Se elige `capture="environment"`. Se rechaza la cámara en página.**

| | `capture` (elegido) | `getUserMedia` + `<canvas>` |
|---|---|---|
| Coste | Un atributo HTML | ~100 líneas en `platform.js`, `<video>`, `<canvas>`, POST multipart construido a mano con la cabecera CSRF |
| CSP | Sin cambios | Sin cambios (el JS iría en el archivo), pero más superficie |
| `Permissions-Policy: camera=()` | **Sin cambios.** Esa cabecera gobierna `getUserMedia`, no la app de cámara del sistema que abre el selector de archivos \[supuesto: verificar en Android Chrome e iOS Safari\] | Hay que relajarla a `camera=(self)` — un control documentado en `SECURITY.md §8` |
| Contexto seguro | No hace falta | Exige HTTPS; hoy no lo hay en desarrollo local |
| Riesgo | Ninguno nuevo | La página obtiene un flujo de vídeo EN VIVO del interior de la vivienda de un inquilino |
| Peor caso | El navegador ignora `capture` y abre el selector: degradación silenciosa, no se pierde nada | Falla dura |

Lo único que se pierde es el reescalado en cliente, y el servidor ya reescala a 1568 px y borra el EXIF con GPS (`uploads.py:96-104`), así que la foto del móvil llega igual de limpia.

**Se añaden dos pruebas de candado:** falla si aparece `getUserMedia` en `platform.js`, y falla si desaparece `camera=()` de la cabecera de respuesta.

---

## 9. El punto 6.1, literalmente

El CEO escribió *"una vez resuelto el ticket, el owner puede agregar tickets o documentos"*. **Se interpreta "tickets" como lapsus por "fotos"**, porque el 6.2 dice explícitamente *"tomar fotos... al cerrarlos el owner"* y porque un ticket ya existe cuando se resuelve. Así se diseña.

Dato relevante para que el CEO decida (§15): la lectura literal —encadenar un ticket derivado a uno resuelto— es hoy **imposible por otra razón**: NINGUNA ruta permite al propietario crear un ticket; solo los crea el inquilino (`tenant.py:154-232`). Si eso es lo que quería, son una columna `parent_ticket_id`, una ruta y una pantalla, y **no están en este diseño**.

---

## 10. Puertas legales y banderas

> ### ⚠️ Puerta legal — D-016
> Proveedores, comprobantes, gastos y cotizaciones **se construyen ahora, se ejercitan en mock, y los datos reales entran cuando Legal firme**. No se inventa ningún criterio legal nuevo: se usa la puerta `DATA_MODE` que ya existe.
>
> Un plomero autónomo es una persona física: su nombre, su celular y su RFC son datos personales de un tercero que nunca aceptó nada. Por eso:
>
> | Campo | Control en `DATA_MODE=mock` |
> |---|---|
> | `providers.email` | `validate_mock_email` (`mockmode.py:84-98`) — **solo si el campo no viene vacío** |
> | `providers.phone` | `validate_mock_phone` (`mockmode.py:101-109`) — ya tolera vacío |
> | `providers.tax_id` | Rechazado con 400 en mock |
> | `providers.notes`, notas del gasto | **`reject_real_contact_in_text()`, guard NUEVO en `mockmode.py`** |
>
> **Error a evitar, verificado:** `validate_mock_email("")` **lanza 400**, porque calcula `domain = ""` y `""` no está en `MOCK_EMAIL_DOMAINS` (`mockmode.py:88-90`). Como el correo del proveedor es opcional, hay que comprobar que el campo trae algo antes de llamarla. Si no, será imposible dar de alta un proveedor sin correo.
>
> **El guard de texto libre no es opcional:** sin él, el campo de notas es el agujero por el que entra el teléfono real del plomero el primer día y el candado de D-016 queda abierto sin que nadie lo note. Rechaza en mock un correo o una secuencia de 10 dígitos dentro del texto. Falso positivo conocido: un folio de 10 dígitos se rechaza; solo actúa en mock, así que el coste es fricción en pruebas, y el mensaje de error debe decir exactamente qué se detectó.
>
> **Límite honesto y declarado, no disimulado:** no se puede validar el contenido de un PDF. Para los comprobantes el candado enforzable es la banda visible más `documents.meta='mock'` en cada fila creada en modo pruebas, que permite purgar con exactitud los archivos de esa época al pasar a live. El residual queda escrito.
>
> **Los gastos NO son pagos.** No hay dinero moviéndose ni datos bancarios de inquilino, así que no caen bajo `PAYMENTS_MODULE_ENABLED` ni bajo el catch-all 501 de `payments.py:154-159`, que solo cubre `/api/payments*`.

**Banderas de entorno** (patrón vigente de `mockmode.py:48-58`, leídas **siempre en el servidor**, nunca solo al pintar el menú):

| Bandera | Por defecto | Qué cierra |
|---|---|---|
| `PROVIDERS_MODULE_ENABLED` | `true` | Directorio y asignación |
| `TICKET_ATTACHMENTS_ENABLED` | `true` | Fotos y documentos del propietario |
| `QUOTES_AGENT_ENABLED` | `false` | Cotización automática (7.4) |
| `TICKET_EMAIL_INTAKE_ENABLED` | *no existe* | **No se crea. La ingestión de correo no se construye.** |

**Entitlements por plan** — se consumen por CLAVE, nunca comparando el nombre del plan:

| Clave | Planes | Nota |
|---|---|---|
| `providers.manage` | todos, **incluido el trial de 90 días** | Ver §15 |
| `tickets.attachments` | todos | |
| `quotes.manual` | todos | |
| `expenses.itemized` | todos | |
| `quotes.auto_agent` | **solo Enterprise+** | |

La función `has_entitlement(db, user, clave)` es del **área de planes**. Mientras no exista, la versión local devuelve `False` para `quotes.auto_agent` y `True` para el resto, y el esqueleto queda apagado sin romper nada.

**Estado de la cuenta:** con el trial vencido o la cuenta por encima de su límite de casas, las rutas de **escritura** de esta área devuelven 403 con mensaje comercial, pero **toda la lectura, la descarga de comprobantes y la exportación siguen funcionando**. Nunca se oculta ni se borra un dato por una razón de cobro: los comprobantes fiscales del propietario no pueden quedar secuestrados por una suscripción vencida.

**Los planes NO se guardan en `PlatformSetting`**: es clave/valor GLOBAL de texto (`models.py:198-212`) y un plan por cuenta ahí sería un ajuste global mal usado.

---

## 11. Migración

`platform.db` (la base REAL del CEO) está **sin migrar desde E1**: le faltan 9 tablas y 7 columnas de `users`. No hay Alembic ni tabla de versión.

0. **Antes de nada, una sola vez:** copiar `platform/data/platform.db` a `platform.db.bak-AAAAMMDD`. Es un paso de migración, no un servicio de respaldo (los respaldos los canceló el CEO). El primer arranque contra esa base aplicará de golpe todo lo pendiente de E1 **además** de lo de esta área.
1. **`scripts/migrate_c.py --dry-run`**: imprime el DDL exacto sin tocar nada. Se corre primero contra `platform-mock.db` (que sí está al día), después contra la copia `.bak`, y solo entonces contra la real.
2. **PRERREQUISITO BLOQUEANTE — `UPLOAD_DIR`.** Hoy `uploads.py:30` no se ramifica por `DATA_MODE` mientras `db.py:33-36` sí lo hace: los ids de ticket **colisionan** entre `platform-mock.db` y `platform.db` y dos tickets distintos comparten `data/uploads/tickets/7/`. Con fotos ya es malo; con facturas significa mezclar un comprobante real con basura de pruebas. Ramificar a `data/uploads` (live) y `data/uploads-mock` (mock), respetando el `UPLOAD_DIR` explícito del entorno que usan las pruebas. **Mover a mano las fotos de prueba existentes ANTES del primer arranque en live**: ninguna ruta las busca en dos sitios.
3. `Base.metadata.create_all(bind=engine)` (`main.py:227`) crea `providers` y `ticket_quotes` completas. Son tablas nuevas: **sí admiten NOT NULL**. Requisito de orden: `accounts` (D-013) debe existir antes; como las FK no se imponen no hay fallo físico si no está, pero el backfill del paso 8 la necesita.
4. Ampliar `_ensure_ticket_columns()` (`main.py:183-215`) con una línea en el diccionario `wanted`: `"provider_id": "ALTER TABLE maintenance_tickets ADD COLUMN provider_id INTEGER"`.
5. Nueva `_ensure_document_columns()`: `PRAGMA table_info(documents)` + ALTER de `ticket_id, account_id, expense_id, provider_id, stored_path, content_type, bytes, sha256, uploaded_by_user_id, doc_date, fiscal_year, deleted_at`. La tabla tiene **0 filas**: no hay backfill.
6. Nueva `_ensure_ticket_photo_phase()`: `ALTER TABLE ticket_photos ADD COLUMN phase VARCHAR NOT NULL DEFAULT 'report'`. **Sin UPDATE de backfill**: el DEFAULT rellena las filas existentes en el propio ALTER. Es legal en SQLite y el repo ya lo hace en `main.py:162`.
7. Nueva `_ensure_ai_usage_account()`: `ALTER TABLE ai_usage ADD COLUMN account_id INTEGER`, y backfill desde `users.account_id` por `user_id` **solo si esa columna de `users` ya existe**; si no, se salta sin error.
8. Backfill de cuenta cuando D-013 aterrice: el mismo paso que rellena `users.account_id` debe rellenar `providers.account_id`, `documents.account_id` y `ticket_quotes.account_id`. Hoy es un no-op (tablas vacías); se deja escrito porque el mismo guion correrá sobre la base real más tarde, y una fila con `account_id` NULL provoca un 503 diagnosticable — nunca una fuga.
9. Índices del §3.8 con `CREATE INDEX IF NOT EXISTS`.
10. Registrar `platform_settings['schema_version'] = 'C1'` al terminar. Es lo único que distingue una base a medio migrar de una base nueva, y hoy son indistinguibles.
11. **Todas** las funciones `_ensure_*` empiezan con la guarda `if not engine.url.get_backend_name().startswith("sqlite"): return` y con `cols = PRAGMA table_info(...); if not cols: return` (patrón de `main.py:176-178` y `main.py:210-212`), y se registran en `on_startup()` **después** de `create_all` y de las tres existentes (`main.py:227-230`).
12. **Cero DROP COLUMN, cero cambios de tipo, cero renombrados de valores de enum.** `documents.file_url` se queda donde está, vacía para siempre.
13. **Cero miembros nuevos en `TicketEventTypeEnum`** (C-5). `DocTypeEnum` gana `invoice` y `quote`, que es cambio de código sin DDL y sin riesgo hacia atrás porque ningún código lee `Document` hoy.

---

## 12. Pruebas

Dos suites nuevas, `platform/tests/test_providers.py` y `platform/tests/test_ticket_attachments.py`, con el **patrón obligatorio del repo**: variables de entorno ANTES de importar la app (`DATABASE_URL` a sqlite en `tempfile.mkdtemp`, `APP_ENV=dev`, `DATA_MODE=mock`, `UPLOAD_DIR` temporal) → `from app.main import app` → `with TestClient(app) as c:` para disparar el startup → sembrar con `SessionLocal()` guardando solo ids enteros → un `TestClient` por usuario → login por el formulario HTML extrayendo `csrf_token` con regex y esperando 302 con `follow_redirects=False`. Cada una define su `check(n, c, e)`, imprime PASS/FAIL, cierra con `RESULTADO: N pasaron, M fallaron` y `sys.exit(1 if fail else 0)`. `run_all.py` las descubre solas. **Sin rutas absolutas de Windows.**

*(Deuda a arreglar de paso, verificada: `test_migrate.py` no imprime la línea RESULTADO y sus 7 PASS no suman al total; `test_migrate.py:3-4` y `test_ui.py:156` llevan rutas absolutas `C:\Aura\...` que revientan en cualquier CI que no sea esta máquina.)*

La lista completa va en `test_plan`.

---

## 13. Riesgos

1. **Memoria en las subidas.** `CSRFMiddleware` lee el cuerpo multipart entero en memoria y lo vuelve a parsear (`security.py:194-207`): 3 archivos de 8 MB son ~48 MB retenidos por petición concurrente en capa gratuita. Mitigado con 3 archivos por envío en fotos, 1 en documentos, 5 MB por documento y rechazo temprano por `Content-Length`. Sin esos topes, subir comprobantes es un agotamiento de memoria trivial.
2. **PDF y XML no se pueden sanear.** Único punto del sistema donde se guarda lo que llegó. Defensa entera en sniff + topes + cabeceras de entrega. Si alguien cambia `attachment` por `inline` "para previsualizar", se abre el agujero.
3. **Sin FKs impuestas** (`PRAGMA foreign_keys` no se activa en ninguna parte del código; SQLite lo deja apagado por defecto): un DELETE por SQL directo deja punteros muertos sin ningún error. El borrado lógico, el conteo de referencias en la aplicación y `provider_name_snapshot` son la única protección real. Añadir `ticket_quotes` al `cascade` del ORM de `MaintenanceTicket` (como `photos` y `events`, `models.py:423-424`) y **dejar `documents` FUERA a propósito**: un comprobante fiscal debe sobrevivir al ticket.
4. **HEIC.** Una foto de iPhone en "Alta eficiencia" llega como HEIC y Pillow la rechaza con un mensaje incomprensible. Mitigado conservando el `accept` restringido y ampliando el texto del error (`uploads.py:90-92`) para nombrar HEIC y la ruta Ajustes › Cámara › Formatos › Más compatible. \[supuesto: verificar con un iPhone real antes de dar el 6.2 por cerrado\]
5. **`capture` frente a `Permissions-Policy`.** La spec de HTML Media Capture permite que un navegador aplique la política de cámara. Hoy ni Chrome Android ni iOS Safari lo hacen \[supuesto: probar en dispositivo real\]. Peor caso: degradación al selector de archivos, no un fallo.
6. **`scoped_providers` y los archivados.** Una sola llamada que olvide `include_archived` hace reaparecer proveedores archivados en el desplegable y el propietario los vuelve a usar. Un único punto de decisión, ninguna consulta a `providers` fuera de `scoping.py`.
7. **Crecimiento de almacenamiento.** 5 fotos del inquilino + 10 del propietario + 5 documentos ≈ 145 MB por ticket en el peor caso. Hace falta una cuota por cuenta \[supuesto: el volumen no está dimensionado en esta área\] o el disco se llena antes de que el plan se venda.
8. **El mayor riesgo del 7.4:** una solicitud de cotización enviaría a un tercero **fotos del interior de la vivienda de un inquilino**. Por eso hay cuatro cerrojos, la selección de fotos sería manual y por defecto no saldría ninguna, y hoy la ruta no intenta nada.
9. **La ingestión de correo no se construye,** y no solo por falta de infraestructura: sin verificación SPF/DKIM/DMARC y sin lista blanca remitente→arrendamiento, cualquiera que aprenda la dirección crea tickets en la cola de cualquier propietario. Es inyección directa a la bandeja del propietario y a un agente que gasta dinero.
10. **Correo saliente síncrono.** `email_utils.py` es `smtplib` bloqueante con una sola plantilla y sin cuenta SMTP productiva. Por eso este diseño no envía nada a nadie; conectarlo bloquearía el hilo de la petición.
11. **Dependencias entre áreas:** `accounts` + `user.account_id` (D-013), `has_entitlement` (planes) y `expenses` (fiscal). Cada una entra por un solo punto. Si `expenses` no llega, el módulo funciona sin gastos; si `has_entitlement` no llega, el agente sigue apagado; **si `accounts` no llega, el módulo no arranca** — es la única dependencia dura, y es dura porque D-013 lo decidió así.

---

## 14. Qué se injertó de las propuestas perdedoras

De **A (mínimo)**: el despacho por `accion` para el CRUD (6 acciones en 1 ruta en vez de 7 rutas) · el hallazgo de `validate_mock_email("")` · reutilizar `TicketEventTypeEnum` sin añadir miembros · ordenar el selector de proveedores por el oficio del ticket en el servidor · la prueba de regresión sobre `/actualizar` urlencoded como la más importante de todo el lote · usar solo clases CSS existentes.

De **C (producto)**: `reject_real_contact_in_text()` para el campo de notas · campo propio `proveedor_id` en vez de sobrecargar `body` · la marca "sin gasto" en los resueltos y el filtro por proveedor · `fiscal_year` materializada en `documents` · precarga con `Property.price_currency` · el borrado híbrido (físico si 0 referencias, archivado si las hay).

Se **rechazó** de B: la exclusión mutua entre `provider_id` y `assigned_to_user_id` (destruye el responsable interno sin que nadie lo pidiera) y los miembros nuevos de `TicketEventTypeEnum`. Se **rechazó** de C: dar al inquilino acceso a `/owner/documentos/{id}` (contradice su propia prueba y le enseña los importes) y `address_text`. Se **rechazó** de A: `providers.owner_user_id` como raíz de aislamiento (viola D-013).

**Errores de hecho que compartían las tres, corregidos:** (a) SQLite **sí** admite `ADD COLUMN ... NOT NULL DEFAULT <constante>` — `main.py:162` ya lo hace, y eso elimina el backfill de `phase`; (b) `Document` **no tiene** `stored_path`, `content_type`, `bytes` ni `sha256`, pero **sí tiene `file_name`**, así que no hace falta añadir `original_name`; (c) no existe ninguna colisión de rutas de media, porque un parámetro de ruta nunca cruza `/`.
