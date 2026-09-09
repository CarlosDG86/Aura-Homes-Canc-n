<!-- Generado por el panel de diseño del 2026-09-08. Ganadora: A · Panel derivado: cero tablas nuevas, cero rutas nuevas (ángulo mínimo) -->

# Área D · Panel del propietario, filtros y reportes

**Fecha:** 2026-09-08 · **Estado:** Diseño cerrado, listo para construir · **Fase:** 2a/2b (solo lectura)

Diseña los puntos 2.1 y 2.2 del feedback del CEO del 2026-09-07. Premisas cerradas: D-013 (raíz de aislamiento = cuenta), D-014 (español con cadenas extraídas), D-015 (exportación fiscal = otra área), D-016 (puerta legal existente).

---

## 1. Alcance y regla de oro

**Dentro:** los cuatro KPIs del CEO, cuatro indicadores de salud operativa, un bloque de calidad de datos, filtros por zona / tamaño / selección, y la conexión de esos filtros con los dos CSV del propietario.

**Fuera, a propósito** (y hay que decírselo al CEO, sección 11): gastos y comprobantes (área E), proveedores (área F), exportación fiscal por año (D-015, área E), planes y entitlements (área de cuentas), cobros y morosidad (2c sigue cerrado por el catch-all 501 de `payments.py:154-159`).

> **Regla de oro de esta área: el panel NO ESCRIBE NI UNA FILA.** Ni para «reconciliar» una discrepancia, ni para corregir `Property.status`. Todas sus rutas son GET. Una pantalla de solo lectura no puede ser el vector de un cambio no querido, y esa garantía es más barata de auditar que cualquier permiso.

**Segunda regla, igual de dura: ningún CSV de esta área contiene nombre, correo, teléfono ni identificador de inquilino.** Solo conteos y atributos de la propiedad. La ocupación se expresa «ocupada/vacía», nunca «ocupada por Fulano». Ver el callout legal de la sección 10.

---

## 2. Dónde vive el código, y por qué

| Qué | Dónde | Por qué |
|---|---|---|
| Panel `/owner` | **Módulo nuevo `app/routers/owner_dashboard.py`** | `pages.py` tiene 908 líneas y mezcla login, 2FA, alta de propietarios, administración de usuarios y sincronización del sitio; el panel está ahí por accidente histórico y duplica a mano el cálculo de insignias que ya vive en `owner_portal._nav_badges` (`pages.py:674-687` vs `owner_portal.py:87-99`). `owner_portal.py` tiene 517 líneas y va a crecer con gastos (área E) y proveedores (área F). |
| Helper de filtros y agregados | **Módulo nuevo `app/filtros_owner.py`** (sin router) | Lo importan `owner_dashboard.py` (panel + CSV de cartera) y `owner_portal.py` (lista de tickets + reporte). Si el helper viviera en cualquiera de los dos routers habría importación circular: `owner_portal` ya importa de `pages` (`owner_portal.py:60`). |
| Etiquetas en español | **Módulo nuevo `app/labels_es.py`** | D-014. Ver sección 8. |
| Filtros en la lista y el reporte de tickets | `owner_portal.py:110` y `owner_portal.py:140`, **extendidos** | Se conservan URL, plantillas y columnas del CSV: hay pruebas en verde que las fijan (`tests/test_owner_portal.py:151-156`). |

`owner_dashboard.py` importa `_require_owner`, `_ctx` y `_nav_badges` de `owner_portal.py`. No hay ciclo: `owner_dashboard → owner_portal → pages`.

> ⚠️ **Paso obligatorio, no cosmético:** borrar `@router.get("/owner")` de `pages.py:658-704` **en el mismo commit** en que se añade el nuevo. `main.py:122` registra `pages.router` ANTES que `owner_portal.router` (`main.py:124`) y que el nuevo módulo; con dos rutas del mismo método y camino, Starlette se queda con la primera registrada. El panel nuevo no se vería jamás, sin error y sin traza. Hay una prueba dedicada a esto (sección 9).

---

## 3. Definición de OCUPACIÓN — la decisión de fondo

Existen dos fuentes que pueden discrepar. **Se elige el CONTRATO (`Lease` con `status = active`)** y se descarta `Property.status`.

**Definición literal, la que va impresa bajo el KPI:**

> Ocupación % = propiedades con al menos un arrendamiento activo ÷ total de propiedades del propietario.

**Por qué el contrato y no el estatus publicado (tres razones verificables):**

1. `Property.status` es un dato de **marketing del sitio público**. `_mirror_fields_from_site` (`pages.py:577-594`) lo incluye entre los campos espejados y `sync_site_properties` hace `setattr(existing, key, value)` sobre todos ellos en cada corrida (`pages.py:636-640`): un KPI montado ahí **cambia solo**, sin que el propietario toque nada.
2. El propietario **no tiene ninguna pantalla** para modificar `Property.status`; es admin-only. Un indicador de gestión que su dueño no puede mover no es un indicador, es un rumor.
3. El arrendamiento es el hecho que el propietario **crea** (`owner_portal.py:335`) y **termina** (`owner_portal.py:373`) dentro de la plataforma, y es la misma fuente que alimenta «Inquilinos», el enrutado de tickets y `scoped_users` (`scoping.py:160-170`). Elegirlo mantiene los cuatro KPIs internamente consistentes.

Razón estructural adicional, mirando a D-010: cuando la plataforma se venda a otra administradora, sus propiedades tendrán `site_ref = NULL` y `status` se quedará en `available` para siempre. `Property.status` es **incapaz por construcción** de medir ocupación en el producto que se va a vender.

