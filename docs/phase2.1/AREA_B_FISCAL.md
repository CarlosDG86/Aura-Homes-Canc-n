<!-- Generado por el panel de diseño del 2026-09-08. Ganadora: Libro de gastos con catálogo puente y paquete de auditoría (producto) -->

# Fase 2 · Área B — Gastos, módulo fiscal y exportación para auditoría

**Fecha:** 2026-09-08 · **Estado:** diseño cerrado, listo para construir. Sustituye a las tres propuestas de arquitectura del 2026-09-08.
**Alcance:** puntos 2.3, 2.4 y 7.3 del feedback del CEO, y la exportación de D-015.
**Depende de:** Área A (`accounts`, D-013) y del área de proveedores (`vendors`, punto 5). Ninguna de las dos bloquea la construcción: ver §3.4 y §11.

> ⚠️ **Puerta legal (D-016).** Gastos, comprobantes y proveedores caen bajo la puerta que YA existe (`DATA_MODE`). Se construye ahora, se prueba en mock, y los datos reales entran cuando Legal firme y el CEO lo confirme por separado. **No se inventa ningún criterio legal nuevo.** Ver §9.

> ⚠️ **Lo que este módulo NO hace.** No es asesoría fiscal. No calcula impuestos ni retenciones. No determina deducibilidad. No decide qué es gasto corriente y qué es mejora capitalizable (eso lo marca el propietario). No deprecia. No valida ni timbra CFDI ante el SAT. No presenta ninguna declaración. Registra, clasifica, etiqueta y entrega. *«Los datos son lo que importa»* — CEO, 2026-09-07.

---

## 0. Correcciones de hecho sobre el estado del código

Las tres propuestas se apoyaron en datos que hay que corregir antes de construir. Verificado hoy contra el fuente:

| Afirmación circulante | Realidad verificada |
|---|---|
| `owner_portal.py`, `pages.py`, `tenant.py`, `payments.py` | Viven en `platform/app/routers/`, no en `platform/app/`. `scoping.py`, `uploads.py`, `security.py`, `models.py`, `main.py`, `mockmode.py` sí están en `platform/app/`. |
| «20 tablas en models.py» | **19** (`grep -c __tablename__` = 19). |
| «a platform.db le faltan 9 tablas» | Le faltan **8**: `ai_usage`, `announcement_recipients`, `announcements`, `messages`, `platform_settings`, `sessions`, `ticket_events`, `ticket_photos`. Tiene 11 tablas, 3 usuarios y 3 propiedades. |
| «`documents` está vacía y solo existe en la base mock» | Existe en **ambas** bases con 0 filas. Un `ALTER TABLE documents` tocaría también la base real del CEO. |
| `Document` en models.py:470-481 / :474-486 | `Document` es **models.py:487-498**. El rango 476-485 es `Payment`, y `Payment.receipt_document_id` es **models.py:485**. |
| `scoped_tickets` en scoping.py:127-140 / :143-147 | Líneas reales de `scoping.py`: `owned_properties` **60**, `get_owned_property_or_404` **84**, `assert_can_assign_property` **91**, `scoped_leases` **111**, `scoped_tickets` **133**, `get_scoped_ticket_or_404` **150**, `scoped_users` **160**. |
| «consultar tipos de cambio oficiales añade una dependencia» | **Falso.** `httpx==0.28.1` ya está en `requirements.txt` y `google_sso.py` lo importa al cargar. La objeción válida a una API de tipos de cambio es otra: llamada saliente, punto de fallo, y una cifra cuyo origen no se puede justificar ante un auditor. |
| «dos suites de prueba conservan rutas absolutas de Windows» | **No reproducible.** `grep -rn 'C:\\|C:/' platform/tests/*.py` no devuelve nada; todas usan `tempfile.mkdtemp()` y `pathlib.Path(__file__).resolve().parent.parent`. No gastar esfuerzo ahí. |
| «snapshot con `python -m app.backup`» | `backup.py:36` toma `BACKUP_DATA_DIR` con valor por defecto `/data` — el volumen de Fly, que está suspendido. En local hay que pasar `BACKUP_DATA_DIR=<repo>/platform/data`. Ver §10 paso 0. |
| `.btn-danger` no existe en el CSS | Correcto, pero **sí existe `.btn-danger-inline`** (platform.css:322, 348). Igual con `.flash-ok` (no existe) frente a `.flash-urgent` y `.flash-info` (platform.css:502-503). Sí existen `.hint`, `.muted`, `.empty-row`, `.sync-table`, `.inline-form`, `.badge`, `.status`, `.form-grid`, `.timeline`, `.photo-grid`, `.nav-item`, `.nav-badge`. |
| `test_migrate.py` no suma al total | Correcto: termina en `sys.exit(0 if ok else 1)` sin imprimir la línea `RESULTADO:`. Error a no repetir. |

Además, un hecho que ninguna propuesta conectó y que sí afecta a este módulo: **`Permissions-Policy: camera=()`** (security.py:246) bloquea la cámara por cabecera. Esto **no** afecta a la subida de comprobantes —un `<input type="file">` con `accept` abre el selector del sistema operativo y permite elegir una foto ya tomada— y **sí** afecta al punto 6.2 del CEO, que necesita `capture=`. **El módulo fiscal no debe relajar esa cabecera**; si hay que tocarla, es decisión del área de tickets y con su propia justificación.

---

## 1. Qué se construye, en una frase

Un **libro de gastos por propiedad**, capturable en menos de treinta segundos, del que en marzo sale un **paquete ZIP verificable** que el propietario descarga y entrega a su contador. La jurisdicción no bifurca la captura: se clasifica una vez contra un catálogo propio, y ese catálogo es el puente que lleva cada categoría a su línea de **IRS Schedule E** y a su **concepto SAT**.

---

## 2. Catálogo fiscal — dónde vive y por qué

**Decisión: el catálogo vive en un módulo de Python (`platform/app/fiscal_catalog.py`), no en una tabla.**

Razones, en orden:

1. Es dato de referencia que cambia con la **ley**, no con el usuario. Va versionado en git, es idéntico en `platform.db` y en `platform-mock.db`, y un cambio de mapeo se revisa en un diff. Es exactamente lo que pide la instrucción 1 del CEO.
2. Una tabla con CRUD de admin permite que el mapeo **diverja entre mock y live** en silencio, y una siembra idempotente que «nunca hace UPDATE» garantiza esa divergencia en cuanto alguien edite una fila.
3. Ahorra una tabla, una pantalla de admin, una función de siembra con reconciliación y su prueba de no-duplicación.

**Coste aceptado:** cambiar el mapeo exige un despliegue. En este producto un despliegue es un push a `main`; es aceptable.

`expenses.category_code` se guarda como **VARCHAR, jamás como `Enum` de SQLAlchemy**: los Enum se persisten con el NOMBRE del miembro y un valor desconocido en la base rompe la lectura del ORM. Un catálogo fiscal está condenado a crecer.

**UN catálogo propio con DOS columnas de mapeo, no dos catálogos.** Dos catálogos obligarían a clasificar el mismo gasto dos veces, garantizarían que ambas clasificaciones divergieran con el tiempo y dejarían en el limbo a una propiedad que cambia de jurisdicción. Con un catálogo puente, la ambigüedad se concentra en ~15 filas que un contador revisa de una sentada, en vez de repartirse entre miles de gastos.

