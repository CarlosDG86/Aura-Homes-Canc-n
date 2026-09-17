# Pendientes — prioridades para la próxima sesión

**Actualizado:** 2026-09-16
**Estado general:** desarrollo local. La Fase 2.1 está **construida (E8–E14)** en la rama `work/feedback-usuarios`, sin publicar.

---

## 0. Contexto: qué está arriba y qué no

| | Estado |
|---|---|
| Sitio público (Cloudflare Worker `aura-homes-cancun`) | 🟢 Arriba — verificado HTTP 200 el 2026-09-08 |
| Plataforma (Fly `aura-homes-plataforma`) | 🔴 **No responde** — verificado HTTP 000 el 2026-09-08 |
| Respaldos automáticos | ⚫ Cancelados por el CEO |
| Rama de trabajo | `work/feedback-usuarios`, creada desde `main` |

> ⚠️ Un `push` a `main` **republica el sitio público**: Cloudflare está conectado al
> repositorio. Para trabajar sin publicar, usar una rama.

> ⚠️ La rama `docs/architecture-and-phase2` está **9 commits atrasada y no contiene la suite de
> pruebas**. No trabajar ahí.

---

## 1. Prioridad alta

### 1.1 ~~El agujero de acceso por la API~~ — etapa E8 ✅ HECHA (2026-09-08)

Las tres rutas de `/api/auth/*` quedan retiradas tras `LEGACY_JSON_AUTH_ENABLED`
(apagada por omisión) y devuelven 404. La resolución de sesión vive ahora en una sola
función, `security.resolve_session_user`, que usan tanto las páginas HTML como la API.

Verificado: las dos pruebas de concepto que demostraron el agujero ya no lo reproducen, y
`tests/test_e8.py` añade **22 comprobaciones** que lo mantienen cerrado — incluida la que
antes fallaba en silencio: *revocar la sesión ahora sí cierra la API*.

Detalle y evidencia: [`docs/phase2.1/HALLAZGOS_SEGURIDAD.md`](phase2.1/HALLAZGOS_SEGURIDAD.md).

### 1.1b ~~E9 — cuentas, aislamiento y migración~~ ✅ HECHA (2026-09-08)

Tablas `accounts` y `account_plan_events`, `users.account_id`, `properties.account_id`,
migración con relleno idempotente, matriz de planes (D-018) y escritor único de cuenta.

`scoping.py` **no cambió de predicado**, a propósito: un `account_id` en NULL cae en la
rama heredada, que es más estrecha. `test_scoping.py` se ejecuta sin tocar una línea y
mantiene sus 27 comprobaciones — el contrato de la etapa.

Ensayo en seco contra la base real: pasa dos veces con diff vacío la segunda, y el hash
del archivo original queda idéntico. Ejecutarlo antes de cualquier arranque real:

```
cd platform && python -m app.migrate --simular
```

> ⚠️ El primer arranque contra `platform.db` **no es «añadir account_id»**: descarga de
> golpe la deuda de E1 y E5 — 8 tablas, ~19 columnas y 20 índices. Ese es el momento
> delicado, no la migración de cuentas. Hacer la instantánea antes.

### 1.1c ~~E10 — recuperación de contraseña y ver contraseña~~ ✅ HECHA (2026-09-15)

Nueve rutas de recuperación, botón «ver contraseña» en cinco pantallas, buzón de salida,
mínimo de contraseña unificado en 12, obligación de cambiar la clave temporal (D-030a) y
`scripts/restablecer_admin.py` como vía de rescate del administrador (D-022).

**El hallazgo H-2 queda cerrado**: la guarda del modo simulación vive ahora dentro de
`email_utils`. Ya se puede configurar el SMTP de producción sin riesgo de que salga una
contraseña en claro desde el modo de pruebas.

### 1.1d ~~E11 — panel del propietario, filtros y reportes~~ ✅ HECHA (2026-09-16)

Ocho indicadores (los cuatro del CEO más cuatro de salud operativa), cada uno con su
definición impresa debajo; bloque «Datos por revisar»; filtros por zona, recámaras,
tamaño y ocupación; selección efímera por URL; y descarga de la cartera en CSV.

**Ocupación = contratos vigentes ÷ total**, no el estatus publicado. Ese estatus lo
sobrescribe la sincronización del sitio en cada corrida y el propietario no tiene ninguna
pantalla para cambiarlo: un indicador que su dueño no puede mover no es un indicador.
Cuando los dos no coinciden, el panel **avisa y no reconcilia** — escribir `status` desde
aquí lo revertiría la siguiente sincronización.

El panel **no escribe ni una fila** y **ningún CSV lleva datos del inquilino**. Las dos
cosas tienen prueba.

### 1.1e ~~E12 — proveedores, archivos de ticket y cámara en móvil~~ ✅ HECHA (2026-09-16)

Directorio de proveedores con alta, archivado, borrado y supresión de contacto; asignación
a tickets; fotos del trabajo y del cierre con la cámara del teléfono; y comprobantes en
PDF, XML, JPG o PNG.