### 3.1 Qué se hace con la discrepancia

**No se reconcilia. No se crea tabla ni proceso ni botón. Se cuenta y se muestra**, distinguiendo los dos sentidos, que no valen lo mismo:

| Caso | Lectura | Riesgo |
|---|---|---|
| `status = rented` **y sin** arrendamiento activo | Probablemente falta capturar el contrato; o alguien vive ahí sin registro ni acceso al portal | La renta se está cobrando fuera del sistema: es el agujero que arruina la exportación fiscal (D-015) |
| `status = available` **y con** arrendamiento activo | La vivienda sigue anunciada en el sitio público, con fotos y ubicación, mientras está habitada | Privacidad del inquilino + llamadas de prospectos por una casa ocupada |

Se muestra como aviso sobre la tabla («N propiedad(es) no coinciden con el sitio público») y como `<span class="badge">` en la fila, y se puede aislar con `?ocupacion=revisar` — **un valor más del filtro que ya existe, no una ruta nueva**. No hay botón de «corregir»: escribir `status` desde aquí lo revertiría la siguiente sincronización y podría cambiar lo que ve el público.

> **Dato verificado que el CEO va a encontrarse el primer día:** en `data/platform.db` hay 3 propiedades y **0 arrendamientos**. La propiedad #3 («Departamento SM 15», owner_id 2) tiene `status = 'rented'`. Es decir: el propietario #2 abrirá su panel y verá **Ocupación 0 %** con una de sus dos casas marcada como rentada en el sitio. El número no está mal; los contratos no están cargados. Sin el texto explícito de estado vacío, esa primera mirada decide si el panel se usa o no.

---

## 4. Los indicadores — conjunto completo y su justificación

Cada ficha lleva **su definición literal impresa debajo**. Un KPI sin definición visible es un KPI que dos personas leen distinto.

### 4.1 Primarios (los cuatro del CEO)

| # | Indicador | Cálculo | Qué decide el propietario con él |
|---|---|---|---|
| 1 | **Propiedades** | `COUNT` sobre `owned_properties` | Denominador de todo lo demás |
| 2 | **Inquilinos activos** | `COUNT(DISTINCT Lease.tenant_id)` con `Lease.status = active`, join a las propiedades propias | A cuánta gente le responde; denominador de los comunicados |
| 3 | **Tickets abiertos** | `status != resolved` (open + in_progress) | Qué atiende hoy. **Misma definición que la insignia del menú** (`owner_portal.py:95`), obligatoriamente calculada por la misma función |
| 4 | **Ocupación %** | Sección 3 | ¿Tengo que anunciar algo? |

> ❗ **Corrección a las tres propuestas:** el KPI de Inquilinos **NO** puede salir de `scoped_users`. `scoping.py:160-170` hace el `DISTINCT` sobre `Lease.tenant_id` **sin filtrar `Lease.status`**, así que ese conjunto incluye a inquilinos con contrato terminado y el KPI saldría inflado. (Efecto secundario ya existente, fuera de esta área pero conviene anotarlo: `_my_tenants` en `owner_portal.py:100-102` arrastra el mismo problema y sigue listando ex-inquilinos.)

### 4.2 Secundarios (salud operativa)

| # | Indicador | Cálculo | Por qué está |
|---|---|---|---|
| 5 | **Emergencias abiertas** | `priority = emergencia` y `status != resolved`. Se destaca solo si > 0, reutilizando `.flash-urgent` (`platform.css:501`) | Es lo único que justifica interrumpir el día |
| 6 | **Ticket abierto más antiguo (días)** | `MIN(created_at)` de los no resueltos | «Qué se me quedó parado» — la misma señal que ya justifica el promedio de horas en `owner_portal.py:150-156` |
| 7 | **Unidades vacías (n)** | Complemento de la ocupación, en absoluto | El porcentaje no se traduce en acción; «3 casas vacías» sí |
| 8 | **Mensajes sin leer** | Ya se calcula en `_nav_badges` | Continuidad con la insignia del menú |

### 4.3 Bloque «Datos por revisar» (calidad de datos, no es una ficha)

Lista con enlaces, debajo de las fichas. Es el bloque que garantiza que en marzo el dato exista:

- N discrepancias sitio ↔ contrato (sección 3.1), por sentido → `?ocupacion=revisar`
- N arrendamientos activos **sin renta capturada** (`monthly_rent IS NULL`)
- N arrendamientos activos **sin fechas** (`start_date` / `end_date` nulos)
- N propiedades sin `zone`, sin `area_m2` o sin `bedrooms` (rompen los filtros en silencio)

### 4.4 Lo que NO se pinta, y por qué

| Ausente | Razón verificada |
|---|---|
| **Contratos por vencer** | `end_date` no se escribe nunca: `create_tenant` (`owner_portal.py:333-336`) crea el `Lease` sin fechas y `end_lease` (`owner_portal.py:373`) solo cambia `status`. Verificado en datos: los 2 arrendamientos de `platform-mock.db` tienen `start_date`, `end_date` y `monthly_rent` en NULL. Saldría 0 siempre |
| **Cobrado / morosidad** | 2c cerrado, `payments.py:154-159` devuelve 501 incondicional |
| **Gastos / rentabilidad** | Área E, bajo la puerta D-016 |
| **Renta mensual (cualquier cifra de dinero)** | Ver 4.5 |

### 4.5 Por qué el panel v1 no lleva ninguna cifra de dinero