### 2.1 Forma de cada entrada

```python
CATALOG_VERSION = "2026.1"   # se estampa en el manifiesto de cada paquete

@dataclass(frozen=True)
class Categoria:
    code: str                 # estable, NUNCA se renombra
    label_es: str
    help_es: str              # texto de ayuda bajo el select
    irs_schedule_e_line: str | None   # None = sin equivalencia limpia
    sat_concepto: str | None
    is_capital_default: bool
    requires_receipt: bool
    sort_order: int
    active: bool
```

### 2.2 Siembra inicial (15 códigos)

| code | label_es | IRS Schedule E | Concepto SAT (LISR art. 115) |
|---|---|---|---|
| `mantenimiento` | Mantenimiento y reparaciones | 14 Repairs | Mantenimiento y conservación |
| `mejora_capital` | Mejora o remodelación (capitalizable) | 18 Depreciation | Inversión — no deducible en el ejercicio |
| `predial` | Impuesto predial | 16 Taxes | Impuesto predial |
| `servicios` | Servicios (agua, luz, gas) | 17 Utilities | Servicios |
| `seguro` | Seguro del inmueble | 9 Insurance | Primas de seguros |
| `admin_cuota` | Cuota de administración / condominio | 7 Cleaning and maintenance | Mantenimiento y conservación |
| `honorarios_admin` | Honorarios de administración de la propiedad | 11 Management fees | Salarios y honorarios |
| `honorarios_prof` | Honorarios legales y contables | 10 Legal and other professional fees | Honorarios profesionales |
| `intereses_hipoteca` | Intereses de crédito hipotecario | 12 Mortgage interest | Intereses reales por préstamo |
| `publicidad` | Publicidad y promoción del inmueble | 5 Advertising | Gastos de publicidad |
| `comisiones` | Comisiones de arrendamiento | 5 Advertising | Comisiones y mediaciones |
| `limpieza` | Limpieza y jardinería | 7 Cleaning and maintenance | Mantenimiento y conservación |
| `suministros` | Materiales y suministros | 15 Supplies | Materiales |
| `viajes` | Traslados a la propiedad | 6 Auto and travel | Gastos de traslado |
| `otro` | Otro | *(vacío)* | *(vacío)* |

Cada entrada termina, en pantalla y en el paquete, con: *«Etiquetado orientativo. Confírmalo con tu contador.»*

**Códigos retirados:** nunca se borran del módulo; pasan a `active=False` y a un diccionario `RETIRADOS` para que un gasto histórico siga renderizando su etiqueta.

**Jurisdicción y catálogo:** el catálogo es único; lo que cambia con la jurisdicción es **qué columna de mapeo se imprime** en el resumen y en el paquete, y qué avisos se muestran. La jurisdicción **no cambia cómo se captura ni cómo se guarda** un gasto. Bifurcar el modelo por jurisdicción sería el error caro.

---

## 3. Modelo de datos

Regla de SQLite que gobierna todo: **`NOT NULL` solo es viable en tablas nuevas**, que nacen de `create_all()`. Toda columna añadida por `ALTER TABLE` a una tabla existente debe ser nullable o llevar default, porque SQLite no permite `DROP COLUMN` ni cambiar tipos con facilidad. Y `PRAGMA foreign_keys = 0` en ambas bases: las FK están declaradas por documentación y por el ORM, **no las impone el motor**.

### 3.1 `expenses` — nueva

| Columna | Tipo | Nota |
|---|---|---|
| `id` | INTEGER PK | |
| `account_id` | INTEGER NULL, idx | D-013. Nullable + backfill: el orden de construcción con el Área A no bloquea. |
| `property_id` | INTEGER NOT NULL, idx | El aislamiento y la exportación son por propiedad. |
| `ticket_id` | INTEGER NULL, idx | Punto 2.4. Un ticket puede tener varios gastos; un gasto puede no tener ticket. |
| `expense_date` | DATE NOT NULL | |
| `tax_year` | INTEGER NOT NULL, idx | Se deriva de `expense_date` al escribir, no se pide en el formulario. Materializado para que el índice compuesto sirva. |
| `category_code` | VARCHAR(40) NOT NULL | Contra `fiscal_catalog`. **VARCHAR, no Enum.** |
| `vendor_id` | INTEGER NULL | Área de proveedores. Declarado **sin `ForeignKey`** para no acoplar el arranque a una tabla que aún no existe. |
| `vendor_name_raw` | VARCHAR(160) NULL | Instantánea de texto libre: sobrevive al borrado del proveedor y permite capturar sin haberlo dado de alta antes. |
| `tax_doc_ref` | VARCHAR(64) NULL | UUID del CFDI en MX o nº de factura/recibo en US. Una columna sirve a las dos jurisdicciones. **Se teclea; no se extrae de ningún XML.** |
| `amount` | NUMERIC(14,2) NOT NULL | Lo que se pagó. **Nunca se sobrescribe.** |
| `currency` | VARCHAR(3) NOT NULL default `'MXN'` | |
| `base_currency` | VARCHAR(3) NOT NULL | Copia de la moneda base de la cuenta en el momento de la captura. |
| `amount_base` | NUMERIC(14,2) **NULL** | Derivado y congelado. **NULL cuando no hay tipo de cambio disponible** — ver §5. |
| `fx_rate` | NUMERIC(18,8) NULL | Congelado en la fila. 1 cuando `currency == base_currency`. |
| `fx_rate_date` | DATE NULL | |
| `fx_source` | VARCHAR(40) NULL | `'manual'`, `'DOF'`, `'IRS-yearly-average'`… |
| `is_capital` | BOOLEAN NOT NULL default 0 | Mejora capitalizable frente a gasto corriente. Es la única distinción que ambas jurisdicciones tratan distinto: en `True`, el mapeo salta a *18 Depreciation* aunque la categoría sea `mantenimiento`. |
| `payment_method` | VARCHAR(30) NULL | Texto corto libre. |
| `note` | TEXT NULL | |
| `status` | VARCHAR(16) NOT NULL default `'confirmado'` | `confirmado` \| `borrador`. Todo lo que genera la automatización nace `borrador`. |
| `adjusts_expense_id` | INTEGER NULL | Asiento de ajuste sobre un gasto de un año ya cerrado. |
| `data_mode` | VARCHAR(8) NOT NULL | Sello del modo en que nació la fila (`mock`/`live`). Ver §9.2. |
| `voided_at` / `voided_by_user_id` / `voided_reason` | DATETIME / INTEGER / VARCHAR(200), NULL | **No hay DELETE.** Ver §3.7. |
| `created_by_user_id` | INTEGER NULL | |
| `created_at` / `updated_at` | DATETIME server_default | |

**No lleva columna `locked`.** El bloqueo por cierre de año se **deriva** consultando `fiscal_year_closures` en el momento de la escritura. Una bandera denormalizada puede quedar desincronizada del cierre real; una consulta pequeña en un POST no cuesta nada.

### 3.2 `expense_receipts` — nueva

