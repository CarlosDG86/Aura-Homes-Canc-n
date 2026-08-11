# Phase 2 — Diseño funcional y técnico por módulo

**Fecha:** 2026-08-08 · **Estado:** diseño aprobado por el CEO en decisiones clave (ver §2), pendiente de construcción.
**Alcance:** este documento define QUÉ se construye y CÓMO. Complementa —no reemplaza— `PLAN.md`
(secuenciación 2a→2b→2c), `DB_SCHEMA.md` (borrador de esquema) e `INFRA_STACK.md` (stack).

> ⚠️ **Puerta legal (no negociable).** Este diseño incluye módulos 2b (inquilinos, tickets, PII) y
> parte de 2c. Según `CLAUDE.md`, se **construye ahora pero no se activa con datos reales** hasta que
> Legal firme y el CEO lo confirme por separado. Ver §9.

---

## 1. Arquitectura general

Dos superficies independientes, sin acoplamiento:

| Superficie | Qué es | Tecnología | Cambia en Phase 2 |
|---|---|---|---|
| **Sitio público** | Escaparate de propiedades, sin login | Estático (`build.py` → `dist/`) | Solo el encabezado: menú **"Ingresar"** (§3) |
| **Plataforma** | Gestión con login | FastAPI + SQLite + Jinja2 (`platform/`) | Todo lo demás |

El sitio público **sigue siendo estático y sin base de datos**. La plataforma vive en otro origen
(hoy `127.0.0.1:8010`; en producción un subdominio, p. ej. `app.aurahomescancun.com`). El único
vínculo es un enlace en el encabezado.

```
Visitante  ──►  sitio estático (dist/)  ──[enlace "Ingresar"]──►  plataforma (FastAPI)
                                                                     │
                                              ┌──────────────────────┼──────────────────────┐
                                           Admin                  Owner                 Inquilino
                                        (URL oculta)         (Google SSO)            (Google SSO)
```

---

## 2. Decisiones del CEO incorporadas (2026-08-08)

| # | Decisión | Consecuencia de diseño |
|---|---|---|
| 1 | **Google SSO + contraseña de respaldo** | OIDC con PKCE. Admin: URL oculta + 2FA obligatorio. Ver `SECURITY.md` |
| 2 | **Agente AI con Claude Haiku + visión** | `claude-haiku-4-5`. Ver `AI_TICKET_AGENT.md` |
| 3 | **Fotos en disco local junto a SQLite** | Re-codificadas, sin EXIF, servidas con autorización (no estáticas) |
| 4 | **Owner expone un número de contacto aparte** | `users.contact_phone` ≠ `users.phone` (personal) |

---

## 3. Módulo 0 — Accesos desde el sitio público

### 3.1 Cambio en el encabezado

Hoy el encabezado muestra un enlace directo **"Administración"** (`site.json → ui.*.admin_login`)
que apunta a la plataforma. **Se elimina** y se sustituye por un desplegable:

```
┌─ Ingresar ▾ ─────────────┐      (EN: "Log in")
│  Soy Propietario         │  →  /acceso/propietarios
│  Soy Inquilino           │  →  /acceso/inquilinos
└──────────────────────────┘
```

- Bilingüe obligatorio (ES/EN), ambas cadenas en `data/site.json`.
- Accesible por teclado (`Enter`/`Espacio` abre, `Esc` cierra, `Tab` recorre, `aria-expanded`).
- Sin JS framework: `<details>`/`<summary>` o el `app.js` existente.
- **El acceso de Admin desaparece del sitio público.** No hay enlace, ni en el pie, ni en `sitemap`.

### 3.2 URL oculta de Admin

- Ruta configurable por entorno: `ADMIN_LOGIN_PATH` (p. ej. `/gestion-interna-a7f3c1`).
- No enlazada en ninguna parte, `X-Robots-Tag: noindex, nofollow`, fuera de `sitemap.xml`.
- Es **ofuscación, no seguridad**: la protección real es 2FA + límite de intentos + lista de IP
  opcional (ver `SECURITY.md §4`). Una URL oculta sin 2FA no protege nada.

