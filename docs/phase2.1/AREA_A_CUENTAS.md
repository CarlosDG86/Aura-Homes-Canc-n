<!-- Generado por el panel de diseño del 2026-09-08. Ganadora: Custodia por cuenta, plan sin dinero (ángulo riesgo) -->

> **Fase 2 · Área A — Cuentas, planes, prueba gratuita y entitlements**
> **Fecha:** 2026-09-08 · **Estado:** diseño cerrado, listo para construir · **Premisas:** D-010, D-013, D-014, D-015, D-016
> **Base:** FastAPI + SQLAlchemy 2.0.35 + SQLite en un archivo + Jinja2 server-rendered. Sin Alembic, sin pytest, sin JS de framework.

---

## 0. Resumen en cinco frases

1. La **cuenta** es la raíz de aislamiento y la portadora del plan (D-013): `accounts` es tabla nueva, `users.account_id` dice *quién puede mirar* y `properties.account_id` dice *de qué cliente son los datos*.
2. `scoping.py` gana **una sola función privada** con dos ramas: si el usuario tiene cuenta se filtra por cuenta; si no la tiene se filtra por `owner_id` como hoy. Por eso las 27 comprobaciones de `platform/tests/test_scoping.py` siguen en verde **sin editar ese archivo**.
3. El plan es un **campo administrativo**: la plataforma registra QUÉ plan, jamás CUÁNTO. Cero importes, cero moneda, cero ciclo de cobro — el cobro cae bajo la puerta legal de pagos y `payments.py:157-159` sigue devolviendo 501 incondicional.
4. La prueba de **90 días arranca con la primera casa**, no con el alta de la cuenta, y el día 91 se bloquean solo los verbos de crecimiento: leer, resolver tickets y exportar datos fiscales nunca se bloquean.
5. Toda propiedad cruza de cuenta por **un único camino auditado y bloqueable**; las rutas que hoy reasignan `owner_id` a ciegas dejan de poder cruzar la frontera.

---

## 1. El problema que este diseño existe para impedir

Verificado hoy contra el fuente, hay **tres** puntos donde una propiedad cambia de dueño sin que nada sepa de cuentas:

| Punto | Archivo:línea | Qué hace hoy |
|---|---|---|
| Reasignación manual de admin | `platform/app/routers/pages.py:840-863` (escritura en `:859`, `prop.owner_id = user_id`) | Mueve N casas al usuario elegido en un formulario, sin comprobar nada más que que la casa exista |
| Sincronización del sitio público | `platform/app/routers/pages.py:641-642` (`existing.owner_id = owner.id`) | Reasigna el dueño de la casa espejada desde `data/properties.json` |
| API JSON de admin | `platform/app/routers/admin.py:33-43` (`Property(**payload.model_dump())`) | Acepta `owner_id` del cuerpo de la petición |

Si la cuenta de una propiedad se **derivase** de su dueño, esas tres rutas moverían en silencio los tickets, las fotos del interior de una vivienda y los futuros comprobantes fiscales de un cliente a otro. Por eso `properties` lleva `account_id` **explícito**: cruzar la frontera de cliente deja de ser un efecto colateral y pasa a ser una acción propia, auditada y bloqueable.

El precio de esa decisión es que existen dos columnas que pueden desincronizarse, y **SQLite no lo impide**: verificado, `PRAGMA foreign_keys` devuelve `0` tanto en `platform/data/platform.db` como en `platform/data/platform-mock.db`. La integridad no la sostiene la base; la sostienen tres cosas: **un escritor único**, **un verificador en cada arranque** y **una prueba con deriva inyectada a propósito** (§9, §11).

---

## 2. Modelo de datos

### 2.1 Tabla nueva `accounts`

| Columna | Tipo | Nulo | Default | Para qué |
|---|---|---|---|---|
| `id` | INTEGER PK | no | — | — |
| `name` | VARCHAR | no | — | Nombre de la administradora. Dato mercantil B2B, no PII de persona |
| `plan` | VARCHAR | no | `'trial'` | `trial` \| `standard` \| `standard_plus` \| `enterprise` \| `enterprise_plus`. **String, no `Enum()`** — ver §2.5 |
| `status` | VARCHAR | no | `'activa'` | `activa` \| `suspendida` \| `cerrada` |
| `trial_days` | INTEGER | no | `90` | Duración de la prueba **de esta cuenta**. Resuelve 90 vs 60 sin un plan nuevo (§4.1) |
| `trial_started_at` | DATETIME | sí | NULL | Se fija al pasar de 0 a 1 propiedad |
| `trial_ends_at` | DATETIME | sí | NULL | **Materializado** al arrancar la prueba, nunca recalculado al leer |
| `trial_property_id` | INTEGER | sí | NULL | Qué casa arrancó el reloj. Informativo y auditable |
| `properties_max_override` | INTEGER | sí | NULL | Excepción comercial por cuenta sin tocar la matriz |
| `is_operator` | BOOLEAN | no | `0` | Cuenta de Aura. **Solo estas pueden espejar propiedades del sitio público** (§7) |
| `primary_user_id` | INTEGER | sí | NULL | Interlocutor de la cuenta. FK declarada, no impuesta |
| `country` | VARCHAR | sí | `'MX'` | Jurisdicción fiscal de la administradora — la consume el área C (IRS/SAT). No es PII |
| `plan_assigned_at` | DATETIME | sí | NULL | NULL = «plan sin asignar», se marca en rojo en el directorio |
| `plan_assigned_by_user_id` | INTEGER | sí | NULL | Quién lo decidió |
| `plan_note` | VARCHAR(500) | sí | NULL | Referencia del acuerdo **firmado fuera de la plataforma**. Validada (§2.6) |
| `created_in_db` | VARCHAR | sí | NULL | `basename` del archivo de base al crear la fila. Cable trampa mock↔real (§8.3) |
| `created_by_user_id` | INTEGER | sí | NULL | — |
| `created_at` / `updated_at` | DATETIME | no | `func.now()` / `onupdate` | Convención de `models.py` |

**Prohibido en esta tabla, sin excepción:** cualquier columna de importe, moneda, ciclo de cobro, IBAN, CLABE, tarjeta, RFC, EIN o dirección fiscal. Las tres primeras familias abrirían la puerta legal de pagos; las tres últimas son PII fiscal de un tercero y pertenecen al módulo de exportación fiscal, detrás de `DATA_MODE` (D-016). Hay una prueba estructural que falla si aparecen (§11, check 24).

### 2.2 Tabla nueva `account_plan_events` (append-only)

| Columna | Tipo | Nulo |
|---|---|---|
| `id` | INTEGER PK | no |
| `account_id` | INTEGER (índice) | no |
| `from_plan` / `to_plan` | VARCHAR | sí |
| `from_trial_ends_at` / `to_trial_ends_at` | DATETIME | sí |
| `from_status` / `to_status` | VARCHAR | sí |
| `note` | TEXT | sí |
| `actor_user_id` | INTEGER | sí |
| `created_at` | DATETIME | no |