| Columna | Tipo | Nota |
|---|---|---|
| `id` | INTEGER PK | |
| `expense_id` | INTEGER NOT NULL, idx | |
| `kind` | VARCHAR(10) NOT NULL | `imagen` \| `pdf` \| `xml` |
| `stored_path` | VARCHAR NOT NULL | Relativo a `UPLOAD_DIR`, nunca absoluto — mismo contrato que `TicketPhoto` (models.py:434-449). |
| `original_name` | VARCHAR(200) NULL | Solo para mostrarlo; nunca se usa como nombre en disco. |
| `content_type` | VARCHAR(80) NOT NULL | Canónico, decidido por el servidor. |
| `bytes` | INTEGER NOT NULL | |
| `sha256` | VARCHAR(64) NOT NULL | Lo que convierte el archivo en evidencia y detecta corrupción del volumen. |
| `recoded` | BOOLEAN NOT NULL default 0 | 1 solo en imágenes, que sí pasan por Pillow. |
| `uploaded_by_user_id` | INTEGER NULL | |
| `created_at` | DATETIME server_default | |

**No se reutiliza `documents`.** Razón, verificada: `documents` (models.py:487-498) tiene `tenant_id` y un `doc_type` que incluye `id_verification` (models.py:55-60), y `Payment.receipt_document_id` la apunta desde 2c (models.py:485). Meter comprobantes fiscales del propietario en la misma tabla que las identificaciones oficiales de inquilinos pone dos regímenes de acceso distintos bajo un solo helper, y obliga a 2c y a este módulo a compartir almacén sin columna que los distinga. `documents` se deja intacta y muerta.

### 3.3 `fx_rates` — nueva

`id` PK · `account_id` INTEGER NULL · `currency_from` VARCHAR(3) NOT NULL · `currency_to` VARCHAR(3) NOT NULL · `rate_date` DATE NOT NULL · `rate` NUMERIC(18,8) NOT NULL · `kind` VARCHAR(16) NOT NULL (`diario` \| `promedio_anual`) · `tax_year` INTEGER NULL · `source` VARCHAR(40) NOT NULL · `note` VARCHAR(200) NULL · `entered_by_user_id` INTEGER NULL · `created_at` DATETIME · **UNIQUE(`account_id`,`currency_from`,`currency_to`,`rate_date`,`kind`)**

Tabla de **consulta** para prerrellenar el `fx_rate` del gasto, no para recalcularlo después. `source` es NOT NULL a propósito: toda tasa debe poder responder «de dónde salió esto» ante un auditor.

### 3.4 `fiscal_year_closures` — nueva

`id` PK · `account_id` INTEGER NULL · `property_id` INTEGER NULL (NULL = toda la cuenta) · `tax_year` INTEGER NOT NULL · `closed_at` DATETIME NOT NULL · `closed_by_user_id` INTEGER NULL · `reopened_at` DATETIME NULL · `reopened_by_user_id` INTEGER NULL · `reopen_reason` VARCHAR(300) NULL · `export_sha256` VARCHAR(64) NULL · **UNIQUE(`account_id`,`property_id`,`tax_year`)**

Tabla y **no** una clave en `platform_settings`: esa tabla es clave/valor **global** sin scoping (models.py:208-212); meter el `property_id` dentro de la cadena de la clave es una ACL con tipo string, y no deja actor, fecha ni motivo de reapertura.

### 3.5 `fiscal_exports` — nueva

`id` PK · `account_id` INTEGER NULL · `owner_user_id` INTEGER NOT NULL, idx · `tax_year` INTEGER NOT NULL · `property_id` INTEGER NULL · `stored_path` VARCHAR NOT NULL · `bytes` INTEGER NOT NULL · `sha256` VARCHAR(64) NOT NULL · **`includes_ticket_photos` BOOLEAN NOT NULL default 0** · `expense_count` INTEGER · `receipt_count` INTEGER · `missing_fx_count` INTEGER · `excluded_other_mode_count` INTEGER · `catalog_version` VARCHAR(16) · `data_mode` VARCHAR(8) NOT NULL · `created_by_user_id` INTEGER NULL · `created_at` DATETIME

Es la memoria de **qué salió de la plataforma**. `includes_ticket_photos` es columna y no nota porque es el dato que importa si algún día un inquilino pregunta.

### 3.6 `expense_recurrences` — nueva, **solo el modelo (Fase B-2)**

`id` PK · `account_id` NULL · `property_id` NOT NULL, idx · `category_code` NOT NULL · `amount` NOT NULL · `currency` NOT NULL · `vendor_id` NULL · `frequency` VARCHAR(12) (`mensual`\|`bimestral`\|`anual`) · `day_of_month` INTEGER NULL · `month_of_year` INTEGER NULL · `next_run_date` DATE NOT NULL · `active` BOOLEAN default 1 · `note` VARCHAR(200) NULL · `created_by_user_id` NULL · `created_at` DATETIME

Predial, seguro y cuota de administración son el grueso del volumen anual y son idénticos cada vez. **La tabla se crea ahora** para no migrar después; **las rutas y la pantalla se dejan para la segunda tanda.** Materialización **perezosa** al abrir `/owner/fiscal`, comparando `next_run_date` con hoy: no hay cron ni worker, el despliegue es un único proceso FastAPI. Todo lo que genere nace `status='borrador'`.

### 3.7 Anular, no borrar

No existe ninguna ruta de borrado duro de un gasto. `accion=anular` exige motivo (400 sin él, igual que `resolver` exige nota hoy en owner_portal.py:245-247), fija `voided_at`/`voided_by_user_id`/`voided_reason`, saca la fila de los totales y **la mantiene visible, tachada, en la lista y en el CSV con estado `anulado`**. Un borrado duro dejaría comprobantes huérfanos en disco y haría irreproducible un paquete ya entregado al contador.

### 3.8 Cambios en tablas existentes

| Tabla | Acción | Columnas |
|---|---|---|
| `properties` | ALTER | `tax_jurisdiction VARCHAR NULL` — `'MX'` \| `'US'` \| `'BOTH'`. NULL hereda de la cuenta; si la cuenta tampoco la tiene, `'MX'`. |
| `accounts` (D-013) | ALTER, con guarda | `default_tax_jurisdiction VARCHAR NULL default 'MX'` · `base_currency VARCHAR NULL default 'MXN'` |
| `documents` | **sin cambio** | Explícito, para que nadie «aproveche» la tabla vacía. |
| `maintenance_tickets` | **sin cambio** | El vínculo vive en `expenses.ticket_id`. Poner un importe en el ticket forzaría 1:1 y habría que deshacerlo con la segunda factura. |
| `platform_settings` | **sin cambio** | |

**Una sola columna de jurisdicción en la propiedad, no dos.** La única pregunta que este módulo le hace a la jurisdicción es *«¿qué columnas de mapeo imprimo para los gastos de esta casa?»*, y eso lo contesta la propiedad. Dónde declara el contribuyente solo fija el **valor por defecto**, que vive en la cuenta. Si el Área A necesita un `country` para direcciones o filtros, es su columna, no la mía. Va en la propiedad y no solo en la cuenta porque una administradora puede tener casas a ambos lados de la frontera y una jurisdicción por cuenta clasificaría mal todo el portafolio **en silencio**, con el error apareciendo justo en la auditoría. Se elige el error visible sobre el error silencioso.