---

## 4. Roles y reglas de acceso

| Capacidad | Admin | Owner | Inquilino |
|---|:--:|:--:|:--:|
| Alta/baja de **propiedades** | ✅ | 🚩 (según bandera) | ❌ |
| Editar campos descriptivos de propiedad | ✅ | ✅ (solo suyas) | ❌ |
| Verificar "cumple requisitos" | ✅ | ❌ | ❌ |
| Alta de **owners** | ✅ | ❌ | ❌ |
| Alta de **inquilinos** y vínculo a propiedad | ✅ | ✅ (solo suyas) | ❌ |
| Ver tickets | todos | de sus propiedades | los suyos |
| Crear ticket | ✅ | ✅ | ✅ (vía agente AI) |
| Resolver ticket | ✅ | ✅ | ❌ |
| Comunicados | ✅ | ✅ (a sus inquilinos) | ❌ |
| Mensajes 1:1 | ✅ | ✅ | ✅ (a su owner) |
| Editar datos propios | ✅ | ✅ | ✅ |
| Bitácora de auditoría | ✅ | ❌ | ❌ |

> **✅ Resuelto por el CEO (2026-08-08): el módulo Owner se conserva, con bandera.**
> El alta/baja de propiedades por parte del owner **no se elimina**; queda tras
> `OWNER_PROPERTY_MANAGE_ENABLED`. Con la bandera encendida el owner administra sus propiedades como
> hoy; apagada, el módulo desaparece de su interfaz y solo el Admin da de alta (el criterio de
> "cumple requisitos"). El CEO cambia el modo sin tocar código ni redesplegar.
>
> **La bandera se aplica en dos capas, no en una.** Ocultar el botón no es seguridad: si la bandera
> está apagada, las rutas `POST /owner/propiedades` y `DELETE` deben responder **403 en el
> servidor**, aunque alguien construya la petición a mano. Una bandera que solo esconde la interfaz
> es una falsa protección.

**Regla de oro de autorización:** el rol nunca basta. Toda consulta se filtra además por pertenencia
(`Property.owner_id == user.id`, `Lease.tenant_id == user.id`). Un owner con el ID de una propiedad
ajena debe recibir **404**, no 403 (no confirmar la existencia del objeto).

---

## 5. Módulo Owner

### 5.1 Registro del owner en base de datos
El owner **es** un registro en `users` con `role='owner'`. Lo crea el Admin (ya existe en 2a:
`POST /admin/owners`) y recibe por correo una clave temporal de un solo uso; al activarla elige
contraseña o vincula su cuenta de Google.

### 5.2 Alta de inquilinos y vínculo con propiedades
- `POST /owner/inquilinos` → crea `users` con `role='tenant'`, `created_by_user_id = owner.id`.
- El vínculo inquilino↔propiedad es una fila en **`leases`** (arrendamiento): `property_id`,
  `tenant_id`, fechas, renta, estado.
- **Restricción dura:** el `property_id` debe pertenecer al owner. Se valida en servidor, no en el
  formulario. Un inquilino puede tener varios arrendamientos históricos; solo uno `active` por unidad.
- Correo de invitación con enlace de activación de un solo uso (24 h de vigencia).

### 5.3 Tickets de mantenimiento
- Listado filtrable por propiedad, unidad, estado, prioridad, categoría y rango de fechas.
- Detalle con hilo cronológico (`ticket_events`): comentarios, cambios de estado, fotos.
- Acciones: comentar, asignar (`assigned_to_user_id`), cambiar estado, **resolver** (exige
  `resolution_notes`), reabrir.
- Estados: `open → in_progress → resolved` (+ `reopened` como evento, vuelve a `open`).