La propuesta A proponía «Renta mensual estimada» = Σ `COALESCE(lease.monthly_rent, property.price_amount)`, rotulada «estimada». **Se rechaza.** `price_amount` es **precio de anuncio**, espejado del `priceMXN` del JSON público (`pages.py:588`), no lo pactado; y la propia propuesta lo llamaba «el puente natural con el módulo fiscal». Un número aproximado que alimenta algo que va a ver un contador no se arregla con una etiqueta: se arregla no poniéndolo. Añádase que SQLite no tiene tipo decimal y SQLAlchemy guarda `Numeric` como coma flotante, así que cualquier suma de dinero del panel sería además informativa por redondeo.

**En su lugar**, el bloque 4.3 imprime «Renta contratada: sin capturar en N de M contratos», que es información verdadera y accionable. El dinero entra en el panel cuando el alta de inquilino capture `monthly_rent` (decisión CEO-D-05).

---

## 5. Filtros (punto 2.2)

Un solo `<form method="get">` que envuelve **la barra de filtros Y la tabla con sus casillas**. Se incluye como parcial `_owner_filtros.html` desde el panel, la lista de tickets y el reporte, para que las tres pantallas hablen del mismo universo.

> El formulario es **GET, así que NO lleva `csrf_input`**. `CSRFMiddleware` solo guarda métodos mutantes (`security.py:36`, `UNSAFE_METHODS = {POST, PUT, PATCH, DELETE}`). Hay que resistir la tentación de añadirlo «por costumbre»; hay una prueba que lo fija.

| Parámetro | Control | Valores | Notas |
|---|---|---|---|
| `zona` | `<select>` | claves normalizadas de las zonas **de la cartera propia**, más `sin-zona` | Ver 5.1 |
| `recamaras` | `<select>` | `1`, `2`, `3`, `4mas`, `sin-dato` | `bedrooms` es entero exacto y es el lenguaje comercial del propietario |
| `m2` | `<select>` | tramos: `hasta80`, `80a150`, `mas150`, `sin-dato` | Ver 5.2 |
| `ocupacion` | `<select>` | `ocupada`, `vacante`, `revisar` | `revisar` = discrepancia (sección 3.1). Evita una ruta dedicada |
| `prop` | `<input type="checkbox" name="prop">` por fila, **repetible** | ids | La «selección» del CEO. Ver 5.3 |
| `formato` | `<button name="formato" value="csv">` | `csv` | Un botón de envío aporta su `name/value` solo cuando es el pulsado |

**Tamaño = m² Y recámaras, los dos, como filtros independientes.** No se sustituyen: recámaras es el eje comercial («mis de 3 recámaras»), m² es el eje de reporte y de coste de mantenimiento. Ambas columnas existen (`models.py:135` y `:137`) y **están pobladas**: verificado en `data/platform.db` → `area_m2` = 62, 180, 192 y `bedrooms` = 1, 3, 3; en `platform-mock.db` se añaden 245 y 280 m². Se descartan campos numéricos min/max: cuatro parámetros más, validación de rangos invertidos, y peor en un móvil donde los selects ya ocupan todo el ancho.

Todo filtro tiene cubeta explícita **«sin dato»**, y la página imprime en texto «Mostrando N de M propiedades · X sin zona · Y sin metros». Un filtro que excluye filas nulas sin decirlo produce reportes truncados que nadie detecta.

Validación en servidor por **lista blanca**: un valor no reconocido se ignora y se anuncia con una viñeta («filtro no reconocido, se ignoró»), nunca un 500 y nunca interpolación en SQL. «Limpiar» es un `<a href="/owner">`, no un reset por JS.

### 5.1 Zona: normalización EN LECTURA, sin columna nueva

`Property.zone` es texto libre (`models.py:130`) espejado del JSON público. **No se crea `zone_key`** y **no se normaliza en la base**, por tres razones:

1. `pages.py:636-640` hace `setattr` sobre las claves que devuelve `_mirror_fields_from_site`, que no incluiría `zone_key`: cada sincronización dejaría la clave obsoleta y el filtro empezaría a perder casas **semanas después, en silencio**. Es el peor fallo posible en un filtro.
2. Verificado en `data/properties.json`: 7 entradas, zonas exactas y repetidas («Residencial Cumbres» dos veces, junto a «Centro», «Puerto Cancún», «Lagos del Sol», «Polígono Sur», «Arbolada»). Hoy no hay ni un caso que la columna resuelva.
3. Property es espejo unidireccional JSON→SQLite; escribir una columna derivada ahí es sembrar trabajo para D-013.

**Cómo se agrupa entonces:** la cartera del propietario se carga en memoria una vez por petición (sección 7) y la clave se calcula en Python:

```python
def clave_zona(z: str | None) -> str:
    if not z:
        return ""
    s = unicodedata.normalize("NFKD", z)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())
```

> **Hecho verificado que obliga a esto:** `LOWER()` de SQLite es **solo ASCII**. Comprobado contra `data/platform-mock.db`: `lower('POLÍGONO')` devuelve `pol\xcdgono` y `lower('Polígono')` devuelve `pol\xedgono` — **no son iguales**. Una comparación de zona insensible a mayúsculas y acentos **no se puede escribir en SQL** en esta base sin una función personalizada o una columna almacenada. Filtrar en Python no es pereza: es la única opción sin migración.

El desplegable se rellena solo con las zonas **de la cartera propia**. Poblarlo con un `DISTINCT` global sería una fuga silenciosa entre cuentas: revelaría en qué zonas opera otro propietario.

### 5.2 Tramos de m²

Constante de módulo en `filtros_owner.py`, editable en una línea:

```python
TRAMOS_M2 = (("hasta80", None, 80), ("80a150", 80, 150), ("mas150", 150, None))
```