El proveedor es **un dato de la cuenta, nunca una fila en `users`**: `users.email` es único
global, así que dos administradoras no podrían registrar al mismo plomero.

**El inquilino no ve ningún comprobante**, ni de su propia vivienda. Ve las fotos del
trabajo terminado; lo que costó y a quién se le pagó es asunto del propietario.

### 1.1f ~~E13 — gastos desglosados y libro fiscal~~ ✅ HECHA (2026-09-16)

Catálogo de 15 categorías con doble mapeo SAT / IRS Schedule E, libro de gastos por
propiedad y por ticket, tipos de cambio manuales, cierre y reapertura de año fiscal, y
reporte CSV.

**Regla que gobierna todo:** sin tipo de cambio, el importe convertido queda **vacío y no
suma**. No se inventa una conversión. Un reporte visiblemente incompleto es mejor que uno
silenciosamente falso, porque el segundo se entrega sin que nadie lo revise.

Un gasto **no se borra: se anula con motivo**. Borrar la fila destruiría la constancia de
que existió, que es justo lo que un auditor viene a revisar.

**Pendiente de D-027:** el texto del descargo legal está escrito y en pantalla, pero espera
la aprobación del CEO y la revisión de su abogado.

### 1.1g ~~E14 — paquete para el contador, cotizaciones y planes con efecto~~ ✅ HECHA (2026-09-16)

**Paquete fiscal (D-015, la «Auditors View»).** Un ZIP por año y por casa o por cuenta con
`gastos.csv`, `resumen_por_categoria.csv` (SAT e IRS lado a lado), `tickets.csv`, los
comprobantes originales, `MANIFIESTO.json`, `LEEME.txt` y `SHA256SUMS.txt`. Se escribe a
disco (`data/exports-mock/` o `data/exports/`), nunca se arma en memoria, y tiene tope de
tamaño (`EXPORT_MAX_BYTES`, 200 MB).

- **Pantalla intermedia obligatoria**: un POST sin confirmar vuelve a ella.
- **Fotos del interior fuera por omisión.** La casilla nace desmarcada y, si se marca, queda
  en `fiscal_exports.includes_ticket_photos` y con registro propio en la bitácora.
- **El inquilino sale como «Inquilino #contrato».** La prueba busca su nombre, correo y
  teléfono en todos los archivos de texto del ZIP. Tampoco sale la descripción del ticket:
  es texto libre y ahí aparece de todo.
- En modo pruebas el nombre del ZIP y el `LEEME` dicen `DATOS-DE-PRUEBA`, y las filas
  nacidas en otro modo se excluyen y se cuentan.

**Cotizaciones manuales** en la ficha del ticket: registrar, aprobar, rechazar. Aprobar solo
sella el estado — ver D-017 en el registro de decisiones. La automática responde 403 sin
plan Enterprise+ y 501 con él.

**Planes con efecto** (D-018):

| Situación | Qué se bloquea | Qué NO se bloquea nunca |
|---|---|---|
| Casas por encima del límite | Dar de alta otra casa (409), en las tres puertas | Leer, reportes, tickets |
| Prueba vencida o cuenta suspendida | Altas de casa, inquilino, proveedor, gasto y cotización (403) | Leer, resolver tickets, descargar y generar el paquete fiscal, **que un inquilino reporte una avería** |

- El reloj de 90 días arranca al dar de alta la **primera casa**, no al crear la cuenta.
- `PLAN_LIMITS_ENFORCED=false` apaga los bloqueos comerciales (nunca el aislamiento) y deja
  una fila en la bitácora por cada alta que habría bloqueado.
- **«Plan y cuenta»** (`/owner/cuenta`): plan, uso frente al límite, días de prueba y qué
  pasa al terminar. Sin precios.
- **«Cuentas y planes»** (`/admin/cuentas`): único escritor de `accounts.plan`, con nota
  obligatoria y evento en el historial. Extender la prueba solo hacia adelante y hasta 180 días.

> ⚠️ **Un propietario dado de alta desde ahora nace en prueba, con una sola casa.** Para darle
> más, hay que asignarle plan en «Cuentas y planes». Los propietarios que ya existían quedaron
> en `enterprise_plus` sin reloj (D-020) y no notan nada.

**Lo que quedó fuera de E14**, del diseño del área A: alta de cuentas vacías, mover usuarios
entre cuentas, transferir casas entre cuentas desde pantalla, «solicitar cambio de plan» y la
banda de aviso en todas las páginas.

`tests/test_e14.py`: 139 comprobaciones. Suite completa: **712 en 17 suites**. Ensayo de
migración contra la base real: pasa, idempotente, hash del original sin cambios.

**Con E14 termina la construcción de la Fase 2.1.** Lo que queda son decisiones del CEO
(D-017, D-025 a D-030) y dependencias externas (correo, Legal).

### 1.2 El sitio público enlaza a un host caído