### 5.4 Reporte de tickets por unidad
`GET /owner/tickets/reporte` — por cada propiedad/unidad:
conteo por estado, por categoría, por prioridad; tiempo medio de resolución; tickets reabiertos;
top de categorías recurrentes (señal de problema estructural). Exportable a CSV.

### 5.5 Comunicados
- `POST /owner/comunicados` con audiencia: **todos mis inquilinos** / **una propiedad** / **selección**.
- Canales: **bandeja de entrada** (siempre) + **correo** (casilla opcional).
- Se materializa un `announcement_recipients` por destinatario para poder mostrar entregado/leído.
- El envío de correo es asíncrono y tolerante a fallos: si SMTP falla, el comunicado ya está en la
  bandeja y se marca `delivered_email_at = NULL` para reintento.

### 5.6 Mensajes 1:1
Hilos owner↔inquilino dentro de la app (`messages`). Notificación por correo opcional.

---

## 6. Módulo Inquilino

- **Levantar tickets con fotos** mediante el agente AI (ver `AI_TICKET_AGENT.md`). Siempre existe un
  **formulario manual de respaldo** si el agente falla o se agota el presupuesto.
- **Contactar al owner:**
  - Bandeja interna (queda registrado — es la vía recomendada para disputas).
  - Correo: `mailto:` al owner.
  - WhatsApp: `https://wa.me/<owner.contact_phone>` con mensaje prellenado.
    **Se usa `contact_phone`, nunca `phone`.** Si el owner no lo capturó, el botón no se muestra.
- **Editar sus datos:** nombre, teléfono, idioma, contraseña, cuenta de Google vinculada.
  **No** puede cambiar su correo de acceso sin verificación (vector de secuestro de cuenta).

---

## 7. Cambios de esquema

Sobre lo que ya existe en `platform/app/models.py`.

### 7.1 `users` — columnas nuevas
| Columna | Tipo | Para qué |
|---|---|---|
| `auth_provider` | enum(`password`,`google`) | Cómo entra |
| `google_sub` | varchar UNIQUE NULL | ID estable de Google (`sub`). **Nunca vincular por correo solo** |
| `contact_phone` | varchar NULL | Número que ve el inquilino (owner) |
| `is_active` | bool | Desactivar sin borrar (preserva historial) |
| `must_change_password` | bool | Tras clave temporal |
| `last_login_at`, `failed_login_count`, `locked_until` | — | Antifuerza bruta |
| `totp_secret`, `totp_enabled` | varchar / bool | 2FA (obligatorio en admin) |
| `locale` | varchar(2) | `es`/`en` |
| `created_by_user_id` | FK users NULL | Quién dio de alta a este usuario |

### 7.2 `properties` — columnas nuevas
`unit_label` (unidad/depto), `created_by_user_id`, `requirements_verified_at`,
`requirements_notes` (la verificación de requisitos que exige el CEO).

### 7.3 `leases` — reutilizada como vínculo inquilino↔propiedad
Añadir `created_by_user_id`. Ya tiene `property_id`, `tenant_id`, fechas, renta, estado.

### 7.4 `maintenance_tickets` — columnas nuevas
`public_ref` (`TCK-2026-0001`), `lease_id`, `category`, `priority`, `location_in_unit`,
`created_via` (`ai_agent`|`form`|`staff`), `assigned_to_user_id`, `resolved_at`,
`resolution_notes`, `ai_summary`, `ai_confidence`.

### 7.5 Tablas nuevas
| Tabla | Para qué |
|---|---|
| `ticket_photos` | Fotos: ruta, miniatura, hash, tamaño, quién subió, EXIF eliminado |
| `ticket_events` | Historial: creación, comentarios, cambios de estado, asignaciones |
| `messages` | Hilos 1:1 owner↔inquilino |
| `announcements` + `announcement_recipients` | Comunicados y su entrega/lectura |
| `notifications` | Campanita: aviso corto con enlace |
| `sessions` | Sesión con revocación server-side (ver `SECURITY.md §3`) |
| `audit_log` | Quién hizo qué, cuándo, desde qué IP |
| `login_attempts` | Límite de intentos y detección de ataques |
| `ai_usage` | Tokens y costo por ticket → tope de presupuesto |