**Por qué no basta `audit_log`:** verificado, `security.audit()` escribe en esa tabla y **ninguna de las 27 plantillas la lee**. Un historial comercial que solo viva ahí es un historial que nadie puede consultar cuando en marzo haya que conciliar lo cobrado por transferencia con lo que la plataforma dice. `audit_log` se sigue escribiendo además, para la traza de seguridad; `account_plan_events` es lo que se **enseña** en la ficha de cuenta. Nunca se borra ni se actualiza.

### 2.3 Columnas nuevas

| Tabla | Columna | Tipo | Por qué |
|---|---|---|---|
| `users` | `account_id` | INTEGER NULL | Membresía: *quién puede mirar* |
| `properties` | `account_id` | INTEGER NULL | Custodia: *de qué cliente son estos datos* |

Ambas **nullable a la fuerza**: SQLite no admite añadir una columna `NOT NULL` sin default a una tabla con filas, y declararlas `nullable=False` en `models.py` produciría un esquema distinto en una instalación nueva (`create_all`) que en la migrada (`ALTER`) — la clase de divergencia que solo se manifiesta en una de las dos. Se declaran `nullable=True` en el modelo y el invariante «todo usuario y toda propiedad tienen cuenta» lo sostienen el relleno de arranque, los ayudantes de alta y el verificador de §9. **NULL falla en seguro:** cae a la rama heredada, que es estrictamente más estrecha.

### 2.4 Índices

```
CREATE INDEX IF NOT EXISTS ix_users_account_id       ON users(account_id);
CREATE INDEX IF NOT EXISTS ix_properties_account_id  ON properties(account_id);
CREATE INDEX IF NOT EXISTS ix_account_plan_events_account_id ON account_plan_events(account_id);
CREATE INDEX IF NOT EXISTS ix_leases_property_id     ON leases(property_id);
CREATE INDEX IF NOT EXISTS ix_leases_tenant_id       ON leases(tenant_id);
```

Los dos primeros pasan a ser el `WHERE` más caliente de la aplicación. Los dos de `leases` son colaterales baratos en la misma función: `leases` no tiene ningún índice hoy y a partir de ahora **toda** consulta de cuenta pasa por ese join (`scoped_leases`, `scoped_users`, el contador de inquilinos del panel).

### 2.5 `plan` y `status` como String, no como `Enum()` — divergencia deliberada

`models.py` usa `Enum(RoleEnum)` en todas partes (`models.py:82`). Aquí se diverge, y el motivo es el **modo de fallo**:

- Un `role` desconocido **debe** reventar: es un fallo de seguridad.
- Un `plan` desconocido con `Enum()` haría **ilegible la fila de la cuenta** y dejaría a un cliente sin poder entrar, por un dato meramente comercial.

Con String + lista blanca **en la escritura** y resolutor que **degrada en la lectura**: `plan` desconocido → `trial` (lo más restrictivo: 1 casa, cero extras); `status` desconocido → `suspendida` (solo lectura). `status` es la palanca con la que el CEO o Legal detienen el tratamiento de datos de una cuenta, y una palanca que falla en abierto no es una palanca. En Python los valores viven como constantes en `plans.py` (§5), no como `enum.Enum` mapeado a la columna.

### 2.6 Validación de `plan_note`

Tope de 500 caracteres y **rechazo de secuencias de 13 a 19 dígitos consecutivos** (con o sin espacios/guiones). No es paranoia: es lo único que impide que alguien pegue ahí un número de tarjeta y meta un dato de pago en una tabla que está fuera de la puerta legal de pagos. La etiqueta del campo lo dice literalmente.

---

## 3. Aislamiento — cómo se propaga a `scoping.py` sin romper las 27 comprobaciones

### 3.1 La única función nueva

```python
# platform/app/scoping.py

def _predicado_propietario(user: User):
    """Pertenencia de una propiedad al ámbito del usuario.

    Dos ramas a propósito. Si el usuario tiene cuenta, el ámbito es la cuenta
    (D-013). Si no la tiene —fila legada, alta con un fallo, admin de
    plataforma— se usa el filtro de siempre, que es ESTRICTAMENTE MÁS
    ESTRECHO: un account_id perdido puede ocultar de más, jamás mostrar de más.
    """
    account_id = getattr(user, "account_id", None)
    if account_id is None:
        return Property.owner_id == user.id
    return Property.account_id == account_id
```

### 3.2 Los seis puntos de sustitución

| Función | Línea actual | Filtro de hoy | Filtro nuevo |
|---|---|---|---|
| `scoped_properties` (rama owner) | `scoping.py:51-52` | `Property.owner_id == user.id` | `_predicado_propietario(user)` |
| `owned_properties` | `scoping.py:68` | `Property.owner_id == user.id` | `_predicado_propietario(user)` |
| `assert_can_assign_property` (rama no-admin) | `scoping.py:99-100` | vía `owned_properties` | sin cambio (hereda) |
| `scoped_leases` (rama owner) | `scoping.py:116-118` | `Property.owner_id == user.id` | `_predicado_propietario(user)` |
| `scoped_tickets` (rama owner) | `scoping.py:143-145` | `Property.owner_id == user.id` | `_predicado_propietario(user)` |
| `scoped_users` (rama owner) | `scoping.py:172-181` | `Property.owner_id == user.id` en la subconsulta de inquilinos | `_predicado_propietario(user)` **+** unir los usuarios de la propia cuenta |

**Ningún `join` cambia.** Verificado: `scoped_leases` y `scoped_tickets` ya hacen `join(Property, Property.id == …)` y filtran sobre `Property`; solo cambia el predicado. `is_admin()` sigue cortocircuitando antes en las cuatro funciones (`scoping.py:44-46, 122-124, 136-138, 162-164`).

### 3.3 Por qué las 27 comprobaciones siguen verdes sin tocarse

`platform/tests/test_scoping.py:32-34` crea los usuarios con `User(name=…, email=…, password_hash=…, role=…)` — **sin `account_id`**, así que la columna queda NULL y las 27 comprobaciones recorren íntegramente la rama heredada, idéntica byte a byte a la de hoy. Incluidas las tres que más importan: «owner A no ve la casa B», «owner A no puede asignar a la casa B» y «admin por owner router no ve casas ajenas» (`test_scoping.py:103`).

> **Criterio de aceptación, no negociable:** `python platform/tests/test_scoping.py` debe imprimir el mismo número de PASS que hoy **sin que se edite una sola línea de ese archivo**. Si hay que editarlo, la semántica de aislamiento cambió — parar y revisar, nunca ajustar la prueba.

### 3.4 Cambio de significado que hay que documentar