### 3.9 Índices

`ix_expenses_property_year (property_id, tax_year)` · `ix_expenses_account_year (account_id, tax_year)` · `ix_expenses_ticket (ticket_id)` · `ix_expense_receipts_expense (expense_id)` · `ix_fx_lookup (currency_from, currency_to, rate_date)`

El resumen anual por propiedad es la consulta caliente y sin el índice compuesto hace recorrido completo. Precedente negativo a no repetir: `leases` no tiene índice en `property_id` ni `tenant_id` (models.py:349-356) y `scoped_leases` (scoping.py:111) hace join por ahí en cada vista.

---

## 4. Aislamiento

Todo pasa por `platform/app/scoping.py`. Se añade allí, y **solo allí**:

```python
def scoped_expenses(db, user) -> Query:
    """Gastos visibles: los de las propiedades de este usuario."""
    q = db.query(Expense)
    if is_admin(user):
        return q
    if _role_of(user) == RoleEnum.owner.value:
        return q.join(Property, Property.id == Expense.property_id).filter(
            Property.owner_id == user.id)
    return q.filter(False)   # el inquilino NO ve gastos, nunca

def get_scoped_expense_or_404(db, user, expense_id) -> Expense: ...
```

Calcado de `scoped_tickets` (scoping.py:133-148). Reglas que no se negocian:

- **Lo ajeno devuelve 404, nunca 403.** Un 403 confirmaría que el objeto existe.
- El `property_id` que llega por formulario pasa por `assert_can_assign_property` (scoping.py:91-105). Sin eso, un propietario cuelga gastos en la casa de otro editando un campo.
- Si viene `ticket_id`, se valida con `scoped_tickets` **y además** se comprueba `ticket.property_id == property_id`. Un gasto no puede colgar de un ticket de otra casa.
- Los filtros de la URL (`?propiedad=`) se aplican **dentro** del conjunto ya acotado: comodidad, no control de acceso. Mismo criterio que owner_portal.py:123-127.
- **El inquilino no accede a ninguna ruta de este módulo.** Un comprobante fiscal lleva el RFC y el domicilio del propietario.

---

## 5. Moneda y tipo de cambio

El CEO opera en MXN; el IRS exige USD. Reglas:

1. `amount` + `currency` es **lo capturado** y no se sobrescribe jamás.
2. `amount_base` es **derivado y congelado en la fila** junto con `fx_rate`, `fx_rate_date` y `fx_source`. Un total que cambia de cifra entre marzo y abril no sirve como evidencia.
3. Si `currency == base_currency`: `fx_rate = 1`, `amount_base = amount`.
4. Si difieren y **no hay tasa disponible**, `amount_base` queda **NULL**. La pantalla lo cuenta como hueco *antes* de los totales y el manifiesto del paquete trae `missing_fx_count > 0`. **Un paquete visiblemente incompleto es infinitamente mejor que uno silenciosamente falso.** En ninguna salida aparece un importe convertido sin origen.
5. Cargar una tasa **recalcula** los gastos no anulados de años **abiertos** que la usen, y **nunca** toca un año cerrado.
6. **No hay consulta automática de tasas.** La objeción no es la dependencia (`httpx` ya está): es que una llamada saliente añade un punto de fallo y produce una cifra cuyo origen no podríamos justificar ante un auditor. El propietario elige la tasa y declara su fuente, y esa fuente se imprime en cada línea del CSV.

---

## 6. Comprobantes — pipeline de PDF y XML

**Módulo nuevo `platform/app/uploads_docs.py`. No se toca `uploads.py`**: su contrato (re-codificar siempre) es correcto para imágenes y debe seguir siéndolo.

### 6.1 Aceptación

| kind | Detección | Tratamiento |
|---|---|---|
| `imagen` | Pillow, como hoy | Se delega en `uploads.save_ticket_photo`… **no**: se usa el mismo algoritmo (`Image.open` → `verify` → `convert("RGB")` → `thumbnail(1568)` → JPEG q82) extraído a un helper compartido. `recoded=1`, EXIF y GPS destruidos. |
| `pdf` | Los primeros 5 bytes son `%PDF-` **y** el archivo contiene `%%EOF` | **Se guarda tal cual.** No se puede re-codificar sin añadir un parser, que sería a su vez superficie de ataque. |
| `xml` | Primer carácter no-blanco es `<`, la raíz es `Comprobante` de `cfd/3` o `cfd/4` por inspección **textual**, y **no** contiene `<!DOCTYPE`, `<!ENTITY` ni `<?xml-stylesheet` | **Se guarda como bytes opacos. Nadie lo parsea nunca.** |

### 6.2 Por qué NO se parsea el XML del CFDI

Extraer UUID, RFC e importe del XML para autorrellenar es cómodo y **se descarta en v1**. Un filtro textual de `<!DOCTYPE`/`<!ENTITY` es una **lista negra**, y `xml.etree.ElementTree` de la biblioteca estándar no es un parser endurecido. El premio es no teclear un UUID; el precio es meter la clase de vulnerabilidad más grave que podría entrar por este módulo (XXE, bomba de entidades) en una aplicación que hoy no tiene ni un parser XML. El propietario teclea el UUID en `tax_doc_ref`. Si el CEO quiere la lectura automática, es una fase posterior **detrás de `defusedxml`** y con su propia revisión (§14, decisión abierta).

### 6.3 Topes y memoria

`CSRFMiddleware` lee el cuerpo multipart **completo en memoria y lo parsea dos veces** (security.py:194-207) **antes** de que la ruta pueda rechazar nada. Por eso:

- **Un archivo por petición.** Sin atributo `multiple`.
- **2 MB por archivo** para PDF y XML (`FISCAL_RECEIPT_MAX_BYTES`); 8 MB para imagen, reutilizando el tope existente.
- Máximo **5 comprobantes por gasto**.
- **Guarda por `Content-Length` en el propio middleware, antes del `await request.body()`**, devolviendo 413. Son tres líneas en `security.py:180-195`. **Es un cambio transversal, fuera de esta área**, y lo declaro aquí porque este módulo es quien abre el segundo camino de subida del sistema. Sin él, dos subidas grandes simultáneas tumban el proceso en free-tier.

### 6.4 Almacenamiento

Ruta: `UPLOAD_DIR/comprobantes/{mock|live}/{property_id}/{uuid4hex}.{ext}`

**El modo de datos va EN la ruta** porque `UPLOAD_DIR` es un único directorio para mock y live (uploads.py:30) mientras la base sí se separa por modo (db.py:33-37), y los ids colisionan entre las dos bases. Sin esto, un comprobante de prueba y uno real acaban en la misma carpeta. Los directorios se crean con `os.makedirs(exist_ok=True)` **en el momento de la primera subida, no al arrancar**: el arranque ya se cayó una vez por un `os.makedirs` sobre una ruta no escribible en contenedor (main.py:96-115).

### 6.5 Descarga

**Una sola regla, sin excepciones, para los tres tipos:**

```
Content-Disposition: attachment; filename="<saneado>"
Content-Type: application/octet-stream
X-Content-Type-Options: nosniff
```