Advertencia honesta para el CEO: con su cartera real (62, 180, 192 m²) el tramo intermedio queda **vacío**. Ver CEO-D-06.

### 5.3 Selección: efímera, en la URL, sin tabla nueva

Casillas `<input type="checkbox" name="prop" value="{{p.id}}">` dentro del mismo formulario. Al enviar serializan a `?prop=3&prop=7`. **La URL es la persistencia**: se marca como favorito y se comparte, que es el 90 % del valor de una cartera guardada al 0 % de su coste.

Se **rechazan las carteras guardadas con nombre** (tabla `owner_portfolios` / `property_groups`) por tres razones acumulativas:
- «selection» aparece en la frase del CEO dentro de una lista de **filtros para un reporte** («list filters by zone, size, selection — para los reportes del Owner»), no como algo que se nombre o se reutilice.
- Por **D-013 una cartera pertenece a la CUENTA, no al usuario**. Crearla hoy garantiza una segunda migración con `account_id` en cuanto exista `accounts`, esta vez con datos dentro.
- `PRAGMA foreign_keys` está en **0** (verificado: `db.py:41-43` no registra ningún listener que lo active; la consulta devuelve `(0,)`), así que una cartera puede quedar apuntando a una propiedad borrada sin que nada lo impida.

Si mañana el CEO las pide, la URL con `?prop=…` es la semilla exacta y no se tira nada.

**Topes y saneamiento** (en el mismo commit, no después): máximo **200** ids en `?prop`; los no numéricos se descartan; la lista se **interseca** con `owned_properties`, de modo que un id ajeno simplemente desaparece del resultado —mismo criterio ya escrito en `owner_portal.py:120-127` («el filtro es comodidad, no control de acceso»)—; se muestra un aviso neutro («algunas propiedades del enlace ya no están disponibles») que **no confirma si existen**.

---

## 6. Reportes y exportación

**Se REUTILIZA `GET /owner/tickets/reporte`, no se sustituye.** Ya calcula por unidad total / abiertos / en proceso / resueltos / emergencias / horas promedio / categoría frecuente y ya baja en CSV (`owner_portal.py:141-193`); ya está enlazado en el menú (`base.html`, grupo Mantenimiento) y ya tiene pruebas en verde (`tests/test_owner_portal.py:151-156`). Reescribirlo no añade ni un dato.

**No se crea ningún centro de reportes** (`/owner/reportes`, `/owner/reportes/cartera`, …): dos URLs que devuelven lo mismo es más superficie que auditar en scoping para una cartera de 3 a 7 casas. La exportación de la cartera cabe en `?formato=csv` del propio panel, siguiendo el patrón que el reporte de tickets ya usa (`owner_portal.py:186-190`).

### 6.1 Reglas comunes a TODO CSV de esta área

| Regla | Detalle | Por qué |
|---|---|---|
| **Cero PII de inquilino** | Ni nombre, ni correo, ni teléfono, ni id. Ocupación = «ocupada/vacía» | Sección 10 |
| **Escape de fórmulas** | Si una celda empieza por `=`, `+`, `-`, `@`, tabulador o retorno, se antepone `'` | Hoy `owner_portal.py:180-188` vuelca `p.title` crudo y Excel lo ejecutaría |
| **BOM UTF-8** | `﻿` al inicio + `charset=utf-8` en el `Content-Type` | Sin él, Excel en español destroza «Categoría» y «Cancún» |
| **Cabecera de procedencia** | Primeras filas: fecha y hora, usuario, filtro aplicado en prosa, nº de filas | Un CSV filtrado que llega a un tercero no puede parecer la cartera completa |
| **Tope de filas** | `TOPE_FILAS_CSV = 2000`. Por encima se niega y se pide afinar el filtro | Separa una descarga legítima de un volcado; y evita el DoS |
| **Registro** | `audit(db, request, "owner.report.export", object_type="report", meta=filtro + nº filas)` | `security.audit()` (`security.py:486-507`) ya captura actor, rol e IP y nunca tumba la petición. **Solo se audita la descarga, no la lectura del panel**: auditar cada carga convierte la bitácora en ruido |
| **Descarga** | `Content-Disposition: attachment`, nombre de archivo que refleja el filtro | — |
| **Entitlement** | Todo pasa por un único helper `puede_exportar(user)` que **hoy devuelve `True`** | Cuando existan los planes se cambia una función, no seis rutas |

Las columnas actuales del CSV de tickets **no se renombran ni se quitan** (`"Propiedad"` y `"Horas promedio resolución"` están fijadas por `tests/test_owner_portal.py:156`). Se **añade** una columna **Zona** y una fila de totales. De paso se elimina la clave muerta `"unit"` de `owner_portal.py:167`: evalúa `hasattr(p, "unit_label")` sobre una columna que `Property` no tiene, siempre vale `None`, y no se pinta en `owner_report.html` ni se escribe en el CSV.

### 6.2 CSV de cartera (`GET /owner?formato=csv`)

Una fila por propiedad: `id, título, zona, recámaras, m², estatus publicado, ocupación según contrato, inquilinos (n), tickets abiertos, emergencias, días del ticket abierto más antiguo, discrepancia (sí/no)`.

---

## 7. Rendimiento y presupuesto de consultas

**Presupuesto: ≤ 8 sentencias SQL por carga de `/owner`, constante en el número de propiedades, arrendamientos y tickets.** Hay una prueba que lo verifica (sección 9).