`owned_properties` pasa de «mis casas como persona» a «las casas de mi cuenta». Es exactamente lo que pide D-013 y hay que decirlo en el docstring, porque el propio archivo advierte contra que alguien «arregle» una de las dos semánticas sin darse cuenta (`scoping.py:59-66`). Consecuencia práctica: en la base real, tras migrar, **cada cuenta tiene un solo propietario**, así que las dos ramas seleccionan el mismo conjunto; la ampliación solo se nota cuando el admin añada de verdad un segundo usuario a una cuenta.

### 3.5 Ayudantes nuevos para las áreas B, C y D

```python
def account_properties(db, user) -> Query   # vacía si account_id es None
def account_user_ids(db, user) -> list[int] # [user.id] si account_id es None
```

Devuelven consulta **vacía**, nunca completa, cuando no hay cuenta. Regla de una línea para las tablas nuevas de gastos, proveedores y documentos: **toda tabla nueva lleva `account_id` propio si no cuelga de una propiedad, y se filtra por él, no por `owner_id`.** (Proveedores sí lo lleva: un proveedor sirve a varias casas. Gastos no: cuelgan de propiedad o de ticket.)

---

## 4. Prueba gratuita, planes y límites

### 4.1 Contradicción 90 vs 60 días — resuelta

> ✅ **Resuelto en el diseño (2026-09-08), pendiente de visto bueno formal del CEO.**
> El feedback del 2026-09-07 es **posterior y más específico** que D-010, así que la regla vigente es **90 días para UNA casa** en toda cuenta nueva. La promesa de «60 días a clientes fundadores» de D-010 **no se construye como segundo régimen**: se honra poniendo `trial_days = 60` en esa cuenta concreta. Un mecanismo, un rastro, cero caminos de código adicionales.
> Verificado: ni «60 días», ni «fundador», ni «2,500» aparecen en ningún archivo del repositorio — D-010 vive solo en Drive.

### 4.2 Cuándo arranca el reloj

**Al pasar de 0 a 1 propiedad**, no al crear la cuenta. Razones: (a) el CEO escribió «90 day free trial, just for one home» — el trial está atado a la casa; (b) el reloj no debe consumirse mientras el cliente todavía no ha cargado nada; (c) una cuenta vacía no contiene ningún dato y no tiene sentido que caduque.

Al fijarse se escriben las tres columnas de golpe, dentro de la misma transacción que crea la propiedad: `trial_started_at = now()`, `trial_ends_at = now() + trial_days`, `trial_property_id = prop.id`.

**`trial_ends_at` se materializa, no se calcula al leer.** Si mañana la constante pasa de 90 a 60, ningún cliente vivo ve moverse su fecha.

### 4.3 Matriz de planes (`platform/app/plans.py`, sin estado y sin base de datos)

| Plan | Máx. propiedades | `gastos_itemizados` | `proveedores_crud` | `export_fiscal_manual` | `agente_wa_email` | `export_fiscal_auto` | `cotizacion_auto` |
|---|---|---|---|---|---|---|---|
| `trial` | 1 | ✅ | ✅ | ✅ | — | — | — |
| `standard` | 20 | ✅ | ✅ | ✅ | — | — | — |
| `standard_plus` | 20 | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| `enterprise` | sin límite | ✅ | ✅ | ✅ | — | — | — |
| `enterprise_plus` | sin límite | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

Las claves de entitlement **jamás se renombran** (mismo motivo que con los enums: una clave vieja en una plantilla debe seguir significando lo mismo). `properties_max_override` de la cuenta, si no es NULL, gana sobre la columna de límite.

### 4.4 Contradicción punto 5 vs punto 7.2 (tabla de proveedores) — resuelta

> ✅ **Resuelto en el diseño:** el **CRUD manual de proveedores es de todos los planes**; lo exclusivo de `enterprise_plus` es la **cotización automática**.
>
> Tres argumentos, no comodidad: (1) el punto 5 pide la lista «para el owner» sin condición y «por el momento»; (2) el punto 7.4 convierte la lista en **requisito previo** del agente — un Enterprise+ que estrena la cotización automática con la agenda vacía no obtiene ningún valor el primer día, así que regalar el CRUD es precisamente lo que hace vendible el complemento; (3) el coste marginal es asimétrico: unas filas en SQLite valen cero, mientras que cotizar automáticamente llama a un modelo de pago (`ai_agent.py:93` y la tabla `AiUsage` existen justo para vigilar ese gasto) y manda correo saliente.
> **Refutación honesta:** si el CEO quiere cobrar el directorio en sí, es cambiar **una celda de la matriz** — ni esquema, ni migración, ni rutas. Por eso es función y no columna.

### 4.5 Contradicción punto 7.3 vs D-015 (exportación fiscal) — resuelta

> ✅ **Resuelto en el diseño:** se parte en **dos claves**.
> `export_fiscal_manual` (el owner elige año fiscal y propiedad y descarga el paquete — la «Auditors View» de D-015) está en **todos los planes, incluido `trial`, y sigue disponible con la cuenta suspendida o cerrada.** Si un cliente deja de pagarnos y por eso no puede entregarle a su contador lo que le pide el SAT o el IRS, el obstáculo somos nosotros — y eso es mal producto y peor argumento legal.
> `export_fiscal_auto` (el desglose anual consolidado, precalculado y enviado — literalmente el punto 7.3) es de los planes «+». Eso es lo que se cobra: la **automatización**, no el acceso a los propios datos.

### 4.6 Qué ocurre exactamente al superar el límite

Dos situaciones que **no** hay que confundir:

**(a) Intentar superarlo** (crear la casa 21 con `standard`): se rechaza **en la escritura**, en el escritor único, así que las tres puertas de creación quedan cubiertas.

| Puerta | Archivo | Respuesta |
|---|---|---|
| `POST /api/owner/properties` | `owner.py:53-66` | **409** con detalle en español |
| `POST /api/admin/properties` | `admin.py:33-43` | **409**, calculado sobre la cuenta del `owner` resuelto en `admin.py:35`, no sobre la del solicitante |
| `POST /admin/sync-site-properties` | `pages.py:597-655` | Rechazo **fila por fila**, nunca aborta a medias: «N sin sincronizar: la cuenta X está en su límite» |

Orden de aplicación en el alta: **primero** `OWNER_PROPERTY_MANAGE_ENABLED` (`owner.py:30-46`, 403 «el alta la realiza el administrador»), **después** el límite de plan (409). Invertirlo daría un mensaje que no corresponde.

**(b) Ya estar por encima** (una cuenta bajada de `enterprise` a `standard`, o la migración): **no borra, no archiva y no oculta nada.** La cuenta pasa al estado de solo-crecimiento-bloqueado y la banda dice «tienes 24 propiedades y tu plan permite 20; no puedes añadir más».

> **Regla en una línea:** los límites se aplican al **CREAR**, nunca al **LEER**. Un límite que filtrara lecturas haría invisibles propiedades sin borrarlas, que es peor que ambas cosas. La plataforma jamás elige cuál de las casas de un cliente deja de existir.