> Sin Alembic en el MVP: las migraciones se aplican con funciones idempotentes tipo
> `_ensure_property_site_ref()` (patrón ya usado en `main.py`). Si el número de cambios crece,
> incorporar Alembic antes de 2c.

---

## 8. Mapa de rutas

**Autenticación**
```
GET/POST  /acceso/propietarios          Login owner (correo+contraseña)
GET/POST  /acceso/inquilinos            Login inquilino
GET       /auth/google/start            Inicia OIDC (state+PKCE+nonce)
GET       /auth/google/callback         Retorno OIDC
GET/POST  /{ADMIN_LOGIN_PATH}           Login admin (oculto)
POST      /{ADMIN_LOGIN_PATH}/2fa       Segundo factor TOTP
GET/POST  /activar/{token}              Activación de cuenta / clave temporal
GET/POST  /recuperar                    Recuperación de contraseña
POST      /logout
```

**Admin** — `/admin`, `/admin/propiedades[/nueva|/{id}]`, `/admin/owners`, `/admin/usuarios/{id}`,
`/admin/auditoria`, `/admin/ai-uso`, `/admin/sync-site-properties`,
`/admin/pagos/metodos`, `/admin/pagos/requisitos` (submenú Pagos, §9.2),
`/admin/mock/purgar` (solo con `DATA_MODE=mock`)

**Owner** — `/owner`, `/owner/propiedades`, `/owner/inquilinos`, `/owner/tickets[/{id}]`,
`/owner/tickets/reporte`, `/owner/comunicados`, `/owner/mensajes`

**Inquilino** — `/inquilino`, `/inquilino/tickets[/nuevo|/{id}]`, `/inquilino/mensajes`,
`/inquilino/perfil`

**Medios protegidos** — `GET /media/tickets/{ticket_id}/{photo_id}`
Sirve la foto **solo** si el solicitante es el inquilino autor, el owner de esa propiedad o un admin.
**Nunca** un `StaticFiles` público: son datos personales.

---

## 9. Puertas legales y de activación

**Decisión del CEO (2026-08-08):** 2b se enciende **ya, en modo simulación (mock)** para poder
probar. Legal se incorpora después. Nada de datos reales mientras tanto.

| Módulo | Estado | Bandera | Nota |
|---|---|---|---|
| 2a Admin/Owner/Propiedades | Productivo, datos reales | `OWNER_PROPERTY_MANAGE_ENABLED` | Bandera solo decide si el owner administra propiedades |
| **2b Inquilinos + tickets + AI** | **Encendido en modo mock** | `TENANT_MODULE_ENABLED=true` + `DATA_MODE=mock` | Solo datos ficticios |
| **2c Pagos** | Conexiones y requisitos en submenú de Admin | `PAYMENTS_MODULE_ENABLED=false` | Se configura, no se cobra |

### 9.1 `DATA_MODE=mock` — cómo se garantiza que no entren datos reales

"Modo de pruebas" no puede ser una promesa: se hace cumplir por código.

1. **Base de datos aparte.** En modo mock la app usa `platform/data/platform-mock.db`, **nunca**
   `platform.db`. Este es el punto más importante: `platform.db` contiene los propietarios reales
   del CEO. Si los inquilinos de prueba se guardaran ahí, quedarían mezclados con datos reales y
   separarlos después sería un trabajo manual y arriesgado.
2. **Validación de altas.** Con `DATA_MODE=mock`, crear un inquilino exige correo en un dominio de
   prueba (`@example.com`, `@test.local`) y teléfono del rango reservado `+52 555 01xx xxxx`. Un
   correo real es rechazado con un mensaje claro.
3. **Marca visible.** Banda permanente en la interfaz: **"MODO PRUEBAS — datos ficticios"**, para
   que nadie capture un inquilino real por descuido.