Nunca `inline`, ni siquiera para imágenes. La ruta de fotos de tickets sí sirve `inline` (tenant.py:296-297), y es correcto ahí porque son JPEG re-codificados; aquí una sola regla significa una sola prueba y ninguna «mejora» que abra un agujero. Un XML servido inline con `xml-stylesheet` ejecuta XSLT en el navegador; un PDF inline ejecuta su propio JavaScript **en nuestro origen**. Se pierde la miniatura del comprobante; se gana que la ruta no pueda degradarse.

`stored_path` se resuelve siempre con la contención de rutas de `uploads.resolve_stored_path` (uploads.py:51-62). El `filename` del `Content-Disposition` se sanea: sin comillas, sin barras, sin saltos de línea.

---

## 7. Año fiscal, cierre y ajustes

- El año fiscal es **natural** (enero–diciembre) para MX y US en esta fase. `tax_year` se deriva de `expense_date` al escribir.
- **Cerrar** un año (por propiedad o por cuenta) hace que crear, editar o anular gastos de ese año devuelva **409** con el motivo. Escribe `fiscal_year_closures` y `audit_log`.
- **Reabrir** exige motivo escrito (**400** sin él) y deja `reopen_reason` + `audit_log`. La reversibilidad con huella es preferible a la irreversibilidad, que empuja a la gente a falsear datos.
- Sobre un año cerrado sí se puede registrar un **asiento de ajuste** (`adjusts_expense_id`), que aparece como línea propia. Es lo que hace un contador cuando encuentra algo después de entregar.
- **Honestidad obligatoria:** el cierre es un control **de la aplicación**, no inmutabilidad criptográfica. Quien tenga el archivo SQLite puede alterar cualquier fila. El `LEEME.txt` del paquete lo dice literalmente, y el `sha256` del paquete sí permite al contador demostrar que **lo que él recibió** no cambió. Prometer inmutabilidad que no existe sería peor que no prometer nada.

---

## 8. Exportación — la «Auditors View» de D-015

D-015 fija que «Auditors View» = **exportación por año fiscal y propiedad que el propietario descarga y entrega a su contador**. **No se crea rol auditor. No se toca `scoping.py` para terceros.**

### 8.1 Contenido del paquete

`aura-fiscal-{propiedad|cuenta}-{anio}-{aaaammdd}.zip`

```
LEEME.txt                    aviso legal, qué contiene, qué NO es, y el aviso de que
                             el cierre no es inmutabilidad criptográfica
MANIFIESTO.json              anio, propiedad, jurisdicción, moneda base, catalog_version,
                             conteos, missing_fx_count, excluded_other_mode_count,
                             fotos_incluidas (true/false), data_mode, generado_en
gastos.csv                   una línea por gasto, con tipo de cambio y fuente en cada línea
resumen_por_categoria.csv    categoría · etiqueta ES · línea Schedule E · concepto SAT ·
                             total corriente · total capitalizable
tickets.csv                  ticket público, propiedad, fecha, resolución — inquilinos
                             SEUDONIMIZADOS como "Inquilino #<lease_id>"
comprobantes/<gasto_id>/…    los archivos originales, con su nombre uuid
fotos/<ticket_id>/…          SOLO si se marcó la casilla
SHA256SUMS.txt               hash de cada archivo del paquete
```

**Formato: CSV más los archivos originales. No PDF.** Un PDF necesitaría dependencia nueva y le daría al contador un documento que no puede procesar. *«Los datos son lo que importa.»*

### 8.2 Reglas del paquete

1. **Fotos del interior de viviendas: excluidas por defecto.** La casilla existe, nace **desmarcada**, vive en una **pantalla intermedia de confirmación** con su advertencia (*«muestran el interior de la vivienda de tus inquilinos»*), y marcarla queda en `fiscal_exports.includes_ticket_photos` y en `audit_log`.
2. **Seudonimización obligatoria.** Nombre, correo y teléfono de inquilinos **no salen nunca**. El contador necesita saber que se gastaron 4.200 pesos en plomería, no quién vive ahí.
3. **Sello de modo.** Se excluye toda fila cuyo `data_mode` no coincida con el modo actual, y el manifiesto lo declara en `excluded_other_mode_count`. En mock, el nombre del ZIP y el `LEEME.txt` llevan `DATOS-DE-PRUEBA`.
4. **Anti-inyección de fórmulas en CSV.** Toda celda de texto que empiece por `=`, `+`, `-` o `@` se escribe con prefijo de comilla simple. El contador abre el archivo en Excel. *(Hallazgo heredado fuera de esta área: `/owner/tickets/reporte` — owner_portal.py:176-190 — no lo hace hoy; vale la pena arreglarlo de paso.)*
5. **Memoria y disco.** El ZIP se escribe a `platform/data/exports/` y se sirve con `FileResponse` en streaming; **nunca se arma en memoria**. Si supera el umbral configurable, se rechaza y se pide exportar por propiedad. El volumen de producción es de 1 GB compartido con la base y las fotos (BACKUP.md).
6. **Auditoría obligatoria** en cada generación: `audit(db, request, "fiscal.exportar", object_type="property", object_id=..., meta="anio=… docs=… fotos=si/no")`.

---

## 9. Puertas (tres, independientes, todas en servidor)

### 9.1 Puerta legal — `DATA_MODE` (D-016)

La que **ya existe**. En `DATA_MODE=mock` se construye y se prueba todo; en `live` la app ya se niega a arrancar sin `LEGAL_CLEARANCE_REF` (mockmode.py:61-81). **No se añade ningún criterio legal nuevo.**

| Módulo | Estado | Bandera |
|---|---|---|
| Gastos (captura, edición, anulación) | Construido, probado en mock | `DATA_MODE` + `FISCAL_MODULE_ENABLED` |
| Comprobantes (PDF/XML/imagen) | Construido, probado en mock | `DATA_MODE` + `FISCAL_MODULE_ENABLED` |
| Resumen fiscal y paquete de exportación | Construido, probado en mock | `DATA_MODE` + `FISCAL_MODULE_ENABLED` |
| Recurrencias y borrador desde ticket | **Modelo sí, rutas en Fase B-2** | + entitlement de plan |

Un CFDI real contiene RFC, nombre y domicilio de emisor y receptor: dato personal de terceros. Por eso el módulo entero vive detrás de esta puerta.

### 9.2 Sello por fila — refuerzo propio

`expenses.data_mode` se sella al nacer con el modo actual. La exportación excluye lo que no coincida. Así, una fila de pruebas no puede colarse en un paquete fiscal real **ni aunque alguien cruce las bases o copie filas**. Es la contrapartida en datos de lo que §6.4 hace en disco.

### 9.3 Bandera de módulo

`FISCAL_MODULE_ENABLED`, variable de entorno, default `true`, mismo patrón que `tenant_module_enabled` (mockmode.py:48-49) y `owner_property_manage_enabled` (mockmode.py:52-58). **Comprobada en el servidor en las 16 rutas, no solo al pintar el menú**: ocultar un botón no impide construir la petición a mano. Apagada devuelve **404** (no 501: un 501 anuncia que el módulo existe).

### 9.4 Entitlement por plan

**Recomendación de esta área** (el CEO decide, ver §14 decisión 1):