### 4.7 El día 91

| Bloqueado | No bloqueado |
|---|---|
| Crear propiedad | Entrar y leer absolutamente todo |
| Dar de alta inquilino | Comentar y **resolver** tickets abiertos |
| Crear arrendamiento | Descargar la **exportación fiscal** y los documentos |
| Crear proveedor | Cambiar contraseña, ver sesiones |
| Crear gasto | **Que un INQUILINO abra un ticket** |

La última fila no es cortesía. Una fuga de agua no sabe nada de suscripciones: cortar el canal por el que se reporta una avería en la vivienda que alguien habita convierte un impago en un problema de habitabilidad. Es la regla que más fácil se rompe en un refactor de límites y por eso tiene prueba propia (§11, check 16).

Sin periodo de gracia (sería una prueba de 105 días con más estado que mantener) y sin pérdida de datos.

### 4.8 Estados de cuenta

| `status` | Qué permite |
|---|---|
| `activa` | Todo lo que su plan incluya |
| `suspendida` | Solo lectura + exportación fiscal + descarga de documentos |
| `cerrada` | Solo exportación fiscal + descarga de documentos |

**Ningún estado borra datos ni oculta filas.** Cerrar no es borrar; el borrado es una acción aparte que esta área no define. **No existe ruta de borrado de cuentas**: con `PRAGMA foreign_keys = 0`, borrar dejaría usuarios y propiedades apuntando al vacío — invisibles pero presentes, que es peor que un error.

---

## 5. Entitlements — cómo se consultan

Módulo nuevo `platform/app/plans.py`. **Sin estado, sin base de datos, sin tabla de entitlements**: cinco planes por seis derechos son treinta celdas que habría que mantener sincronizadas con el código que las consulta; un diccionario en git se revisa en una lectura y no lo puede corromper un `UPDATE` suelto.

```python
PLANES: dict[str, dict]          # la matriz de §4.3
ETIQUETAS_PLAN: dict[str, str]   # "standard_plus" -> "Standard+"
ETIQUETAS_FUNCION: dict[str, str]
ETIQUETAS_ESTADO: dict[str, str]

def plan_de(cuenta) -> str                       # degrada lo desconocido a 'trial'
def estado_de(cuenta) -> str                     # degrada lo desconocido a 'suspendida'
def tiene(plan: str, clave: str) -> bool
def limite_propiedades(cuenta) -> int | None     # respeta properties_max_override
def estado_cuenta(db, cuenta) -> EstadoCuenta    # (puede_crecer, motivo, usadas, limite, dias_restantes)
def exigir(cuenta, clave: str) -> None           # GET -> página "no incluido"; POST -> 403
def contexto_cuenta(db, user) -> dict            # {"cuenta": {...}, "feat": {...}} — dos dicts PLANOS
```

**D-014:** todas las cadenas visibles salen de los diccionarios `ETIQUETAS_*`, en español, **fuera de la plantilla**, listas para traducir. No se construye i18n.

### 5.1 Desde una ruta

```python
from ..plans import exigir, estado_cuenta
exigir(cuenta, "cotizacion_auto")   # 403 en POST, página informativa en GET
```

Aquí **sí es 403 y no 404**, y la distinción es deliberada: el 404 de `scoping.py:14-16` protege objetos de **otro** cliente y no debe confirmar que existen; un entitlement es una característica de **tu propia** cuenta, y devolver 404 haría creer al cliente que la aplicación está rota.

### 5.2 Desde una plantilla

`contexto_cuenta(db, user)` devuelve **dos diccionarios planos**, nunca objetos del ORM, y se inyecta en:

| Punto de inyección | Archivo:línea |
|---|---|
| `_ctx()` del portal de owner | `owner_portal.py:81-85` |
| Panel `/owner` | `pages.py:692-704` |
| Panel `/admin` | `pages.py:459-512` |
| Vistas de inquilino | `tenant.py` (todas las que renderizan `base.html`) |

En la plantilla: `{% if feat.proveedores_crud %}`.

> ⚠️ **Trampa de Jinja verificada en el intérprete del proyecto.** Jinja 3.1 usa `Undefined` por defecto, y `Undefined.__getattr__` llama a `_fail_with_undefined_error()`: acceder a un atributo de una variable **no inyectada** LANZA `UndefinedError`. Es decir, poner `{% if feat.proveedores_crud %}` en `base.html` **rompería las 27 plantillas**, incluidas las de admin e inquilino, en cuanto un router olvidara inyectar el contexto.
> **Mitigación obligatoria:** registrar `feat` y `cuenta` como **globales por defecto** con valores neutros (`{}`) en `security.register_template_globals` (`security.py:154-168`); las vistas que los inyectan los sombrean. Un `{}` real devuelve `Undefined` en `.clave` **sin lanzar** (esa vía sí pasa por `Environment.getattr`, que devuelve `undefined`), y `{% if %}` lo evalúa como falso: **falla cerrado, el botón no aparece.**
> Ojo con el patrón existente: `google_enabled` se registra como **valor evaluado una vez** (`security.py:167`). El nuestro debe ser un **dict por petición** o un **global vacío**, nunca una función evaluada al registrar.

Y en todo caso la plantilla es **cosmética**: el control real es el de la ruta. El propio repo lo documenta — «ocultar un botón no impide que alguien construya la petición a mano» (`mockmode.py`, docstring de `owner_property_manage_enabled`; `owner.py:30-36`).

### 5.3 Orden de comprobación en toda ruta — es una regla de seguridad, no de estilo

```
1. Sesión y rol            (_current_user_or_none / _require_owner / _require_admin)
2. Aislamiento             (scoping.py → 404 para lo ajeno)
3. Puerta legal y bandera  (DATA_MODE, TENANT_MODULE_ENABLED, PAYMENTS_MODULE_ENABLED, AI_AGENT_ENABLED)
4. Entitlement del plan    (plans.exigir)
5. Límite de la cuenta     (409 / flash)
```

Si el entitlement se comprobara **antes** que el scoping, un 403 «tu plan no incluye esto» sobre un objeto de otra cuenta **confirmaría que ese objeto existe** — exactamente lo que la regla 404-y-no-403 de `scoping.py:14-16` existe para impedir.

**Un entitlement NUNCA levanta una puerta legal.** Un plan `enterprise_plus` no habilita datos reales en `DATA_MODE=mock`, no salta el 501 de pagos y no enciende el agente si `AI_AGENT_ENABLED` está apagado. El plan decide si una función es **alcanzable**; jamás si un dato es **legal**. Interacción cruzada con el área D, en una línea: la cotización automática exige `AI_AGENT_ENABLED` **y** el entitlement `cotizacion_auto`; ni la bandera sustituye al plan ni al revés.

---

## 6. Rutas

**Nuevas — admin**