1. `owned_properties(db, user).order_by(Property.id).all()` — una sola vez: sirve a la tabla, al desplegable de zonas, al filtro de tamaño y a la detección de discrepancias. Con 3-7 filas reales cargarlas en memoria es correcto y es lo que hace viable la normalización de zona en Python (5.1).
2. Arrendamientos activos **por propiedad** (`GROUP BY property_id`, `status = active`, sobre los ids ya filtrados).
3. Inquilinos activos **globales** (`COUNT(DISTINCT tenant_id)`) — aparte, porque un inquilino con dos contratos en dos casas es **una** persona.
4. Tickets agregados (`GROUP BY property_id, status`) + `MIN(created_at)` de los no resueltos.
5. Mensajes sin leer (`COUNT`).

**Prohibido en este módulo:** `.all()` para contar. Hoy `pages.py:674` y `owner_portal.py:94` hidratan **todos** los tickets del propietario en objetos ORM en cada carga de página solo para contarlos. Se sustituye `_nav_badges` por un `func.count()` sobre `scoped_tickets`: es una línea y beneficia a las doce pantallas del portal.

**Prohibido también:** SQL crudo contra columnas de Enum. Se guardan como VARCHAR con el **nombre del miembro**; un `WHERE status='active'` escrito a mano funcionaría hoy y se rompería en silencio si alguien renombra un miembro. Comparar siempre con `LeaseStatusEnum` / `TicketStatusEnum` a través del ORM.

**Toda agregación arranca `FROM properties` acotada por scoping** y hace `LEFT JOIN` hacia fuera, nunca al revés: con `PRAGMA foreign_keys = 0` pueden existir arrendamientos o tickets huérfanos apuntando a propiedades borradas, y contarlos desde el otro lado daría ocupaciones superiores al 100 %.

**Disparador para revisar este diseño** (escrito para que nadie tenga que adivinarlo): ~500 propiedades o ~50.000 tickets por cuenta. Por debajo de eso, un caché o una tabla resumen sería más código del que ahorra y una fuente nueva de datos desincronizados.

---

## 8. Interfaz — pantallas, CSS y móvil

### 8.1 Pantallas

| Pantalla | Plantilla | Contenido |
|---|---|---|
| Panel del propietario | `owner_dashboard.html` (nuevo; `owner.html` se retira) | Franja de 4 fichas grandes + 4 pequeñas → bloque «Datos por revisar» → barra de filtros → tabla de cartera con casillas |
| Barra de filtros | `_owner_filtros.html` (parcial, `{% include %}`) | Compartida por panel, lista de tickets y reporte |
| Reporte por unidad | `owner_report.html` (existente, extendido) | + parcial de filtros arriba, + columna Zona, + fila de totales |
| Lista de tickets | `owner_tickets.html` (existente, extendido) | + parcial de filtros; conserva `?estado` y `?propiedad` por compatibilidad con `owner_tickets.html:12` |

Cada ficha **es un enlace** `<a class="kpi">` a la lista ya filtrada: en móvil la ficha es la navegación.

**Las fichas de KPI reflejan SIEMPRE la cartera completa, no el filtro.** Un KPI que cambia al filtrar no es un KPI, es una línea de reporte. Cuando hay un filtro activo se imprime debajo, en tono más discreto, «En la selección: X propiedades · Y ocupadas · Z tickets abiertos». Es una consulta más y elimina la ambigüedad de raíz.

Tres botones, un solo formulario, **cero JavaScript**:
- `<button type="submit">Filtrar</button>`
- `<button type="submit" name="formato" value="csv">Descargar CSV</button>`
- `<button type="submit" formaction="/owner/tickets/reporte">Ver reporte de tickets</button>` — en GET el navegador descarta el querystring del `action` y reconstruye la consulta con los campos del formulario, que es exactamente lo que se quiere.

**«Seleccionar todo» no se implementa como casilla maestra** (necesitaría JS): se implementa como `<button type="submit" name="alcance" value="filtro">Aplicar a todo el filtro</button>`, que además es lo que el propietario quiere de verdad y evita mandar 200 campos ocultos.

### 8.2 Estados vacíos — obligatorios

| Situación | Qué se imprime |
|---|---|
| 0 propiedades | Ocupación imprime **«—»**, nunca `0 %` y nunca una división por cero |
| Propiedades pero 0 arrendamientos (**estado real de `platform.db` hoy**) | «0 % · sin arrendamientos registrados» + enlace a dar de alta inquilinos |
| Columna de origen nula | **«sin datos»** en gris, **nunca 0** |
| `TENANT_MODULE_ENABLED = false` | Las fichas de personas dicen **«módulo desactivado»**, no 0. Un 0 haría creer al propietario que sus casas están vacías |

### 8.3 CSS (todo en `platform.css`, `style-src 'self'`)

> ⚠️ **CSP: cero JS en línea y cero `style=`.** `tests/test_ui.py:90-93` recorre `["/owner", "/owner/tickets", "/owner/inquilinos", "/sesiones"]` y falla si aparece `onsubmit=`, `onclick=` o `style="`.

Clases **nuevas**:
- `.kpi-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px }` — con `auto-fit` + `minmax` colapsa sola a 2 y a 1 columna **sin ninguna media query nueva**.
- `.kpi`, `.kpi-value` (con `font-variant-numeric: tabular-nums`), `.kpi-label`, `.kpi-note`, `.kpi-empty`
- `.table-wrap { overflow-x:auto }` + `@media (max-width:640px){ .col-sec { display:none } }`
- `.chips` / `.chip` (filtro activo en prosa)

Clases que **las plantillas YA usan y NO existen** en el CSS (verificado): **`.filters`** (`owner_tickets.html:6`) y **`.row-urgent`** (`owner_tickets.html:21`). Esa barra se está pintando sin estilo hoy. Definición mínima:

```css
.filters { display:flex; flex-wrap:wrap; gap:.5rem; align-items:flex-end }
@media (max-width: 640px) { .filters select, .filters .btn { width:100% } }
```

Se reutilizan tal cual `.card`, `table`, `.status-*`, `.badge`, `.btn`, `.flash-urgent` (`platform.css:501`), `.empty-row`, `.hint`, `.muted`. Se usan los tokens existentes (`--border`, `--sand`, `--teal-dark`, `platform.css:5-13`). **Rearmonizar la paleta con el Design System del sitio público es otro trabajo, de otra área.**

### 8.4 Móvil

Breakpoints existentes: 640 px (colapsa `.form-grid`, `platform.css:405-411`) y 860 px (barra lateral → cajón, `platform.css:556-565`). No se toca ninguno.

- La barra de filtros va dentro de `<details><summary>Filtros</summary>`: se colapsa en móvil **sin una línea de JavaScript**.
- La tabla se envuelve en `.table-wrap` con `overflow-x:auto` — hoy **no existe ninguna regla de tabla responsiva** y una tabla de 10 columnas desborda el `.container`.
- Precio, baños, m² y emergencias llevan `class="col-sec"` y se ocultan por debajo de 640 px. En el teléfono sobreviven Propiedad, Ocupación, Inquilinos y Tickets.
- Sin autoenvío al cambiar un select (necesitaría JS y en móvil es hostil): botón explícito.

Honestidad sobre el límite: si la cartera crece a 20+ casas habrá que rediseñar la tabla en tarjetas. `overflow-x` es una solución correcta, no elegante.

### 8.5 Etiquetas (D-014)

Módulo nuevo `app/labels_es.py` con diccionarios planos —`ESTADOS_PROPIEDAD`, `ESTADOS_TICKET`, `ESTADOS_CONTRATO`, `PRIORIDADES`, `KPI_LABELS`, `ENCABEZADOS_CSV`, `TEXTOS_VACIO`— registrados como global de Jinja `t` junto a `csrf_input` (`security.py:155-158`). Las plantillas solo interpolan claves: `{{ t.estado_propiedad[p.status.value] }}`.

Hoy los enum se imprimen **crudos en inglés en la cara del usuario**: `owner.html:31` pinta `{{ p.status.value }}` → «rented», y los tickets muestran «in_progress». Esto lo arregla y deja las cadenas fuera de la plantilla, listas para traducir, **sin construir i18n** y sin tocar las otras 26 plantillas.

**No se renombra ni un valor de enum**: se guardan como VARCHAR con el nombre del miembro y renombrarlos rompería la lectura del ORM sobre filas existentes.

> 🔗 **Cruce de áreas:** este diccionario es compartido. Las áreas de tickets, gastos y proveedores deben usarlo en vez de duplicarlo. El catálogo definitivo y su formato los fija el área de i18n; aquí solo se garantiza que nada quede incrustado en el HTML.

---

## 9. Migración

**Ninguna tabla nueva. Ninguna columna nueva. Ningún `ALTER TABLE`. Ningún miembro de Enum añadido ni renombrado. Cero filas migradas.** El panel es derivado: un despliegue no cambia ni un dato y volver atrás es revertir el commit.

Lo único que se paga son **índices**.

1. **Copia previa** de `data/platform.db` a `platform.db.bak-AAAAMMDD` si se va a arrancar contra la base real. Es la base con los propietarios reales del CEO. (Ya existen dos copias previas en `data/`, mismo patrón.)
2. Declarar `index=True` en `Lease.property_id` y `Lease.tenant_id` (`models.py:352-353`) para que una base **nueva** nazca con ellos.
3. Añadir a `main.py` una cuarta función idempotente **`_ensure_dashboard_indexes()`**, con el mismo molde que `_ensure_property_site_ref` (`main.py:132-146`): guarda `if not engine.url.get_backend_name().startswith("sqlite"): return`, comprueba que la tabla existe (`SELECT name FROM sqlite_master WHERE type='table' AND name=:t`) y dentro de `with engine.begin() as conn:` ejecuta los `CREATE INDEX IF NOT EXISTS`. `IF NOT EXISTS` ya es idempotente en SQLite.
4. Llamarla en el arranque (`main.py:222-230`) **después** de `Base.metadata.create_all()` y de las tres `_ensure_*` existentes, cuando las tablas y columnas ya están.

> ❗ **El paso 2 NO sustituye al paso 3.** `create_all()` **no altera tablas que ya existen**. Prueba verificada de que esto importa: `models.py:398` declara `index=True` en `maintenance_tickets.property_id` desde hace tiempo, y sin embargo `PRAGMA index_list('maintenance_tickets')` sobre `data/platform.db` devuelve **`[]`**, mientras que sobre `platform-mock.db` devuelve los tres índices. Declararlo en el modelo no basta.

### 9.1 Correcciones de hecho sobre las propuestas recibidas

| Afirmación de una propuesta | Realidad verificada |
|---|---|
| «En `platform.db` faltan `start_date`, `end_date`, `monthly_rent` y `status` en `leases`; sin `ALTER` el ORM revienta con "no such column"» | **Falso.** `PRAGMA table_info('leases')` sobre `data/platform.db` devuelve `['id','property_id','tenant_id','start_date','end_date','monthly_rent','status']`. La única ausente es `created_by_user_id`, y `main.py:214-221` ya la parchea al arrancar. Ese paso de migración sobra entero |
| «A `platform.db` le faltan 9 tablas» | Tiene **11** tablas; `platform-mock.db` tiene **19**. Le faltan **8** respecto de la mock: `ai_usage`, `announcements`, `announcement_recipients`, `messages`, `platform_settings`, `sessions`, `ticket_events`, `ticket_photos`. Las crea `create_all()` en el primer arranque. **Esta migración no es de esta área**, pero el panel no se puede dar por bueno contra la base real hasta que corra |
| «`Property.status` puede corregirse desde el portal» | Ninguna propuesta lo pedía, pero conviene fijarlo: **no**. `sync_site_properties` lo sobrescribe (`pages.py:636-640`) |