| Función | Disponible en |
|---|---|
| Captura, edición y anulación de gastos | **Todos**, trial de 90 días incluido |
| Comprobantes (subir, descargar, quitar) | **Todos** |
| Filtros, lista, totales y CSV plano | **Todos** |
| Gasto desde un ticket (punto 2.4) | **Todos** |
| Resumen anual con mapeo IRS/SAT | **Todos** |
| **Paquete de exportación (D-015)** | **Todos** |
| Cierre y reapertura de año | **Todos** |
| Borrador de gasto autogenerado al resolver un ticket | **Standard+ / Enterprise+** |
| Gastos recurrentes (Fase B-2) | **Standard+ / Enterprise+** |
| Desglose comparativo multi-año y multi-propiedad | **Standard+ / Enterprise+** |
| Alertas de comprobantes faltantes | **Standard+ / Enterprise+** |

**Lectura del punto 7.3:** *«automatizar y desglosar todos los gastos por año y por propiedad»* se parte en dos. **«Automatizar» es la mitad que se cobra** — que la máquina cree el gasto en lugar del propietario. **«Desglosar» no se puede cobrar**: es el propio dato del cliente, y retenerlo detrás de un muro de pago es comercialmente frágil (el dato entra incompleto once meses y en marzo el cliente descubre que no puede sacar nada, y nos culpa de su auditoría) y discutible en portabilidad bajo LFPDPPP. Además, **el paquete de marzo es la demostración que convierte** el trial de 90 días de una casa.

**Regla dura asociada:** bajar de plan **nunca** oculta ni borra datos fiscales ya capturados. Deja de generar automáticos; lo capturado se sigue viendo y exportando.

**Implementación:** un único helper `plan_permite_automatizacion(db, user)` que lee `accounts.plan` (Área A). Mientras `accounts` no exista, devuelve `True` (**fail-open**) y la pantalla muestra un aviso de que el control de planes está pendiente. Fail-closed dejaría al CEO sin sus propios reportes durante la construcción, y el módulo vive en mock: no se regala nada a nadie real. Una prueba verifica que es el **único** punto de llamada.

Las funciones de pago devuelven **403** con pantalla explicativa, no 404: la regla del 404 protege la existencia de objetos **de otros**, no la de funciones de pago sobre los datos propios.

---

## 10. Migración

**PASO 0 — SNAPSHOT, obligatorio, antes de nada.** `platform.db` tiene los propietarios reales del CEO (3 usuarios, 3 propiedades) y está sin migrar desde E1: le faltan **8 tablas**. `python -m app.backup` **no sirve tal cual en local**: `backup.py:36` toma `BACKUP_DATA_DIR` con default `/data`, el volumen de Fly, que está suspendido. Usar:

```bash
BACKUP_DATA_DIR="$PWD/platform/data" python -m app.backup
# o, equivalente y sin depender de nada:
python -c "import sqlite3,datetime as d; s=sqlite3.connect('file:platform/data/platform.db?mode=ro',uri=True); t=sqlite3.connect('platform/data/platform.db.%s.bak'%d.date.today().isoformat()); s.backup(t); print(t.execute('PRAGMA integrity_check').fetchone()); t.close(); s.close()"
```

**PASO 1 — Migrar primero lo pendiente, sin código nuevo.** Arrancar la app UNA vez con `DATABASE_URL` apuntando a una **copia** de `platform.db`, para que corran `create_all()` + las tres `_ensure_*` existentes (main.py:221-230). Verificar con `test_migrate.py` que `users` y `properties` salen idénticos. Solo entonces repetir sobre la real. **El módulo fiscal no debe ser el evento que descubra ese retraso**: un fallo mezclaría dos migraciones en un mismo incidente.

**PASO 2 —** Definir los 6 modelos nuevos en `models.py`. `Base.metadata.create_all()` (main.py:225) los crea con sus índices en ambas bases; no altera nada existente.

**PASO 3 —** `_ensure_property_tax_column()` en `main.py`, calcada de `_ensure_property_site_ref` (main.py:132-148): `PRAGMA table_info(properties)`; si el resultado **no está vacío** y falta la columna, `ALTER TABLE properties ADD COLUMN tax_jurisdiction VARCHAR`. Nullable, sin default, **sin UPDATE masivo**: NULL se resuelve en lectura. Si el PRAGMA viene vacío, `return` — la tabla no existe y `create_all` se encarga (misma guarda que main.py:176-177).

**PASO 4 —** `_ensure_account_fiscal_columns()`, misma mecánica sobre `accounts` (D-013): `default_tax_jurisdiction`, `base_currency`. **Empieza con `if not cols: return`**, así el orden de construcción entre el Área A y este módulo no bloquea a nadie.

**PASO 5 —** `_ensure_fiscal_indexes()`: `CREATE INDEX IF NOT EXISTS` para los cinco índices. Idempotente sin PRAGMA previo. Necesario aparte porque `create_all()` **no** añade índices a tablas que ya existen.

**PASO 6 —** Backfill idempotente de `expenses.account_id`, solo si `accounts` existe. Como `expenses` nace vacía es un no-op en la práctica; por eso `account_id` puede ser nullable sin riesgo.

**PASO 7 —** Registrar las tres funciones nuevas en `on_startup` (main.py:216-230), **después** de `create_all()` y junto a las tres existentes.

**PASO 8 —** Crear `platform/data/exports/` y confirmar que `platform/data/uploads/` y `platform/data/exports/` están en `.gitignore`. Un comprobante fiscal o un ZIP con datos de inquilinos commiteado por accidente no se «desborra» de git.

**PASO 9 —** Actualizar `docs/phase2/DB_SCHEMA.md`, `docs/ARCHITECTURE_STATE.md` (congelado en 2026-08-02 y ya dice cosas falsas, como que 2b/2c son stubs 501) y añadir `docs/phase2/FISCAL.md` con este documento.

**PROHIBIDO en este módulo y en los siguientes:** `DROP COLUMN`, cambiar el tipo de una columna existente, renombrar un `code` del catálogo, renombrar un valor de Enum existente, y ejecutar cualquier migración contra `platform.db` sin snapshot previo.

**Marcha atrás:** apagar `FISCAL_MODULE_ENABLED`. Las tablas y columnas quedan inertes; SQLite no las suelta y no se intenta deshacer el esquema.

---

## 11. Rutas

Router nuevo `platform/app/routers/fiscal.py`, con `_require_owner` (owner o admin), `_ctx` y `_nav_badges` importados del patrón de `owner_portal.py:72-99`.

**Trampa de orden que hay que respetar:** con el path param tipado `gasto_id: int`, `/owner/gastos/nuevo` cae en el parametrizado y devuelve **422** si se declara después. Las rutas estáticas van **primero**, igual que `/owner/tickets/reporte` (owner_portal.py:140) va antes de `/owner/tickets/{ticket_id}` (owner_portal.py:196).