El menú «Ingresar» ofrece «Soy Propietario» y «Soy Inquilino» en **22 páginas**, y ambos apuntan
a la plataforma de Fly, que no responde. Quien pulse recibe un error del navegador.

Arreglo: cambiar `data/site.json` y reconstruir. **Requiere aprobación: republica el sitio.**

### 1.3 Cinco decisiones del CEO bloquean cuatro etapas

[`docs/phase2.1/DECISIONES_PENDIENTES.md`](phase2.1/DECISIONES_PENDIENTES.md).

Las dos con más efecto por unidad de esfuerzo:
- **D-024** — cargar los contratos de arrendamiento. Hoy hay 3 propiedades y **0 arrendamientos**;
  sin ellos el panel del punto 2.1 dirá «Ocupación 0 %».
- **D-023** — buzón de correo de producción. Única dependencia externa; su plazo no lo controla
  Desarrollo.

### 1.4 El correo del sitio no existe

Sin cambios desde agosto. `hola@aurahomescancun.com` aparece en el pie de todas las páginas y el
dominio no está registrado. Ahora bloquea además el punto 3.2 de la Fase 2.1: el mismo registro
resuelve las dos cosas.

---

## 2. Prioridad media

### 2.1 El modo simulación no bloquea el correo en todas las rutas

Se puede enviar una contraseña **en claro** a una dirección real. Lo único que lo detiene hoy es
que `SMTP_PASSWORD` está vacío. **Se activa al construir el punto 3.2.** Se corrige en E10.

### 2.2 CI: las pruebas no corren solas

El paso «Suite completa» se retiró del flujo de despliegue, y `test_migrate.py` conserva rutas
absolutas de Windows que revientan en Linux. Además esa suite no imprime la línea `RESULTADO:`,
así que sus 7 comprobaciones no suman al total.

A mano: `cd platform && python tests/run_all.py`

### 2.3 Seis de siete fichas no son inventario real

Sin cambios. `build.py` ya respeta un campo `placeholder` para ocultarlas sin borrarlas.

### 2.4 Aviso de privacidad y términos

Ambas páginas dicen que el texto «se publicará muy pronto» mientras el formulario ya pide nombre,
correo y teléfono. Depende del texto de Legal.

### 2.5 Lighthouse nunca se ha medido

El plan pide 90+ en móvil. Se quitaron los frenos evidentes, pero eso no es haberlo comprobado.

---

## 3. Prioridad baja

- Nueve clases de CSS que las plantillas usan **no existen** en `platform.css` (incluida
  `.btn-danger`, que viste acciones destructivas).
- La plataforma no sigue el sistema visual del sitio público, y es el producto que se va a vender.
- Tres archivos de logo conviviendo: `logo.png`, `logo1.png`, `logoold.png`.
- `banner.jpg` pesa 280 KB.
- Agente de IA de tickets: construido y probado, desconectado, sin llave de API.
- Google SSO: construido y probado, sin credenciales.
- `CLAUDE.md` describe un producto que ya no es el que se construye (dice «no user accounts, no
  payments» y «Next.js»). No se tocó: su sección de producto requiere aprobación del CEO.

---

## 4. Cómo retomar en local

Dos terminales, desde `C:\Aura\claude-code`:

```
cd platform && .venv\Scripts\Activate.ps1 && uvicorn app.main:app --reload --port 8010
```

```
python build.py --serve
```

- Plataforma: `http://127.0.0.1:8010` — usa `data/platform-mock.db` (`DATA_MODE` por defecto es
  `mock`), sin segundo factor.
- Sitio: `http://localhost:8000/es/`

**Acceso:** el usuario admin es `admin@aura-homes-cancun.local`. La contraseña **no es la de
siembra** — se cambió y bcrypt no permite recuperarla. Para poner una nueva:

```
cd platform && python scripts/reset_local_password.py admin@aura-homes-cancun.local
```

La pide por teclado (no se muestra ni queda en el historial) y hace una copia de la base antes
de escribir.

---

## 5. Documentación de referencia

| Tema | Archivo |
|---|---|
| **Fase 2.1 — índice** | `docs/phase2.1/README.md` |
| Plan y secuencia de entrega | `docs/phase2.1/PLAN.md` |
| Esquema y migración | `docs/phase2.1/DB_SCHEMA.md` |
| Decisiones abiertas | `docs/phase2.1/DECISIONES_PENDIENTES.md` |
| Hallazgos de seguridad | `docs/phase2.1/HALLAZGOS_SEGURIDAD.md` |
| **Registro de decisiones** | `docs/decisions/DECISION_LOG.md` |
| Diseño de la Fase 2 (anterior) | `docs/phase2/DESIGN.md` |
| Seguridad | `docs/phase2/SECURITY.md` |
| Despliegue | `docs/phase2/DEPLOY.md` |
| Reportes por departamento | `docs/reports/` y Google Drive `Aura/Reports/` |
| Grafo de conocimiento | `graphify-out/graph.html` (943 nodos) |