### 9.2 Índices

| Índice | Tabla | Columnas | Justificación |
|---|---|---|---|
| `ix_leases_property_status` | `leases` | `(property_id, status)` | Verificado: `PRAGMA index_list('leases')` = `[]` en **ambas** bases; `models.py:348-357` no declara ninguno. Sirve al `GROUP BY` de ocupación y, por prefijo izquierdo, a cualquier lookup por `property_id` |
| `ix_leases_tenant_status` | `leases` | `(tenant_id, status)` | KPI de inquilinos activos y `scoped_users` (`scoping.py:160-170`) |
| `ix_maintenance_tickets_property_id` | `maintenance_tickets` | `(property_id)` | **Existe en mock, NO existe en `platform.db`** pese a `models.py:398` |
| `ix_maintenance_tickets_reported_by_user_id` | `maintenance_tickets` | `(reported_by_user_id)` | Ídem, `models.py:399` |
| `ix_tickets_property_status` | `maintenance_tickets` | `(property_id, status)` | El reporte agrupa por (propiedad, estado); convierte el bucle `O(P×T)` de `owner_portal.py:150-176` en un `GROUP BY` |

**No se crea** `ix_properties_owner_status`: `owner_id` ya está indexado (`models.py:123`) y la cartera son 3-7 filas. **No se crea aquí** el índice único de `properties.site_ref` que le falta a `platform.db` (verificado: solo tiene `ix_properties_owner_id`): es deuda de la migración E1, de otra área; se anota, no se arregla de contrabando.

### 9.3 Orden de despliegue

Aplicar y verificar contra `platform-mock.db` (suite completa en verde) **antes** de arrancar con `DATA_MODE=live`. Reversión: quitar el código y, si se quiere, `DROP INDEX`. Los índices no cambian datos.

---

## 10. Puertas legales y banderas

**No se crea ninguna bandera nueva, y no hace falta ninguna.**

| Bandera / puerta | Estado en esta área | Razón |
|---|---|---|
| **`DATA_MODE` / D-016** | **No abre puerta nueva** | El panel es de solo lectura sobre filas que ya existen: no crea, no almacena ni un dato personal nuevo. No hay altas, así que `validate_mock_email`/`validate_mock_phone` ni se rozan. En live la app ya se niega a arrancar sin `LEGAL_CLEARANCE_REF` (`mockmode.py:61-78`) |
| **`TENANT_MODULE_ENABLED`** | Cambia el **pintado**, no el cálculo | Verificado: solo protege las rutas de `tenant.py`, **no** la creación de arrendamientos en `owner_portal.py:335`. Con la bandera apagada la ocupación se sigue calculando bien; lo que cambia es que las fichas de personas dicen «módulo desactivado» en vez de 0 |
| **`OWNER_PROPERTY_MANAGE_ENABLED`** | No aplica | El panel no da de alta ni de baja propiedades |
| **`PAYMENTS_MODULE_ENABLED`** | Irrelevante | El panel no muestra ni un peso cobrado ni contratado (4.5). El catch-all 501 de `payments.py:154-159` sigue intacto |
| **Planes (7.2)** | Un solo punto de contacto: `puede_exportar(user)`, hoy `True` | El plan vive en `accounts` (D-013), que define otra área. **No se usa `PlatformSetting`**: es clave/valor GLOBAL y no puede diferenciar cuentas |
| **D-013 (cuenta como raíz)** | Preparado, no implementado | Todo entra por `scoping.py`. **Prohibido escribir `Property.owner_id == user.id` a mano** en este módulo |

> ### 🔒 Puerta legal — la única superficie sensible de esta área es la EXPORTACIÓN
>
> El panel no almacena nada nuevo, pero un CSV es la vía más corta para que datos salgan del sistema. **Regla dura, no configurable: ningún reporte de esta área incluye nombre, correo, teléfono ni identificador de inquilino.** No es una bandera, es una prohibición estructural: esas columnas no aparecen en ninguna consulta de este módulo, ni siquiera en mock. Una prohibición estructural es más fiable que un parámetro.
>
> **Se rechaza explícitamente** la propuesta de incluir el nombre del inquilino en el CSV de cartera gateado por `tenant_module_enabled()`. D-016 es una puerta sobre el **almacenamiento** de datos reales de 2b/2c; **no es una autorización para abrir una vía de salida nueva**. Un reporte con identidad de inquilino, si el CEO lo quiere, es **otro entregable**, con su propia decisión del CEO y su propia revisión de Legal (CEO-D-10).
>
> Salvaguardas complementarias, todas dentro de esta entrega: tope de 2000 filas, cabecera de procedencia en el archivo, y una fila en `audit_log` por cada descarga (`security.audit()`, `security.py:486-507`).
>
> **Límite conocido:** `audit_log` lo escribe `security.audit()` pero **ninguna pantalla lo lee hoy**. El rastro existe y nadie lo mira. Una vista de bitácora es de otra área (CEO-D-08).

---

## 11. Riesgos aceptados