- `GET /admin/cuentas` — Directorio: nombre, plan, estado, usuarios, propiedades usadas/límite, días de prueba restantes, marca de cuenta operadora, y aviso destacado cuando `plan_assigned_at IS NULL` («plan sin asignar — migrada»). Sin acciones destructivas en el listado.
- `POST /admin/cuentas` — Alta de una administradora vacía, para registrarla antes de crear su primer usuario. `plan='trial'`, `trial_started_at` NULL, `is_operator=0`, `created_in_db` = basename del archivo de base.
- `GET /admin/cuentas/{cuenta_id}` — Ficha: miembros, propiedades, historial de `account_plan_events`, resultado del chequeo de integridad para esa cuenta, y los tres formularios de cambio.
- `POST /admin/cuentas/{cuenta_id}/plan` — Asigna `plan`, `trial_days` y `properties_max_override` con **nota obligatoria** (referencia del contrato). Escribe `plan_assigned_at`, `plan_assigned_by_user_id`, `plan_note`, una fila en `account_plan_events` y `security.audit()`. **Único escritor de `accounts.plan`.**
- `POST /admin/cuentas/{cuenta_id}/prueba` — Extiende `trial_ends_at` con nota obligatoria. **Solo hacia adelante** en el tiempo (acortar una prueba por formulario es cortarle el acceso a un cliente sin que se vea que es eso lo que se hizo; para eso está `/estado`). Tope duro de +180 días sobre `trial_started_at`. Este es el mecanismo de «clientes fundadores»: no se construye una segunda bandera.
- `POST /admin/cuentas/{cuenta_id}/estado` — `activa` \| `suspendida` \| `cerrada`, con nota obligatoria.
- `POST /admin/cuentas/{cuenta_id}/miembros` — Mueve un usuario a esta cuenta. **Tres negativas duras:** (1) rechaza mover un `admin` a una cuenta que no sea operadora — el personal de Aura no adquiere en silencio la vista de propietario de un cliente; (2) rechaza si arrastraría propiedades con arrendamiento activo o tickets sin resolver; (3) rechaza dejar una cuenta con propiedades y sin ningún usuario.
- `POST /admin/cuentas/{cuenta_id}/propiedades/{property_id}/transferir` — **Único camino por el que una propiedad cruza de cuenta.** Escribe `owner_id` y `account_id` a la vez, por el escritor único. Bloqueada mientras la propiedad tenga arrendamiento activo o tickets sin resolver; el mensaje dice exactamente qué lo impide.

**Nuevas — owner**

- `GET /owner/cuenta` — «Mi cuenta»: plan vigente, qué incluye y qué no, propiedades usadas frente al límite, días restantes, y la frase literal de qué pasará al terminar. **Sin precios y sin botón de compra.** La cuenta se resuelve siempre desde `user.account_id` del servidor; **nunca hay un `account_id` en la URL** — el momento en que esta pantalla acepte un id ajeno es el momento en que filtra el plan y el número de casas de otro cliente. Debe inyectar `open_tickets` y `unread_messages` como todas las vistas del portal (`owner_portal.py:87-100`) o los contadores del menú desaparecen.
- `POST /owner/cuenta/solicitar-cambio` — Registra una solicitud: escribe `audit_log`, avisa al admin, confirma con flash. **No cambia nada.** Deliberadamente no es una compra, así que no roza la puerta de pagos.

**Modificadas**

- `POST /admin/owners` — (`pages.py:527-573`) Gana `cuenta_id: str = Form("")` opcional. Sin él, **crea una cuenta nueva** con `name` = nombre del owner (el caso normal). Con él, añade un segundo usuario a una administradora existente: así se materializa «varios usuarios por administradora» de D-013. En mock, `validate_mock_email/phone` (`pages.py:544-545`) siguen filtrando antes.
- `POST /admin/users/{user_id}/properties` — (`pages.py:840-863`) **Deja de poder cruzar cuentas.** Si el usuario destino está en otra cuenta, devuelve 400 con el mensaje «usa Transferir propiedad para mover una casa entre cuentas»; si está en la misma, escribe `account_id` junto a `owner_id` por el escritor único. **Sin este cambio, la ruta que ya existe rompe el invariante de custodia el primer día.**
- `POST /admin/sync-site-properties` — (`pages.py:597-655`) Rechaza asignar un `site_ref` a un propietario cuya cuenta tenga `is_operator = 0`, y aplica el límite fila por fila. Fija `account_id = owner.account_id` en cada `Property` que crea.
- `POST /api/owner/properties` — (`owner.py:53-66`) `_require_manage_enabled` primero, límite de cuenta después (409). Fija `account_id = current_user.account_id`. `owner_id` sigue saliendo de la sesión y nunca del cuerpo (`owner.py:60-62`).
- `POST /api/admin/properties` — (`admin.py:33-43`) Límite calculado sobre la cuenta del `owner` resuelto en `admin.py:35`, y `account_id = owner.account_id` escrito por el servidor, **ignorando cualquier `account_id` del cuerpo**.

**No se crea**

- `(ninguna ruta JSON /api/cuentas*)` — Decisión consciente. `POST /api/auth/login` (`auth.py:64-71`) y `get_current_user` (`auth.py:28-37`) **no aplican límite de intentos, ni bloqueo por cuenta, ni `is_active`, ni puerta de admin, ni TOTP, ni la tabla `sessions`** — verificado: `get_current_user` solo lee `request.session["user_id"]` y hace `db.get(User, user_id)`. Colgar de ahí el plan y los límites sería poner la lógica comercial detrás del punto más débil del sistema. Todo pasa por pantallas con sesión, CSRF y `sessions`. Arreglar ese agujero es del área de autenticación; aquí solo se evita empeorarlo.

---

## 7. Sitio público con más de una cuenta