```
GET   /owner/gastos                                     lista con filtros y totales
GET   /owner/gastos/nuevo                               formulario de alta (?propiedad= ?ticket=)
POST  /owner/gastos                                     alta (multipart, 1 comprobante opcional)
GET   /owner/gastos/{gasto_id}                          detalle, comprobantes e historial
POST  /owner/gastos/{gasto_id}/actualizar               despacho por 'accion'
GET   /owner/gastos/{gasto_id}/comprobante/{id}         descarga (siempre attachment)
POST  /owner/tickets/{ticket_id}/gasto                  gasto desde el ticket (punto 2.4)
GET   /owner/fiscal                                     panel del año fiscal
GET   /owner/fiscal/reporte                             CSV plano (?anio= &formato=csv)
GET   /owner/fiscal/exportar                            pantalla de confirmación del paquete
POST  /owner/fiscal/exportar                            genera el paquete
GET   /owner/fiscal/exportaciones                       historial de paquetes generados
GET   /owner/fiscal/exportaciones/{id}/descargar        descarga un paquete ya generado
POST  /owner/fiscal/cierre                              despacho por 'accion' (cerrar|reabrir)
GET   /owner/fiscal/tipos-de-cambio                     ver tasas cargadas
POST  /owner/fiscal/tipos-de-cambio                     alta de una tasa
```

`POST /owner/gastos/{gasto_id}/actualizar` es **un solo endpoint despachado por el campo `accion`** ∈ `{editar, anular, ajustar, adjuntar, quitar_comprobante}`, copia deliberada del patrón ya probado de `POST /owner/tickets/{id}/actualizar` (owner_portal.py:219-280), para no inventar una convención nueva y para que toda la subida multipart viva en un solo sitio.

---

## 12. Pantallas

Convención innegociable, verificada en el código: **CSP estricta** (`script-src 'self'; style-src 'self'`, security.py:240-246). **Cero JS y cero CSS en línea.** `test_ui.py:88-93` falla si aparece `onclick=`, `onsubmit=` o `style="` en el HTML. `{{ csrf_input(request) }}` en **todo** formulario POST. Confirmaciones destructivas con `data-confirm`, que conecta `platform.js:17-24` — un `onsubmit=` no se ejecutaría y la acción ocurriría **sin preguntar**, que es el fallo exacto que documenta security.py:225-232.

| Pantalla | Plantilla | Contenido |
|---|---|---|
| Gastos (lista) | `owner_expenses.html` | Filtros como `<form method="get">` (año, propiedad, categoría, con/sin comprobante, anulados) sin autofiltrado. Tabla: fecha · propiedad · categoría · proveedor · importe original · importe base · comprobante · ticket. Fila anulada **tachada y visible, nunca oculta**. Totales en `<tfoot>`. Aviso destacado *«N gastos de 2026 sin comprobante»* — ese contador es lo que evita el pánico de marzo. Botones «Nuevo gasto» y «Descargar CSV». |
| Alta / edición | `owner_expense_form.html` | `.form-grid`: propiedad (select acotado a `owned_properties`), fecha, importe, moneda, categoría (con la línea IRS y el concepto SAT como texto de ayuda), proveedor (`<input>` con `<datalist>`, texto libre admitido), referencia fiscal, casilla «es una mejora, no una reparación», nota, y **un** `<input type="file">` sin `multiple`, con `accept=".pdf,.xml,image/jpeg,image/png,image/webp"`. Bloque de tipo de cambio **siempre visible**, prerrellenado a 1 cuando coincide la moneda. Aviso bajo el importe: *«Aura no decide si un gasto es deducible; eso lo determina tu contador.»* Con `?ticket=N`, precarga categoría, fecha (`resolved_at`) y proveedor **por parámetros, sin crear ninguna fila borrador**. |
| Detalle | `owner_expense_detail.html` | Importe y conversión congelada (*«MXN 4.200,00 · USD 231,00 al tipo 18,1818 del 2026-03-12, fuente: manual»*) o *«sin tipo de cambio cargado»* con enlace. Comprobantes con tamaño, `sha256` abreviado y botón Descargar. Ticket vinculado. **Historial leído de `audit_log`** — la primera pantalla del sistema que lee esa tabla, que hoy se escribe (security.py:486-507) y no lee nadie. Si el año está cerrado: banda de aviso, campos en solo lectura y botón «Registrar ajuste». |
| Año fiscal | `owner_fiscal.html` | Selector de año. **Bloque de avisos ANTES de los números**: gastos sin comprobante, gastos sin tipo de cambio, propiedades sin jurisdicción, filas de prueba excluidas. *Un total que parece completo y no lo está es peor que un total ausente.* Tarjetas por propiedad. Matriz categoría × total con tres columnas de etiquetado (etiqueta ES · línea Schedule E · concepto SAT) y filas separadas para corriente e inversión. Estado del cierre y formulario cerrar/reabrir con `data-confirm`. Descargo al pie. |
| Exportación (confirmación) | `owner_fiscal_export.html` | Pantalla intermedia **obligatoria**: qué llevará el paquete, que los inquilinos van seudonimizados, y la casilla **desmarcada** «incluir fotografías de los reportes de mantenimiento — muestran el interior de la vivienda de tus inquilinos». Si se marca, el botón cambia de texto y `data-confirm` pide confirmación. |
| Historial de paquetes | `owner_fiscal_exports.html` | Qué se generó, cuándo, cuántos gastos y comprobantes, hash, y columna visible **«con fotos: sí/no»**. |
| Tipos de cambio | `owner_fx_rates.html` | Tabla de tasas con fuente obligatoria y tipo (diaria / promedio anual) + formulario de alta. Texto fijo: *«Aura no consulta tasas automáticamente; la tasa y su fuente las eliges tú.»* |
| Detalle del ticket *(modificada)* | `owner_ticket_detail.html` | Bloque nuevo de solo lectura «Gastos de este reporte» con lista, total y enlace «Registrar gasto de este reporte» → `/owner/gastos/nuevo?ticket=<id>`. **No toca el formulario de acción del ticket**, que hoy no es multipart. |
| Menú lateral *(modificada)* | `base.html` | Grupo nuevo «Fiscal» en la rama `role == 'owner'` (base.html:50-70) con «Gastos» (`active='gastos'`) y «Año fiscal» (`active='fiscal'`). **Sin contador de insignia**: un número de gastos no exige acción diaria y competiría con el de reportes abiertos, que sí. |

**Obligatorio en toda vista nueva:** inyectar `**_nav_badges(db, user)` en el contexto (owner_portal.py:87-99). Los contadores del menú los calcula **cada router**, no un middleware; sin eso desaparecen al entrar a Gastos.

**Móvil.** Los breakpoints son 640px (colapsa `.form-grid`) y 860px (sidebar → cajón con `☰`). **Hoy no existe ninguna tabla responsiva.** Una tabla de ocho columnas en un teléfono es ilegible, así que bajo 640px la lista de gastos se pinta como **tarjetas**, y toda tabla ancha va envuelta en un contenedor con `overflow-x: auto`.

**CSS.** Toda clase nueva se añade a `platform.css` **en el mismo cambio**: `.table-scroll`, `.totals-row`, `.money` (alineación derecha, `tabular-nums`), `.expense-card`, `.void`. No se agranda la deuda existente de plantillas que usan clases inexistentes (`.flash-ok`, `.btn-danger`, `.filters`, `.meta`).

**Cadenas (D-014).** Español ahora, **cadenas extraídas fuera de la plantilla**: las etiquetas de categoría, los conceptos SAT, las líneas de Schedule E y los tres avisos legales viven como datos en `fiscal_catalog.py` y llegan por el contexto. **No se construye i18n ni se traduce nada.**