1. **Colisión silenciosa de rutas.** Si sobrevive `pages.py:658-704`, gana por orden de registro (`main.py:122` antes de `:124`) y el panel nuevo **no se ve nunca**, sin error ni traza. Es el riesgo número uno; mitigado con una prueba sobre `app.routes`.
2. **La ocupación saldrá 0 % el primer día.** `platform.db`: 3 propiedades, 0 arrendamientos. El cálculo no está mal; los contratos no se han cargado. Mitigado con el texto explícito «sin arrendamientos registrados». Es una subestimación **deliberada y conservadora**: esconder una vacante cuesta dinero, pero inventar un inquilino que no existe en ninguna fila es peor y no se puede auditar.
3. **Elegir el contrato descarta el conocimiento del admin.** Si el CEO marca una casa como `rented` en el sitio sin registrar el arrendamiento, el panel la contará vacía. Es deliberado y el aviso de discrepancia lo hace visible, pero **el propietario no puede arreglarlo por sí mismo** hasta que exista una pantalla de edición (CEO-D-03).
4. **Tres indicadores quedan en «sin datos» de forma permanente** —contratos por vencer, renta contratada, antigüedad del contrato— hasta que el alta de inquilino escriba `start_date`, `end_date` y `monthly_rent`. Esa captura vive en otra área. Sin ella el panel es honesto pero incompleto.
5. **La sincronización del sitio reasigna `owner_id`** (`pages.py:641-643`): una corrida puede mover propiedades de un propietario a otro y los KPIs cambiarán de golpe. El panel no lo causa, pero lo hace visible por primera vez.
6. **Sin integridad referencial** (`PRAGMA foreign_keys = 0`): pueden existir arrendamientos huérfanos o dos contratos activos sobre la misma casa. El diseño lo **absorbe** (todo por joins desde `properties`, `DISTINCT` en la ocupación, ocupación acotada a ≤ 100 %), pero no lo arregla: es deuda de plataforma.
7. **El aviso de discrepancia puede volverse ruido permanente** si el sitio público nunca se actualiza. Silenciarlo exigiría una columna nueva; se deja fuera a propósito y se revisa tras el primer mes de uso.
8. **Un enlace con filtros compartido por WhatsApp lleva ids de propiedad en la URL.** No es una fuga (otro usuario no pasa de scoping), pero **jamás debe meterse texto libre —zona ni título— en el querystring** de un enlace pensado para compartirse.
9. **Deuda ajena que condiciona la validación:** `platform.db` sigue sin migrar desde E1 (8 tablas y el índice único de `site_ref`). El panel funcionará igual, pero la base real no está en el estado que el código supone.

### 11.1 Trampas de regresión — leer antes de tocar la plantilla

| Prueba existente | Qué exige | Consecuencia |
|---|---|---|
| `tests/test_ui.py:90-93` | `/owner` sin `onclick=`, `onsubmit=` ni `style="` | La barra de filtros y las fichas deben ser HTML plano |
| `tests/test_ui.py:105` | `'class="actions">' not in body.split('<main')[1][:600]` | **No usar `class="actions"`** en la cabecera del panel nuevo |
| `tests/test_ui.py:102-104` | `/owner` con `class="sidebar"`, ≥3 `nav-group-title`, `is-active` | Conservar `active='owner'` en el contexto |
| `tests/test_inbox.py:94-96` | `/owner` debe renderizar `href="/owner/mensajes" … <span class="nav-badge">1</span>` | **El panel nuevo DEBE seguir inyectando `unread_messages`** (vía `_nav_badges`) |
| `tests/test_owner_portal.py:151-156` | El reporte carga con «Casa A», sin «Casa B», `text/csv`, encabezados «Propiedad» y «Horas promedio» | No renombrar ni quitar columnas del CSV; el BOM al inicio no rompe la comprobación de subcadena |

---

## 12. Handoff a Desarrollo

- [ ] `app/filtros_owner.py` — `clave_zona()`, `TRAMOS_M2`, `parsear_filtros(request)`, `aplicar_filtros(props, f)`, `resumen_filtro(f)`, `agregados(db, user, ids)`
- [ ] `app/labels_es.py` + registro como global `t` de Jinja
- [ ] `app/routers/owner_dashboard.py` — `GET /owner` (+ `?formato=csv`)
- [ ] **Borrar** `pages.py:658-704` (mismo commit)
- [ ] `main.py` — `include_router(owner_dashboard.router)` + `_ensure_dashboard_indexes()` llamada tras las tres `_ensure_*`
- [ ] `models.py:352-353` — `index=True` en `Lease.property_id` y `Lease.tenant_id`
- [ ] `owner_portal.py` — `_nav_badges` con `func.count()`; filtros compartidos en `GET /owner/tickets` y `GET /owner/tickets/reporte`; CSV endurecido (BOM, escape, procedencia, tope, `audit`); columna Zona; quitar la clave muerta `unit`
- [ ] Plantillas: `owner_dashboard.html` (nueva), `_owner_filtros.html` (nueva), `owner.html` (retirada), `owner_tickets.html` y `owner_report.html` (include del parcial)
- [ ] `base.html` — renombrar «Mis propiedades» → «Panel» si el CEO aprueba (CEO-D-07)
- [ ] `platform.css` — `.kpi-*`, `.filters`, `.row-urgent`, `.table-wrap`, `.col-sec`, `.chips/.chip`
- [ ] `tests/test_owner_dashboard.py` (nueva) + ampliar el bucle de `test_ui.py:90`

**Estado: 0 de 12 hechos.** Línea base a mantener: **261 pruebas en verde en 10 suites**. La suite nueva **debe imprimir su línea `RESULTADO: N pasaron, M fallaron`** — sin ella no suma al total, que es justo lo que le pasa hoy a `test_migrate.py`. Sin rutas absolutas de Windows. »