4. **Sin correos al exterior.** El mailer queda en modo desarrollo: registra en consola, no envía.
   Ningún inquilino ficticio recibe correo, ningún correo real sale por error.
5. **Sin WhatsApp real.** Los enlaces `wa.me` se muestran deshabilitados.
6. **Purga en un paso.** `POST /admin/mock/purgar` borra todos los datos de simulación. Al pasar a
   producción se empieza limpio, no se depura a mano.
7. **El cambio a real es explícito.** Poner `DATA_MODE=live` exige además `LEGAL_CLEARANCE_REF`
   (referencia del documento de Legal). Sin él, la app **no arranca** en modo real.

> Con esto, "agregaré Legal después" no es un riesgo abierto: mientras no exista esa referencia, el
> sistema es físicamente incapaz de guardar datos personales reales de inquilinos.

### 9.2 Método de pago (2c) — submenú de Admin

Se construyen **las conexiones y los requisitos**, no el cobro:
`/admin/pagos/metodos` (configurar cuentas, referencias, instrucciones de pago),
`/admin/pagos/requisitos` (lista de lo que Legal y el proveedor exigirán).
No se procesa ni se almacena ningún dato de tarjeta. `PAYMENTS_MODULE_ENABLED=false` mantiene
cerradas las rutas de cobro; el submenú es solo configuración previa.

**Para Legal (lista de encargados de tratamiento):** Google (identidad), proveedor SMTP (correo),
**Anthropic (procesa el texto y las fotos de los tickets)**. Los tres deben aparecer en el aviso de
privacidad antes de operar con datos reales.

---

## 10. Riesgos abiertos

| Riesgo | Mitigación |
|---|---|
| SQLite + disco efímero en hosting gratuito | Fly.io con volumen persistente + respaldo cifrado fuera del host (`INFRA_STACK.md §5`) |
| Fotos llenan el volumen (1–3 GB) | Re-codificar a máx. 1600 px, tope 5 fotos/ticket y 8 MB c/u, alerta al 70 % |
| Costo del agente AI sin control | Tope mensual en `ai_usage`; al superarlo, formulario manual |
| Número de WhatsApp del owner mal usado | `contact_phone` separado + opción de ocultarlo |
| Fuga entre owners (el riesgo #1) | Filtrado por pertenencia en toda consulta + pruebas de QA dedicadas |
| Datos reales capturados en modo pruebas | Base separada + validación de dominio + banda visible (§9.1) |

## 11. Hallazgo del grafo de conocimiento — `Property.owner_id` sobrecargada

El análisis con Graphify (2026-08-08) mostró que `properties` es el nodo con más conexiones
transversales del sistema, y que **`Property.owner_id` carga tres responsabilidades sin relación**:

1. **Control de acceso** — `Scoping del owner` la usa para decidir qué ve cada propietario.
2. **Enrutamiento** — la cadena `Ticket → Property.owner_id → User(owner)` entrega los tickets.
3. **Espejo público** — `site_ref` sincroniza con el sitio estático.

Además, dos formularios (`POST /admin/sync-site-properties` y el de reasignación de casas)
escriben en esa tabla **sin protección CSRF**.

**Consecuencia:** un error en `owner_id` no produce un fallo, produce dos a la vez — fuga de datos
entre propietarios **y** tickets entregados al dueño equivocado.

**Reglas que se derivan (obligatorias):**
- `owner_id` **nunca** se toma de un campo del formulario. Solo cambia por una acción explícita de
  Admin, registrada en `audit_log`.
- Reasignar una propiedad **debe revisar los tickets abiertos** de esa propiedad: o se reasignan
  también, o se marcan para revisión. Si no, quedan apuntando al propietario anterior.
- La sincronización con el sitio público **tiene prohibido escribir `owner_id`**. Solo toca campos
  descriptivos y `site_ref`.
- Estos tres formularios encabezan la lista de CSRF (etapa E1 en el handoff de Dev).