Verificado hoy sobre `platform/data/platform.db`: las **tres** propiedades reales tienen `site_ref` (`AUR-DEMO-3` → owner #2, `AUR-001` → owner #3, `AUR-DEMO-2` → owner #2), es decir las tres vinieron de la sincronización del sitio.

- `site_ref` sigue siendo **único global**.
- La sincronización sigue siendo **solo de admin y unidireccional JSON→SQLite** (`pages.py:597-655`).
- Ninguna ruta de owner importa `site_content` ni escribe `site_ref` — hay prueba que lo verifica (§11, check 26).
- **Lo nuevo:** `accounts.is_operator`. Solo las propiedades de cuentas operadoras pueden estar espejadas desde el sitio público. Así, «la casa de un cliente aparece en aurahomescancun.com» deja de ser un descuido posible y pasa a ser **imposible por estructura**.
- La bandera **no se adivina**: la migración la enciende en la cuenta interna de Aura y en toda cuenta que herede al menos una propiedad con `site_ref` no nulo — un dato ya espejado del sitio es, por definición, de Aura. Toda cuenta creada después nace con `is_operator = 0`.

**Descartado:** guardar «qué cuenta publica» en `platform_settings`. Es clave/valor **global** de texto (`models.py:198-212`) y hoy solo lo usa `payments.py`; un ajuste global gobernando permisos por cliente significa que un error de tecleo afecta a todas las cuentas a la vez. Un booleano por cuenta es lo mismo, testeable y sin ese modo de fallo.

---

## 8. Puertas legales y banderas

### 8.1 Puerta legal por módulo

| Módulo | Estado | Bandera / puerta |
|---|---|---|
| Cuentas, planes, entitlements | **Se construye ahora, funciona igual en mock y en live** | Ninguna propia — ver §8.2 |
| Gastos itemizados, comprobantes, proveedores | Se construye ahora, se prueba en mock; datos reales cuando Legal firme (**D-016**) | `DATA_MODE` (`mockmode.py:41-78`) |
| Exportación fiscal (D-015) | Se construye ahora, se prueba en mock | `DATA_MODE` |
| Inquilinos (2b) | Encendido, datos ficticios | `TENANT_MODULE_ENABLED` + `DATA_MODE` |
| Cobro (2c) | **Cerrado** — `/api/payments*` devuelve 501 incondicional (`payments.py:154-159`) | `PAYMENTS_MODULE_ENABLED` |
| Agente IA | Escrito y desconectado | `AI_AGENT_ENABLED` (`ai_agent.py:93`) |

### 8.2 Por qué las cuentas NO llevan puerta propia

Una bandera capaz de apagar la **raíz del aislamiento** es un arma cargada. La separación mock/real ya la da el archivo de base (`db.py:20-37`): una cuenta creada en pruebas no existe en real. Los planes y los límites funcionan igual en mock porque son datos de prueba. `accounts.name` es un dato mercantil B2B; las personas siguen entrando por `validate_mock_email` / `validate_mock_phone`, y D-016 prohíbe inventar criterios legales nuevos.

> **Se rechaza explícitamente** una bandera tipo `ACCOUNTS_ENABLED` que conmute el predicado de aislamiento. Es el archivo donde un error no se nota hasta que un cliente ve los datos de otro; no debe tener interruptor de entorno.

### 8.3 Cable trampa mock ↔ real

`accounts.created_in_db` guarda el `basename` del archivo de base al crear la fila. Al arrancar: si la base resuelta es `platform.db` y alguna cuenta dice `platform-mock.db`, **la aplicación se niega a arrancar** — eso solo puede significar que alguien promovió la base de pruebas a producción, que es exactamente el desastre que `db.py:20-37` existe para evitar. El mensaje de error nombra el archivo, la cuenta ofensora y la salida documentada (restaurar la instantánea correcta). Mezclar datos de prueba con reales no tiene arreglo posterior; un arranque fallido sí.

### 8.4 Bandera de entorno nueva — una sola

`PLAN_LIMITS_ENFORCED` (por defecto `"true"`), leída en `mockmode.py` con el mismo patrón `os.environ.get(...).strip().lower() in {"1","true","yes"}`.

- Solo puede hacer el sistema **más permisivo en la dimensión comercial**: deja de bloquear la creación por límite y por prueba vencida.
- **Nunca toca la dimensión de aislamiento.** Apagarla no hace que nadie vea nada ajeno.
- Con la bandera apagada se escribe una fila en `audit_log` por **cada** creación que se habría bloqueado, para que la excepción no sea invisible ni gratuita.
- Existe porque un fallo en la lógica de límites que deje al CEO sin poder dar de alta una casa un domingo necesita un interruptor documentado en vez de un parche a las tres de la mañana. (Fly está suspendida; fase local — un redespliegue no es la vía rápida.)

Ninguna bandera existente se toca. `PAYMENTS_MODULE_ENABLED` y el 501 de `payments.py:157-159` quedan intactos porque esta área no cobra nada.

---

## 9. Integridad sin claves foráneas

`PRAGMA foreign_keys` devuelve `0` en ambas bases (verificado hoy). Ni las FKs ni las cascadas se imponen. Además, `User.properties` tiene `cascade="all, delete-orphan"` en el ORM: **borrar un usuario por la sesión borra sus propiedades**. De ahí tres reglas:

1. **Escritor único.** Toda escritura de `properties.account_id` pasa por
   `asignar_propiedad_a_cuenta(db, prop, cuenta, actor)`, que escribe `owner_id` **y** `account_id` a la vez y deja rastro. Ninguna otra línea del repositorio asigna esa columna.
2. **Verificador en cada arranque.** `verificar_integridad_cuentas()` cuenta (a) usuarios con `account_id` NULL por rol, (b) propiedades con `account_id` NULL, (c) propiedades donde `account_id` ≠ la cuenta de su dueño. Escribe **una** fila en `audit_log` e imprime en consola. **No tumba el arranque** por estos tres: la aplicación es la única herramienta con la que el CEO puede arreglar los datos, y un servidor que no arranca no arregla nada. **Sí tumba el arranque** en dos casos, que solo pueden significar que algo salió muy mal: `accounts` vacía habiendo usuarios (el relleno no hizo nada en silencio) y el cable trampa de §8.3.
3. **Nunca se borran cuentas ni usuarios.** Solo `status` y `is_active`.

---

## 10. Migración

> ⚠️ **Trampa de arranque, verificada y crítica.** `on_startup()` (`main.py:221-268`) hace `return` anticipado en `main.py:242-243` cuando ya existe un admin. **Cualquier cosa registrada después del bloque de siembra NUNCA se ejecutaría sobre `platform.db`**, que es precisamente la base que hay que migrar. `_ensure_accounts()` se llama en el bloque de `_ensure_*` (`main.py:225-230`), inmediatamente después de `_ensure_ticket_columns()` y **antes** de `db = SessionLocal()`.

**Estado real de partida, verificado hoy:**

| | `platform.db` (REAL) | `platform-mock.db` |
|---|---|---|
| Tablas | **11** | 19 |
| Faltan | `ai_usage`, `announcements`, `announcement_recipients`, `messages`, `platform_settings`, `sessions`, `ticket_events`, `ticket_photos` (**8**) | — |
| Usuarios | 3 — administrador #1, propietario #2, propietario #3 | 8 |
| Propiedades | 3 — #3→owner 2, #4→owner 3, #5→owner 2; **las tres con `site_ref`** | 5 |
| Arrendamientos | 0 | — |
| `PRAGMA foreign_keys` | 0 | 0 |

Es decir: el primer arranque en `live` tras este cambio aplicará **de golpe** 8 tablas, las 7 columnas de seguridad de `users` que faltan, el índice de `site_ref`, las 2 columnas de `account_id`, los 5 índices y el relleno completo. Ese es el motivo exacto por el que el paso 0 no es opcional.

**PASO 0 — Instantánea previa, obligatoria.** Reutilizar `_snapshot(src, dst)` de `platform/app/backup.py:44-66`, que abre el origen en `file:...?mode=ro`, usa `sqlite3.Connection.backup()` y corre `PRAGMA integrity_check` **sobre la copia**. Un `shutil.copy` de una base viva puede capturar una transacción a medias y producir un respaldo corrupto que parece bueno. Destino `platform/data/backups/<basename>.<UTC>.pre-migracion.db`, conservando las últimas 10. **Si la instantánea falla, la migración no se ejecuta y el arranque aborta con mensaje explícito.** (Es una copia local antes de alterar el esquema; nada que ver con los respaldos de Fly/Actions que el CEO canceló.)

**PASO 1 — Ensayo obligatorio.** Guion nuevo `platform/scripts/migrar_cuentas.py --simular`: abre la base en `mode=ro`, imprime qué cuentas crearía, qué usuarios y propiedades tocaría y qué filas quedarían sin resolver, y **sale sin escribir un byte**. Se corre primero contra una **copia** de `platform.db`.

**PASO 2 —** `Base.metadata.create_all()` (`main.py:225`) crea `accounts` y `account_plan_events` solas: son tablas nuevas.

**PASO 3 —** `_ensure_account_columns()`, calcada de `_ensure_user_security_columns` (`main.py:150-181`): `PRAGMA table_info(users)`; si el conjunto no está vacío y falta `account_id`, `ALTER TABLE users ADD COLUMN account_id INTEGER`. Ídem `properties`. Si `PRAGMA` devuelve vacío, `return` — `create_all` se encarga. Guarda de motor idéntica: `if not engine.url.get_backend_name().startswith("sqlite"): return`.

**PASO 4 —** Los cinco `CREATE INDEX IF NOT EXISTS` de §2.4.

**PASO 5 — Relleno, todo dentro de un único `engine.begin()`** (o entra completo o no entra nada):

- **(a)** Cuenta operadora **«Aura · Operación»** si no existe: `is_operator=1`, `plan='enterprise_plus'`, `trial_started_at` NULL, `plan_note='migración D-013'`. Todo usuario con `role='admin'` y `account_id` NULL se une a ella.
- **(b)** Cada usuario con `role='owner'` y `account_id` NULL recibe **una cuenta propia**, `name` = nombre del usuario, `primary_user_id` = su id, `trial_started_at` NULL, `status='activa'`, `plan_assigned_at` NULL. **Nunca se fusionan dos propietarios en una cuenta:** fusionar es irreversible y, si uno resultara ser un cliente y no el CEO, sería una fuga entre clientes; separar después es un POST auditado y barato. En la base real esto crea exactamente **2** cuentas de propietario más la operadora.
- **(c) Plan de las cuentas migradas: `enterprise_plus`, sin reloj de prueba.** Motivo: el propietario #2 tiene 2 casas y el propietario #3 tiene 1; dejarlas en `trial` (límite 1) las pondría **por encima del límite el día uno** y el CEO viviría su propia plataforma como una avería. **Una migración no puede quitar capacidades que ya existían.** Se escribe `plan_note = 'migración D-013 · plan sin límite para no alterar lo que este propietario ya podía hacer; reasignar desde /admin/cuentas'` y `plan_assigned_at` queda **NULL**, así que el directorio de admin lo marca en grande como **«plan sin asignar»** hasta que el CEO decida. *(Este punto es el injerto que corrige la propuesta ganadora, que dejaba deliberadamente al CEO bloqueado.)*
- **(d)** Cada usuario con `role='tenant'` y `account_id` NULL se une a la cuenta del propietario de la propiedad de su arrendamiento más reciente. **Si no se resuelve con certeza, se DEJA EN NULL y se reporta** — adivinar la cuenta de un inquilino es colgar los datos personales de una persona del cliente equivocado, y un NULL cae a la rama heredada, que para inquilinos no cambia nada. En `platform.db` hay 0 arrendamientos: hoy es un no-op.
- **(e)** `UPDATE properties SET account_id = (SELECT account_id FROM users WHERE users.id = properties.owner_id) WHERE account_id IS NULL`. Se ejecuta **después** de (b), nunca antes. Una propiedad cuyo `owner_id` no resuelva a ningún usuario (posible: no hay FKs) se queda NULL y se reporta; no se inventa dueño.
- **(f)** `is_operator = 1` en toda cuenta que haya heredado al menos una propiedad con `site_ref` no nulo. En la base real enciende las dos cuentas de propietario, que es lo correcto: las tres casas vinieron del sitio público de Aura.

**PASO 6 — La migración no arranca ningún reloj comercial.** `trial_started_at` queda NULL en toda cuenta migrada, así que no hay `trial_ends_at`, no hay día 91 y nada se bloquea por vencimiento. El reloj solo arranca cuando el número de propiedades de una cuenta pasa de 0 a 1, cosa que en una cuenta migrada con casas ya existentes no volverá a ocurrir.

**PASO 7 —** `verificar_integridad_cuentas()` al final de `_ensure_accounts()` (§9).

**PASO 8 — Propagación en escritura** (sin esto el relleno se degrada con cada alta nueva):

| Ruta / punto | Archivo:línea | Qué añade |
|---|---|---|
| Siembra del admin | `main.py:240-256` | Cuenta operadora |
| Alta de propietario | `pages.py:527-573` | Crea cuenta nueva, o usa `cuenta_id` |
| Alta de inquilino | `owner_portal.py` (`create_tenant`) | Hereda `user.account_id` del propietario |
| Alta de usuario JSON | `admin.py:89-105` | Hereda la cuenta del solicitante; si es NULL, la operadora |
| Sincronización del sitio | `pages.py:597-655` | `account_id = owner.account_id` |
| Alta de propiedad (owner / admin) | `owner.py:53-66`, `admin.py:33-43` | `account_id` del servidor |

`google_sso.py` no crea usuarios: el auto-registro está prohibido (SECURITY.md §1.1).

**PASO 9 — Idempotencia.** Cada paso está guardado por «si falta la columna / si el índice no existe / si `account_id` es NULL / si la cuenta no existe». Ninguna sentencia `DELETE`, ningún `DROP`, ningún cambio de tipo. Ejecutarlo cien veces deja la base idéntica.

**PASO 10 — Reversión.** SQLite no tiene `DROP COLUMN`: revertir es **restaurar el archivo del paso 0**, no deshacer DDL. Se documenta en una línea en `docs/phase2/DB_SCHEMA.md`: detener la app, apartar el `.db` actual, poner la instantánea previa en su sitio, arrancar con la versión anterior del código. Mientras tanto, **el código nuevo tolera `account_id` NULL en todas partes**, así que desplegar el código sin haber corrido el relleno tampoco rompe nada: se comporta exactamente como hoy.

**PASO 11 — Colateral que se arregla de paso.** `platform/tests/test_migrate.py` lleva rutas absolutas de Windows en las líneas 3-4 y **no imprime la línea `RESULTADO:`**, por lo que `run_all.py:20` no suma sus 7 PASS al total. Se corrige: rutas relativas y línea de resultado.

---

## 11. Interfaz

Todo server-rendered, **cero JavaScript nuevo** (`platform.js` sigue siendo el mismo IIFE del cajón lateral).

| Pantalla | Plantilla | Contenido |
|---|---|---|
| Directorio de cuentas (admin) | `admin_accounts.html` (nueva) | Tabla: nombre, plan, estado, usuarios, propiedades usadas/límite, prueba, marca de operadora. Fila resaltada cuando `plan_assigned_at IS NULL`. Envuelta en contenedor con `overflow-x: auto` propio: el armazón colapsa el menú a 860px pero **no hay tablas responsivas** |
| Ficha de cuenta (admin) | `admin_account_form.html` (nueva) | **Tres bloques `.card` separados, cada uno con su propio `<form method="post">`**: plan, prueba, estado. Debajo: miembros, propiedades e historial de `account_plan_events` con `.timeline`. Etiqueta literal en el campo de nota: «referencia del acuerdo — no escribas datos bancarios ni números de tarjeta aquí» |
| Mi cuenta (owner) | `owner_account.html` (nueva) | Plan, estado, días restantes, usadas/límite; tabla de lo que incluye y lo que no; frase literal de qué pasa al vencer; formulario «Solicitar cambio de plan». **Cero precios, cero botón de compra** |
| Banda de estado | `_account_banner.html` (nueva, `include`) | Una sola línea, solo cuando hay algo que decir: prueba a 15 días o menos, prueba vencida, cuenta por encima del límite, cuenta suspendida, plan sin asignar. Se inserta en `base.html` dentro de `.app-main` (línea 103), justo debajo de `.mock-banner` (línea 11) |
| Menú lateral | `base.html` (edición) | `«Mi cuenta → Plan»` para owner y `«Cuentas»` para admin, con el patrón `{% if active == 'cuentas' %} is-active{% endif %}` ya usado en las líneas 31-98. Distintivo `.nav-badge` cuando quedan 7 días o menos |

**Formularios separados a propósito:** un único formulario con varios botones exigiría JS o un despacho por campo oculto, y el despacho por campo es justo lo que hace frágil `POST /owner/tickets/{id}/actualizar` (`owner_portal.py:219-280`).

### 11.1 Reglas CSP y CSS — verificadas contra el fuente

- **Prohibido** `onclick=`, `onsubmit=` y `style="`. `platform/tests/test_ui.py:92` comprueba las tres cadenas y falla si aparecen.
- `csrf_input(request)` es global de plantilla (`security.py:147-151`) y va en **todo** formulario POST.
- Una acción delicada se confirma con una **pantalla intermedia de POST**, nunca con `confirm()`.
- **Clases que SÍ existen** en `platform/app/static/platform.css`: `.card`, `.container`, `.form-grid`, `.form-grid-2`, `.form-grid-4`, `.form-actions`, `.btn`, `.btn-primary`, `.btn-ghost`, `.btn-danger-inline`, `.btn-disabled`, `.alert`, `.alert-success`, `.alert-error`, `.badge`, `.badge-admin/-owner/-tenant/-new`, `.status`, `.status-available`, `.status-rented`, `.nav-item`, `.nav-badge`, `.nav-group`, `.timeline`, `.mock-banner`, `.muted`, `.hint`, `.help`, `.empty-row`, `.inline-form`.
- **Clases que NO existen y que varias plantillas actuales citan sin efecto** — no reutilizarlas: `.alert-warning`, `.btn-danger`, `.flash-ok`, `.filters`, `.actions`, `.section-head`, `.btn-block`, `.meta`, `.row-urgent`.
- Lo nuevo que hace falta se **añade a `platform.css`** (hoja externa, permitida por `style-src 'self'`): `.alert-warning`, `.badge-plan`, `.status-trial`, `.status-suspendida`, `.status-cerrada`, `.table-scroll`. Una entrada por clase, nada más.
- La barra de uso (7 de 20 casas) se dibuja con **clases de tramo predefinidas** (`.usage-0` … `.usage-100` en pasos de 10), **nunca** con un atributo `style` de anchura — eso rompería `test_ui.py`.
- Todas las cadenas visibles llegan al contexto **ya resueltas** desde `ETIQUETAS_*` de `plans.py` (D-014).

---

## 12. Alcance que este diseño toca fuera de sí mismo

| Cambio | Archivo | Por qué es obligatorio |
|---|---|---|
| `_predicado_propietario` y 6 sustituciones | `scoping.py:51,68,116,143,172` | Raíz de D-013 |
| `_ensure_accounts()` **antes** del bloque de siembra | `main.py:225-230` | El `return` de `main.py:242-243` la haría inerte |
| Rechazo de cruce de cuenta | `pages.py:840-863` | Sin esto, la ruta existente rompe la custodia el primer día |
| `is_operator` en la sincronización | `pages.py:597-655` | La casa de un cliente no puede aparecer en el sitio público |
| `account_id` + límite en las 3 puertas de alta | `owner.py:53-66`, `admin.py:33-43`, `pages.py:597-655` | Un límite que solo cubre una puerta no es un límite |
| Globales por defecto de plantilla | `security.py:154-168` | Sin ellos `base.html` rompe las 27 plantillas |
| Inyección de `contexto_cuenta` | `owner_portal.py:81-85`, `pages.py:459-512`, `pages.py:692-704`, `tenant.py` | Mismo problema repetitivo que ya tiene `_nav_badges` |
| Rutas relativas + línea `RESULTADO:` | `tests/test_migrate.py:3-4` | Sus 7 PASS no suman hoy |

---

## 13. Handoff

- [ ] `plans.py` con matriz, etiquetas y las siete funciones de §5
- [ ] `models.py`: `Account`, `AccountPlanEvent`, `users.account_id`, `properties.account_id`
- [ ] `_ensure_accounts()` + `verificar_integridad_cuentas()` en `main.py`, registradas en `main.py:225-230`
- [ ] `scripts/migrar_cuentas.py --simular` y ensayo contra copia de `platform.db` **y** de `platform-mock.db`
- [ ] `asignar_propiedad_a_cuenta()` como escritor único
- [ ] `_predicado_propietario` y las seis sustituciones en `scoping.py`
- [ ] 10 rutas nuevas + 5 modificadas (§6)
- [ ] 4 plantillas nuevas + 2 ediciones + 6 clases nuevas en `platform.css`
- [ ] `test_cuentas.py` (28 checks) y `test_migrate_cuentas.py`
- [ ] `test_scoping.py` en verde **sin editar**
- [ ] `docs/phase2/DB_SCHEMA.md` y `docs/phase2/PLAN.md` actualizados; `docs/ARCHITECTURE_STATE.md` descongelado; D-010 y D-013 escritos en git, no solo en Drive

**Estado: 0 de 12 hechos. Línea base: 261 pruebas en verde, 10 suites, 0 fallos (2026-09-08).**