---

## 13. Lo que este módulo NO toca

- **`documents`** — se deja muerta, explícitamente (§3.2).
- **`uploads.py`** — su contrato de re-codificación es correcto y tiene pruebas alrededor.
- **`scoping.py`** — solo se **añaden** dos funciones; no se modifica ninguna existente. **No se abre a terceros** (D-015).
- **`Permissions-Policy: camera=()`** — este módulo no la necesita y no la relaja.
- **El agente IA** (`ai_agent.py`) — sigue desconectado; este módulo no lo llama.
- **2c / pagos** — el catch-all 501 (payments.py:154-159) sigue intacto.
- **El sitio público** — cero cambios.

---

## 14. Contradicciones del feedback, resueltas

**Punto 6.1 — «el owner puede agregar tickets o documentos» tras resolver.** Se trata como **lapsus por «fotos o comprobantes»**: añadir *tickets* a un ticket resuelto no significa nada, y si el CEO quería un ticket de seguimiento, eso ya existe creando un ticket normal. Este módulo entrega **la mitad de comprobantes**: el propietario adjunta comprobantes a un gasto y cuelga ese gasto de un ticket resuelto. **La mitad de fotos es del área de tickets** y está bloqueada hoy por dos hechos: el formulario del propietario no es multipart (owner_portal.py:219-221 recibe `Form(...)`, no `UploadFile`) y `Permissions-Policy: camera=()` (security.py:246) bloquea `capture=`. Queda como confirmación al CEO, no como funcionalidad inventada.

**Punto 5 frente a punto 7 — proveedores.** Esta área confirma la lectura razonable **desde el lado del dato**: `expenses.vendor_id` sin proveedores capturables queda vacío para siempre, y un gasto sin proveedor es justo el que un auditor cuestiona. El CRUD manual de tres campos no es lo que justifica un plan de veinte casas; **la cotización automática sí**. Refutarlo tendría un coste concreto y no recuperable: los clientes Standard exportarían paquetes sin proveedor durante años.

**D-010 frente al feedback nuevo — trial y precio.** Este módulo solo necesita saber **qué planes son «+»**. Con 60 días o con 90, con una casa o con varias, el diseño fiscal no cambia: una casa genera pocos gastos y el paquete de marzo es la mejor demostración de venta que tiene el producto. El precio y el destino de la regla de fundadores siguen abiertos y **no los resuelve este diseño**.

---

## 15. Riesgos aceptados

1. **El paquete es el objeto con más riesgo de fuga del sistema.** Sale de la plataforma y llega a un tercero (el contador) que nunca aceptó nuestro aviso de privacidad. Mitigado con `DATA_MODE`, seudonimización, fotos apagadas por defecto, `LEEME.txt`, `fiscal_exports` y `audit_log`. **Lo que no se puede mitigar es qué hace el propietario con el ZIP una vez descargado**: eso es contrato y aviso de privacidad, no código.
2. **El PDF se guarda sin re-codificar.** Un JPEG se reescribe y muere cualquier políglota; un PDF no puede reescribirse sin añadir un parser que sería a su vez superficie de ataque. Se compensa con bytes mágicos, nombre uuid, fuera del árbol web, `attachment` + `octet-stream` + `nosniff`, y `frame-ancestors 'none'` que ya está. **Riesgo residual real:** el archivo puede ser malicioso para el equipo del contador que lo abra. El `LEEME.txt` lo dice.
3. **`PRAGMA foreign_keys = 0`.** Borrar una propiedad por SQL deja gastos y comprobantes huérfanos que el scoping vuelve **invisibles**, que es peor que verlos. Mitigación: `vendor_name_raw` y `category_code` denormalizados, cero borrado duro en este módulo, y una guarda que impide borrar una propiedad con gastos en un año cerrado. *(Esa guarda se llama desde la ruta de borrado de propiedad, que es de otra área.)*
4. **El cierre no es inmutabilidad.** Quien tenga el archivo SQLite altera cualquier fila. Se declara en pantalla y en el paquete.
5. **Un tipo de cambio mal tecleado envenena la exportación en silencio.** Mitigación parcial: el CSV imprime tasa y fuente en cada línea, y la pantalla avisa si la conversión difiere más de un 15% de la última tasa del mismo año. No hay validación posible sin fuente externa, que se descarta por diseño.
6. **El mapeo a dos jurisdicciones es orientativo y no es exacto en los bordes** (deducción opcional del 35% en arrendamiento en México, depreciación a 27,5 años del IRS frente al 5% anual de construcción del SAT). El módulo **no** lo resuelve y no debe intentarlo. Si alguien lee la columna «línea Schedule E» como una determinación fiscal, el riesgo pasa de técnico a de responsabilidad — por eso el descargo va en pantalla y en la portada del ZIP, no en un documento aparte.
7. **Dependencia del Área A.** Mientras `accounts` no exista, `account_id` queda nulo, el aislamiento sigue dependiendo de `property.owner_id` (que es correcto hoy) y la puerta de plan es fail-open. **Lo que no se debe hacer es lanzar este módulo en live antes que `accounts`.**
8. **`platform.db` está 8 tablas atrás y contiene datos reales.** Si el primer arranque que la toca es el del módulo fiscal, un fallo mezcla dos migraciones en un incidente. De ahí el paso 0 y el paso 1.

---

## 16. Handoff

- [ ] `platform/app/fiscal_catalog.py` — 15 categorías, doble mapeo, `CATALOG_VERSION`, `RETIRADOS`, tres avisos legales
- [ ] `platform/app/models.py` — 6 tablas nuevas + `properties.tax_jurisdiction` + 2 columnas de `accounts`
- [ ] `platform/app/main.py` — `_ensure_property_tax_column`, `_ensure_account_fiscal_columns`, `_ensure_fiscal_indexes`, backfill, registradas en `on_startup`
- [ ] `platform/app/scoping.py` — `scoped_expenses` + `get_scoped_expense_or_404`
- [ ] `platform/app/uploads_docs.py` — pipeline PDF/XML/imagen, topes, saneado, contención de rutas
- [ ] `platform/app/security.py` — guarda por `Content-Length` antes del `await request.body()` **(cross-área, requiere revisión de Infra)**
- [ ] `platform/app/routers/fiscal.py` — 16 rutas
- [ ] `platform/app/fiscal_export.py` — armado del ZIP, manifiesto, `SHA256SUMS`, seudonimización, anti-inyección CSV
- [ ] 7 plantillas nuevas + 2 modificadas + clases nuevas en `platform.css`
- [ ] `platform/tests/test_fiscal.py` — ~28 comprobaciones, con la línea `RESULTADO:`
- [ ] `platform/tests/test_ui.py` — añadir las URL nuevas a la comprobación de CSP
- [ ] `docs/phase2/FISCAL.md`, `docs/phase2/DB_SCHEMA.md`, `docs/ARCHITECTURE_STATE.md`, y espejo en Drive `Aura/Reports/Desarrollo/`

**Estado: 0 de 12 hechos. Línea base de pruebas a conservar: 261 pasaron, 0 fallaron, 10 suites.**
