<!-- Generado por el panel de diseño del 2026-09-08. Ganadora: Puerta única de acceso: un solo camino de autenticación, recuperación con token hasheado y correo observable (ángulo producto) -->

# Área E · Acceso: ver contraseña, recuperación y cierre del agujero de `/api/auth`

**Fecha:** 2026-09-08 · **Estado:** diseño cerrado, listo para construir · **Depende de:** ninguna otra área (es la base sobre la que se apoyan todas)

---

## 0. Corrección de hechos previa

Las tres propuestas recibidas comparten o arrastran errores de hecho. Se corrigen aquí porque cambian el diseño:

1. **El agujero de `/api/auth/login` es peor de lo que se describió.** Se contó como «se puede entrar de administrador saltándose el segundo factor», que es cierto pero exige ya conocer la contraseña. Lo grave es lo otro: `auth.py:64-71` no llama a `ip_is_rate_limited` ni a `register_failed_login` ni a `audit`. Es decir, es un **oráculo de adivinación de contraseñas sin freno, sin bloqueo y sin rastro** contra cualquier cuenta: los fallos no incrementan `failed_login_count`, no fijan `locked_until`, no aparecen en `login_attempts` y no aparecen en `audit_log`. Eso es lo que permite *encontrar* la contraseña que después el mismo endpoint usa para saltarse el TOTP. La prioridad de cierre es alta por esto, no por el 2FA.
2. **El CSRF sí se aplica a `/api/auth/login`.** `CSRF_EXEMPT_PATHS` contiene únicamente `/api/health` (security.py:40-42) y el middleware exige el token en todo POST (security.py:181). No es una protección real —el atacante hace un GET a cualquier página, lee su propio token de sesión y lo manda en `x-csrf-token`— pero sí es prueba de que ningún cliente ingenuo está usando ese endpoint hoy.
3. **La guarda de simulación del correo no está donde se dijo.** `owner_portal.py:342` sí consulta `emails_are_sent()`; **`pages.py:827-828` no lo hace**. Con `SMTP_HOST` configurado, la plataforma en modo pruebas envía hoy un correo real con una contraseña en claro. La guarda tiene que vivir dentro de `email_utils`, no en los llamadores.
4. **`test_ui.py` no revisa hoy `/login`.** El bucle que busca código en línea (test_ui.py:90-93) recorre `/owner`, `/owner/tickets`, `/owner/inquilinos` y `/sesiones`. `/login` solo se pide en la línea 82 para leer la CSP. Añadir las pantallas nuevas a esa lista es trabajo obligatorio, no un beneficio automático.
5. **Orden de middleware.** main.py:73-75 documenta que Starlette ejecuta en orden inverso al registro. Para que un middleware nuevo tenga `request.session` ya cargada hay que registrarlo **antes** de la llamada a `SessionMiddleware` (main.py:78), no después.
6. **`platform.css` no usa `:focus-visible`.** El patrón existente es `form input:focus` (platform.css:116-121).
7. **Una tabla nueva migra más barato que una columna nueva.** `Base.metadata.create_all()` (main.py:227) crea tablas nuevas en cualquier base, incluida platform.db; una columna nueva exige tocar una función `_ensure_*` y ejecutarla contra una base que arrastra 9 tablas de retraso desde E1. Esto invierte el argumento de «menos migración» a favor de la tabla dedicada de tokens.

---

## 1. Alcance

| Punto del CEO | Qué se construye aquí |
|---|---|
| 3.1 · «ver contraseña» | Botón real en las 5 pantallas con campo de contraseña, resuelto por delegación en `platform.js` |
| 3.2 · «olvidé mi contraseña» para owner e inquilino | Flujo completo de 7 rutas con token de un solo uso, hash SHA-256, 1 h de vigencia y respuesta indistinguible |
| Hallazgo de seguridad | Retiro de `/api/auth/*` y unificación de `get_current_user` con la resolución de sesión de las páginas |
| Deuda arrastrada | `must_change_password` se aplica por fin; el mínimo de contraseña se unifica en 12; se arregla el bug de argumentos de owner_portal.py:344 |

**Fuera de alcance, declarado:** i18n (D-014: español ahora, cadenas extraídas); segundo factor para owners e inquilinos; caducidad de 24 h de las claves temporales que exige `docs/phase2/SECURITY.md` §1.2 línea 38 —se deja anotada como deuda de E-bis porque exige una columna `temp_password_expires_at` y una rama más en el acceso, y ninguna de las tres propuestas la abordó—; lectura de `audit_log` desde pantalla.

---

## 2. Modelo de datos

### 2.1 `password_reset_tokens` (tabla nueva)

| Columna | Tipo | Nulo | Notas |
|---|---|---|---|
| `id` | INTEGER PK | no | |
| `user_id` | INTEGER FK `users.id` | no | FK declarativa: `PRAGMA foreign_keys=0` no la impone |
| `token_hash` | VARCHAR(64) | no | SHA-256 hexadecimal del token. **El token nunca se guarda** |
| `user_email_at_issue` | VARCHAR | no | Correo del titular al emitir; se compara al validar |
| `created_at` | DATETIME | no | `server_default=func.now()` |
| `expires_at` | DATETIME | no | `created_at + 60 min` (SECURITY.md §1.2) |
| `used_at` | DATETIME | sí | NULL = sin usar |
| `consumed_reason` | VARCHAR | sí | `usado` \| `reemplazado` \| `cambio_de_contrasena`. **VARCHAR, no Enum** |
| `requested_ip` | VARCHAR(64) | sí | |
| `requested_user_agent` | VARCHAR(300) | sí | |
| `used_ip` | VARCHAR(64) | sí | |

**Índices:** `ux_password_reset_tokens_hash` UNIQUE(`token_hash`) · `ix_password_reset_tokens_user`(`user_id`, `used_at`).

Por qué SHA-256 y no bcrypt: el token tiene 32 bytes de entropía, no hay nada que ralentizar por fuerza bruta, y un hash determinista permite buscar por igualdad con índice único en vez de recorrer la tabla comparando fila por fila.

Por qué `user_email_at_issue`: con `PRAGMA foreign_keys=0`, borrar un usuario deja sus tokens huérfanos, y SQLite reutiliza el rowid máximo. Un token viejo podría apuntar a un `id` que después ocupa otra persona. Se cierra por diseño y no confiando en la base.

Por qué VARCHAR y no Enum en `consumed_reason`: los Enums se guardan como el NOMBRE del miembro y un valor desconocido rompe la lectura del ORM. Este es justo el flujo que no puede romperse.

### 2.2 `outbox_emails` (tabla nueva)

| Columna | Tipo | Nulo | Notas |
|---|---|---|---|
| `id` | INTEGER PK | no | |
| `to_email` | VARCHAR | no | |
| `subject` | VARCHAR | no | |
| `body` | TEXT | sí | **Solo se llena si `mockmode.is_mock()`. En live queda NULL** |
| `kind` | VARCHAR | sí | `reset` \| `temp_password` \| `announcement` |
| `user_id` | INTEGER | sí | |
| `created_at` | DATETIME | no | |
| `sent_at` | DATETIME | sí | NULL = no salió |
| `error` | VARCHAR(300) | sí | |

**Índice:** `ix_outbox_emails_created`(`created_at`).

Resuelve dos cosas a la vez: hace **comprobable** un camino de correo que hoy solo imprime por consola (email_utils.py:77-84), y permite responder «¿le llegó o no?» en producción. La regla de `body` es dura: el cuerpo contiene el enlace con el token en claro; guardarlo en live anularía el sentido de hashear el token.

### 2.3 Columnas nuevas

| Tabla | Columna | Tipo | Por qué |
|---|---|---|---|
| `users` | `password_changed_at` | DATETIME NULL | Mostrar «última vez que cambiaste tu contraseña», invalidar tokens emitidos antes de un cambio, y responder al auditor cuándo se tocó la credencial |
| `login_attempts` | `kind` | VARCHAR NULL | NULL = intento de acceso (todas las filas existentes). `reset` = solicitud de recuperación. `reset_token` = intento de canjear un enlace |

`login_attempts.kind` **no es opcional**. Sin ella, `ip_is_rate_limited` (security.py:466-480) cuenta las solicitudes de recuperación como fallos de acceso y once peticiones a `/recuperar` dejan sin `/login` a toda una IP compartida durante un minuto (`MAX_FAILS_PER_IP=10`, `IP_WINDOW_MINUTES=1`, security.py:56-57). Es una negación de servicio trivial contra una oficina o un rango de CGNAT móvil, que es el escenario real del producto.

### 2.4 Sin cambio de esquema

- `users.must_change_password` (models.py:97) ya existe y ya se escribe en `owner_portal.py:329`. **Ninguna ruta lo lee hoy**: aquí empieza a valer.
- `users.locked_until` / `failed_login_count` (models.py:94-95): se limpian al completar una recuperación.
- `sessions`: `revoke_all_sessions(db, user_id, reason, except_sid)` (security.py:375-397) se reutiliza tal cual; hay precedente exacto en pages.py:823.
- `audit_log`: `security.audit()` acepta `action` libre. Acciones nuevas (texto, sin migración): `password_reset.requested`, `password_reset.suppressed_unknown`, `password_reset.suppressed_inactive`, `password_reset.suppressed_admin`, `password_reset.rate_limited`, `password_reset.token_invalid`, `password_reset.completed`, `password_reset.mail_failed`, `password.changed`, `password.forced_change`, `api.auth_legacy_blocked`.
- `accounts` (D-013): esta área **no necesita `account_id`**. El token cuelga de `user_id` y el usuario ya pertenece a una cuenta. Cuando `accounts` aterrice, lo que pasará a contarse por cuenta son los límites por hora y el remitente del correo, no el permiso. Recuperar el acceso se cuenta **por usuario, no por cuenta**: una administradora con diez usuarios no debe agotarle el cupo a sus compañeros.

---

## 3. Rutas

Router nuevo `app/routers/acceso.py` (no se engorda más `pages.py`, que ya pasa de 900 líneas). Importa `_current_user_or_none` de `pages.py`, como ya hace `owner_portal.py:63`, y llama a `register_template_globals(templates)` sobre su propia instancia de Jinja2Templates, como hacen `tenant.py:59` y `owner_portal.py:69`.

```
GET  /recuperar                  — formulario de una sola casilla (el correo)
POST /recuperar                  — solicita el enlace; responde SIEMPRE 302 a /recuperar/enviado
GET  /recuperar/enviado          — mensaje genérico, idéntico exista o no la cuenta
GET  /recuperar/{token}          — valida el token, lo pasa a la sesión y redirige; NO lo consume
GET  /recuperar/nueva            — formulario de contraseña nueva + confirmación
POST /recuperar/nueva            — fija la contraseña, quema el token, cierra todas las sesiones
GET  /recuperar/caducado         — «este enlace ya no es válido»; destino único de todo token malo
GET  /cambiar-contrasena         — cambio voluntario y destino del cambio forzado
POST /cambiar-contrasena         — exige la contraseña actual; aplica el mínimo de 12
GET  /admin/correos              — buzón de salida (SOLO admin y SOLO en modo pruebas)
```

Rutas retiradas:

```
POST /api/auth/login             — RETIRADA (404). Ver §7
POST /api/auth/logout            — RETIRADA (404)
GET  /api/auth/me                — RETIRADA (404)
```

### 3.1 `POST /recuperar` — la regla que ordena todo el flujo

**El token no concede sesión; solo permite ESCRIBIR una contraseña nueva.** Nunca autologin, nunca administrador, nunca 2FA saltado. Quien controle un buzón obtiene, como mucho, tener que volver a pasar por `/login` con todos sus frenos.

Comportamiento:

1. Escribe **siempre** una fila en `login_attempts` con `kind='reset'` y `success=True` (el `success` no importa: la consulta de freno filtra por `kind IS NULL`).
2. Emite token **solo si** el correo corresponde a un usuario existente, con `is_active=True`, con rol ≠ `admin`, y por debajo del límite de 3/hora por correo (SECURITY.md §5, línea 114) y 10/hora por IP.
3. Al emitir: `secrets.token_urlsafe(32)` (≥32 bytes, SECURITY.md §1.2 línea 39), guarda `sha256(token).hexdigest()`, marca `consumed_reason='reemplazado'` y `used_at=now` en todos los tokens vivos anteriores del mismo usuario, y encola el correo.
4. Responde **siempre** 302 a `/recuperar/enviado`. Los seis casos —inexistente, inactiva, bloqueada, de administrador, pasada de límite y éxito— son idénticos hacia fuera: mismo código, mismo `Location`, misma página. Solo se distinguen en `audit_log`.

> **Nunca un 429 con cuerpo distinto.** El propio límite sería el oráculo de enumeración que el flujo intenta cerrar. `/login` ya es cuidadoso con esto (pages.py:171-174); aquí hay que serlo igual.

**El envío va en `BackgroundTasks` de Starlette, no en línea.** `smtplib` es síncrono con timeout de 15 s (email_utils.py:93): enviar dentro de la petición haría que un correo existente tardara ~1 s y uno inexistente nada. Eso es un oráculo de existencia de cuentas cronometrable, y anula todo el cuidado del resto. La tarea recibe **solo cadenas**, nunca la `Session` de `Depends(get_db)`, que ya está cerrada cuando la tarea corre.

### 3.2 `GET /recuperar/{token}` — el token sale de la URL

Valida por `sha256` con `hmac.compare_digest`: exige `used_at IS NULL`, `expires_at > ahora`, usuario vivo, `is_active`, y `user_email_at_issue == user.email` actual.

**No marca `used_at`.** Los previsualizadores y antivirus de correo siguen los enlaces; si el GET consumiera, el enlace estaría quemado antes de que la persona lo abriera.

Si es válido: `request.session.clear()` (para no mezclar identidades si alguien lo abre con otra sesión abierta), guarda `_reset_hash` en la sesión, rota el token CSRF y redirige 302 a `/recuperar/nueva`. Con esto el token **desaparece de la barra de direcciones, del historial, del `Referer` y del registro de acceso del proxy** a partir del primer salto.

Si no es válido —desconocido, caducado, ya usado o con el correo cambiado— redirige a `/recuperar/caducado`, sin distinguir cuál de los cuatro.

Cabeceras propias de esta respuesta: `Cache-Control: no-store` y `X-Robots-Tag: noindex, nofollow, noarchive`.

### 3.3 `POST /recuperar/nueva` — lo que hace en una sola transacción

Revalida el token entero (pudo caducar mientras se escribía; no confía en el GET previo) y después:

| Acción | Por qué |
|---|---|
| `password_hash = hash_password(nueva)` y `password_changed_at = now` | |
| `used_at`, `used_ip`, `consumed_reason='usado'` | Uso único |
| Invalida los demás tokens vivos del usuario | Un enlace pedido dos veces no deja dos llaves |
| `failed_login_count = 0`, `locked_until = None` | Quien recupera legítimamente no debe seguir bloqueado por los intentos del atacante. Hoy no tiene forma de desbloquearse |
| `must_change_password = False` | Acaba de elegir una propia |
| `revoke_all_sessions(db, user.id, "password_reset")` | Precedente exacto en pages.py:823 |
| `audit(..., "password_reset.completed")` | |
| **302 a `/login`** con aviso | |

**No inicia sesión automáticamente.** Un autologin convertiría un buzón comprometido en sesión de un clic, saltaría la puerta de admin y el TOTP, y crearía un cuarto camino de autenticación —que es exactamente el problema que este diseño cierra. El coste es un clic cada varios meses.

### 3.4 `/cambiar-contrasena`

Exige la contraseña **actual** verificada con `verify_password`, también en el camino forzado: es regla única sin ramas, e impide que quien secuestre una sesión abierta se apropie de la cuenta sin conocer la clave. Al terminar: `password_changed_at`, `must_change_password=False`, invalida tokens de recuperación vivos y `revoke_all_sessions(..., "password_changed", except_sid=request.session["sid"])` para no autoexpulsar a quien acaba de cambiarla.

### 3.5 `GET /admin/correos` — buzón de salida (mock)

Tabla de `outbox_emails` con `to_email`, `subject`, `kind`, `created_at`, `sent_at`, `error` y el cuerpo desplegable. **Doble puerta: exige sesión de administrador y `mockmode.is_mock()`; en live devuelve 404.** Es lo que permite al CEO enseñar el flujo completo en una demo sin buzón.

> **Decisión que corrige a dos de las tres propuestas:** el enlace de recuperación **no se imprime nunca en ninguna respuesta HTTP del camino anónimo**, ni siquiera en modo pruebas. La tentación es fuerte (hay precedente con la clave temporal en pantalla, owner_portal.py:352-358) pero aquí el camino es anónimo, y `DATABASE_URL` explícito gana sobre `DATA_MODE`: bastaría arrancar contra la base real sin poner `DATA_MODE=live` para que `/recuperar` se convirtiera en una toma de cuenta de un clic para cualquiera. La demo se cubre con la pantalla de arriba, que exige sesión de administrador.

---

## 4. Interfaz

### 4.1 El botón «ver contraseña»

Se aplica a 5 pantallas: `/login` (que sirve también `/acceso/propietarios` y `/acceso/inquilinos`, pages.py:127-167), `/recuperar/nueva` (2 campos), `/cambiar-contrasena` (3 campos) y `admin_user_form.html`.

Marcado, idéntico en todas:

```html
<div class="field-password">
  <input type="password" id="password" name="password" required
         autocomplete="current-password"
         autocapitalize="none" autocorrect="off" spellcheck="false">
  <button type="button" class="pw-toggle" data-pw-toggle="password"
          aria-controls="password" aria-pressed="false"
          data-label-show="{{ T.pw_mostrar }}" data-label-hide="{{ T.pw_ocultar }}"
          >{{ T.pw_mostrar }}</button>
</div>
```

Reglas de obligado cumplimiento, cada una por un motivo concreto:

- **`type="button"`.** El valor por omisión de `<button>` es `submit`: sin esto, el botón envía el formulario.
- **`autocapitalize`/`autocorrect`/`spellcheck`.** Al pasar a `type=text` el teclado móvil de iOS capitaliza y autocorrige lo escrito, y el propietario acaba enviando una contraseña distinta de la que ve.
- **El JS jamás sustituye, mueve ni recrea el `<input>`, ni toca su `id`, `name` o `autocomplete`.** Solo cambia la propiedad `.type`. Reemplazar el elemento rompe el gestor de contraseñas y el autorrelleno.
- **Texto real, no icono.** Funciona con imágenes desactivadas y lo lee un lector de pantalla. Los rótulos viajan en atributos `data-*` desde la plantilla, no dentro del JavaScript (D-014).
- **Área táctil ≥44 px.** No es adorno: el uso real es un propietario en el móvil.

Comportamiento en `app/static/platform.js` — un **cuarto bloque** dentro del IIFE que ya existe (41 líneas hoy), por **delegación en `document`**, no con `querySelectorAll` al cargar:

```js
function ocultarTodas() {
  document.querySelectorAll('[data-pw-toggle]').forEach(function (b) {
    var i = document.getElementById(b.getAttribute('data-pw-toggle'));
    if (i && i.type === 'text') {
      i.type = 'password';
      b.setAttribute('aria-pressed', 'false');
      b.textContent = b.getAttribute('data-label-show') || b.textContent;
    }
  });
}

document.addEventListener('click', function (event) {
  var t = event.target;
  var btn = t && t.closest ? t.closest('[data-pw-toggle]') : null;
  if (!btn) return;
  var input = document.getElementById(btn.getAttribute('data-pw-toggle'));
  if (!input) return;
  var mostrar = input.type === 'password';
  input.type = mostrar ? 'text' : 'password';
  btn.setAttribute('aria-pressed', mostrar ? 'true' : 'false');
  btn.textContent = btn.getAttribute(mostrar ? 'data-label-hide' : 'data-label-show') || btn.textContent;
  input.focus();
  try { input.setSelectionRange(input.value.length, input.value.length); } catch (e) {}
});

document.addEventListener('submit', ocultarTodas, true);
document.addEventListener('visibilitychange', function () { if (document.hidden) ocultarTodas(); });
document.documentElement.classList.add('has-js');
```

Delegación y no `querySelectorAll` al cargar por dos razones verificables: la página de acceso se vuelve a pintar en cada error (pages.py:187-193) y el mismo control aparece en cinco plantillas. El estado **no se guarda en ningún sitio**: nada de `localStorage`, nada de la contraseña en un `data-*` ni en la URL.

CSS en `app/static/platform.css` (las variables existen, platform.css:5-14):

```css
.field-password { display: flex; align-items: stretch; gap: .4rem; }
.field-password input { flex: 1; }
.pw-toggle { display: none; min-width: 44px; min-height: 44px; padding: 0 .6rem;
  background: transparent; border: 1px solid var(--border); border-radius: 6px;
  font-size: .8rem; font-weight: 600; color: var(--muted); cursor: pointer; }
.has-js .pw-toggle { display: inline-flex; align-items: center; justify-content: center; }
.pw-toggle:focus { outline: 2px solid var(--teal); outline-offset: 1px; }
.pw-hint { font-size: .8rem; color: var(--muted); margin: .25rem 0 0; }
```

`display:none` por omisión más `.has-js` para que sin JavaScript no quede un botón muerto en pantalla. `input[type=password]` e `input[type=text]` ya comparten estilo (platform.css:102-104), así que alternar el tipo no cambia el aspecto.

> **CSP.** Cero `onclick`, cero `style=`. La CSP es `script-src 'self'; style-src 'self'` (security.py:238-243) y el comentario de cabecera de `platform.js` documenta el precedente: cuando había `onsubmit="return confirm(...)"` en las plantillas, **no se ejecutaban** y las acciones destructivas se hacían sin preguntar. Un botón con `onclick` aquí parecería funcionar y no funcionaría.

### 4.2 Plantillas

| Pantalla | Plantilla | Notas |
|---|---|---|
| Acceso | `login.html` (modificar) | Envoltorio `.field-password` + enlace «¿Olvidaste tu contraseña?» bajo el botón Entrar, visible solo si `password_reset_available()` |
| Pedir enlace | `recuperar.html` (nueva) | Reutiliza `.card .login-card`. Una casilla `type=email` con `autocomplete="username"`. Sin selector de rol: el rol sale de la base, nunca de la pantalla |
| Confirmación | `recuperar_enviado.html` (nueva) | Texto fijo: «Si ese correo corresponde a una cuenta activa, te enviamos un enlace. Revisa también la carpeta de no deseados. El enlace caduca en 1 hora.» Nunca «te enviamos un enlace» a secas, que confirmaría existencia |
| Contraseña nueva | `recuperar_nueva.html` (nueva) | 2 campos con `autocomplete="new-password"`. Reglas **antes** de escribir, no como error después: «Mínimo 12 caracteres; distinta de tu correo. Al guardar se cerrarán todas tus sesiones» |
| Enlace no válido | `recuperar_caducado.html` (nueva) | Un solo mensaje para los cuatro motivos. Botón único: pedir otro |
| Cambiar contraseña | `cambiar_contrasena.html` (nueva) | 3 campos. Doble uso: ver §6 |
| Buzón (mock) | `admin_outbox.html` (nueva) | `active='correos'` + contadores del menú |
| Reset del admin | `admin_user_form.html` (modificar) | **Hoy la línea 48 es `<input type="text" ... placeholder="Mínimo 8 caracteres">`: la clave temporal se pinta en claro en pantalla.** Pasa a `type="password"` con el mismo botón y placeholder de 12 |

**Clases:** solo se usan `.card`, `.login-card`, `.alert`, `.alert-error`, `.alert-success`, `.muted`, `.btn`, `.btn-primary`, que existen (platform.css:63, 79, 123, 134, 157, 164, 170, 89). No se usan `.flash-ok` ni `.btn-danger`, que varias plantillas invocan hoy sin que existan en el CSS.

**Menú lateral:** toda pantalla que extienda `base.html` con `user` en contexto necesita `active` y los contadores (`open_tickets`, `unread_messages`), inyectados por el manejador como hace `owner_portal._nav_badges`. Si no se pasa `user`, `base.html:116-121` renderiza `<main>` sin barra lateral —que es justo lo que hace falta para el cambio forzado.

### 4.3 Cadenas (D-014)

Las cadenas visibles **nuevas** y las modificadas de `login.html` se declaran en `app/textos/acceso_es.py` como diccionario plano (clave → castellano) y se exponen a Jinja como global `T`, junto a `csrf_input`, en `security.register_template_globals` (security.py:155-169). Las plantillas escriben `{{ T.recuperar_titulo }}`.

No se construye i18n, no se negocia idioma, no se traduce nada, y **no se retrofitea a las 27 plantillas existentes**: eso es de otra área. Español ahora, cadenas fuera de la plantilla, listas para traducir.

---

## 5. Correo

### 5.1 Refactor de `email_utils.py`

Se separa el envío de la redacción, sin dependencias nuevas (sigue `smtplib`):

- `_compose_password_reset(nombre, enlace, minutos)` junto al `_compose_temp_password` que ya existe (email_utils.py:48-59).
- `enviar(to, subject, body, kind, user_id)` de bajo nivel: escribe la fila en `outbox_emails`, intenta el envío, actualiza `sent_at` o `error`, y nunca lanza.
- **`send_temp_password_email` y `send_password_reset_email` empiezan por la misma guarda:**

```python
if not emails_are_sent():
    return MailResult(sent=False, configured=False)
```

Esto es el arreglo del punto 3 de §0. `mockmode.emails_are_sent()` existe (mockmode.py:112-114) pero `email_utils` nunca la consulta: solo la respetan los llamadores, y `pages.py:827` no la respeta. Con la guarda dentro del emisor, «en simulación no sale un correo» pasa de promesa a código.

- **Arreglo de una línea, mismo commit:** `owner_portal.py:344` llama `send_temp_password_email(tenant.name, tenant.email, ...)` cuando la firma es `send_temp_password_email(to_email, name, ...)` (email_utils.py:62-67). En cuanto se configure SMTP, la clave temporal del inquilino se enviaría a su *nombre* como si fuera una dirección. `pages.py:828` sí lo llama bien.

### 5.2 Contenido del correo de recuperación

Mínimo a propósito: nombre, enlace, «caduca en 1 hora», «si no lo pediste, ignora este mensaje». **Sin propiedad, sin dirección, sin ticket, sin importes.** Un correo de recuperación es en sí mismo un objeto con datos personales de una persona identificada.

### 5.3 Enlace absoluto

Variable de entorno nueva `PUBLIC_BASE_URL` (no es bandera). Sin ella se cae a `str(request.base_url)`, como ya hace `owner_portal.py:345`, que detrás de un proxy puede generar `http://` o un host interno y romper el enlace.

---

## 6. `must_change_password`: se aplica por fin

Hoy `owner_portal.py:329` lo pone en `True` para **cada** inquilino dado de alta y ninguna ruta lo lee: el dato miente desde el primer día, y el propietario conserva para siempre una clave que puede leer.

**Mecanismo: middleware, no comprobación por ruta.** Mismo argumento que el propio repositorio ya escribió sobre el CSRF (security.py:171-177): una dependencia hay que acordarse de añadirla en cada ruta nueva y tarde o temprano se olvida; la protección debe ser por omisión y las excepciones explícitas.

`ForcePasswordChangeMiddleware`, registrado **antes** de la llamada a `SessionMiddleware` en main.py (para que la sesión esté cargada cuando corra; ver §0 punto 5). **No consulta la base**: lee la marca `_must_change_pw` que se escribe en la sesión en el momento en que la sesión queda plenamente autenticada —pages.py:250-252 para el camino sin 2FA y al completar `POST /2fa` para el admin—. Coste cero en base de datos, y no se desincroniza porque todo cambio de `must_change_password` por parte del admin ya revoca todas las sesiones (pages.py:823), forzando un acceso nuevo que relee la marca.

**Lista blanca estricta** (esto es lo que impide encerrar al CEO en un bucle de redirecciones como el `ERR_TOO_MANY_REDIRECTS` que ya documenta pages.py:96-106):

```
/cambiar-contrasena · /logout · /login · /2fa · identity.admin_login_path()
/auth/google/*      · /static/*  · /api/health · /recuperar*
```

Todo lo demás → 302 a `/cambiar-contrasena`. Si la ruta empieza por `/api/` → 403 JSON, no redirección.

`/media/*` **no** está en la lista blanca: las fotos del interior de una vivienda son datos, no recursos estáticos.

Al escribirse la marca se marca también `audit(..., "password.forced_change")`.

---

## 7. Cierre del hallazgo de seguridad

### 7.1 El diagnóstico

`POST /api/auth/login` (auth.py:64-71) valida correo y contraseña y escribe `request.session["user_id"]` **sin freno por IP, sin `locked_until`, sin `is_active`, sin la puerta `ADMIN_LOGIN_PATH`, sin TOTP, sin crear fila en `sessions` y sin escribir en `login_attempts` ni en `audit_log`**. La cookie que emite no abre las pantallas HTML (esas exigen `sid` vivo, pages.py:83-88) pero **sí** abre `/api/admin/*` y `/api/owner/*`, que dependen de `require_role` → `get_current_user` (auth.py:40-53, owner.py:27).

Dos consecuencias, en orden de gravedad:

1. **Adivinación de contraseñas sin freno ni rastro** contra cualquier cuenta, incluida la del administrador. Es el paso previo que hace explotable lo siguiente.
2. **Salto del segundo factor y del bloqueo por intentos** para quien ya tenga la contraseña, y desde ahí crear usuarios (`POST /api/admin/users`) y reasignar propiedades.

### 7.2 Verificación antes de tocar nada (hecha)

```
grep -rn "api/auth" --include=*.py --include=*.html --include=*.js --include=*.json --include=*.md
```

Devuelve exactamente: `platform/app/main.py:117` (el montaje), `platform/README.md:53,81-83` y `docs/ARCHITECTURE_STATE.md:150,159-161`. **Ni una plantilla, ni `platform.js`, ni ninguna de las 10 suites.** El único uso de la API JSON en el repositorio es `tests/test_owner_portal.py:174-182`, que autentica por el **formulario HTML** y manda `x-csrf-token` — no por `/api/auth/login`. Con el despliegue de Fly suspendido y la fase local en curso, no hay tráfico de producción que auditar.

### 7.3 El cierre, en dos mitades

**Mitad A — retirar las tres rutas JSON detrás de bandera.** `LEGACY_JSON_AUTH_ENABLED`, por omisión `false`: `/api/auth/*` devuelve **404** (no 401: un 401 confirmaría que la ruta existe) y escribe `audit(..., "api.auth_legacy_blocked")` con la IP. La bandera es el botón de marcha atrás de un despliegue; el `audit` dice quién la llamó. Se borra el código definitivamente tras dos semanas sin ninguna llamada registrada. Se conservan de `auth.py` `hash_password`, `verify_password` y `require_role`, que usan `admin.py` y `owner.py:18`.

**Mitad B — una sola implementación de «quién eres».** Se extrae `security.resolve_session_user(request, db)` con el cuerpo exacto de `pages._current_user_or_none` (pages.py:63-94): `user_id` en sesión, usuario existente, `is_active`, fila viva en `sessions` vía `resolve_server_session` (revocación, inactividad 30 min / 15 el admin, absoluto 12 h) e `identity.totp_satisfied`.

- `pages._current_user_or_none` pasa a ser un envoltorio que devuelve `None`.
- `auth.get_current_user` pasa a ser un envoltorio que lanza 401.

Vive en `security.py` y no en `identity.py`: `resolve_server_session` y las constantes de sesión ya están ahí, y `identity.py` no toca la base en ninguna de sus funciones hoy —meterle un resolvedor que recibe `db` rompería esa propiedad. No hay ciclo: `security.py` importa modelos de forma diferida y no importa `identity` hoy, e `identity.py` no importa `security`.

Esto es literalmente el argumento que ya está escrito en la cabecera de `pages.py:8-12` sobre no duplicar el filtro de pertenencia. **Efecto: aunque mañana alguien vuelva a montar un login JSON, el agujero no reaparece solo.**

**Efecto colateral deseado y visible:** `/api/admin/*` y `/api/owner/*` quedan sujetas a revocación de sesión, baja lógica y segundo factor. Un usuario con `is_active=False` deja de poder leerlas —hoy puede—. Cualquier guion que dejara una cookie viva días dejará de funcionar.

### 7.4 De propina, una línea

`main.py:71` es `FastAPI(title=..., version="2a")`: hoy `/docs`, `/redoc` y `/openapi.json` publican un mapa navegable de los endpoints de administración. Se pasan a `None` cuando `security.is_production()` (que ya falla del lado seguro, security.py:60-67). En dev siguen disponibles. Un reconocimiento gratuito de la superficie de administración no se regala.

---

## 8. Contraseñas: un solo validador

Nueva `security.validar_fuerza_contrasena(pw, email) -> Optional[str]` (devuelve el mensaje de error o `None`):

| Regla | Motivo |
|---|---|
| ≥ 12 caracteres | `docs/phase2/SECURITY.md` §1.2 línea 37 lo exige; `pages.py:813` acepta 8. El documento manda |
| ≤ 72 bytes UTF-8 | bcrypt trunca en silencio a partir de ahí: una contraseña más larga da una falsa sensación de fuerza |
| Distinta del correo | |
| Fuera de una lista corta embebida de claves obvias | Sin dependencia nueva |

Se usa en **cinco** puntos: `POST /recuperar/nueva`, `POST /cambiar-contrasena`, `pages.py:813` (hoy 8), `routers/admin.py` (alta de usuario) y el alta de owner.

**Verificado que no rompe el alta de inquilinos:** `secrets.token_urlsafe(9)` (owner_portal.py:323) produce exactamente 12 caracteres, que es justo el mínimo nuevo.

**Cómo se aplica el 12 a las cuentas que hoy tienen 8-11:** tras bcrypt la longitud ya no es legible, así que la única vía es mirarla en el momento del acceso. En el inicio de sesión correcto (pages.py:250), si `len(password) < 12` se marca `must_change_password=True`. La primera vez que entran, cambian. **No se fuerza rotación a las contraseñas que ya cumplen**: hacer cambiar a todo el mundo el mismo día genera una avalancha de soporte sin ganancia proporcional.

---

## 9. Puertas legales y banderas

> ### ✅ Puertas legales — D-016, sin criterio nuevo
>
> | Módulo | Estado | Bandera | Comportamiento |
> |---|---|---|---|
> | Recuperación de contraseña | Se construye ahora | `DATA_MODE` (existente) | En mock: el token **sí** se emite y se guarda, el correo **no** sale (guarda dentro de `email_utils`) y el cuerpo queda en `outbox_emails.body` para poder probarlo. En live: `body` queda NULL y sigue exigiéndose `LEGAL_CLEARANCE_REF` para arrancar (mockmode.py:61-78) |
> | Envío de correo | Se construye ahora | `DATA_MODE` (existente) | `emails_are_sent()` pasa a evaluarse **dentro** del emisor, no en los llamadores |
> | Buzón de salida en pantalla | Se construye ahora | `DATA_MODE` + rol admin | 404 en live |
>
> No se inventa ninguna puerta legal nueva. La recuperación no crea datos personales que no estuvieran ya en `users`; lo que toca a una persona real es el **envío**, y eso queda cerrado por la puerta que ya existe.

| Bandera | Valor por omisión | Efecto |
|---|---|---|
| `PASSWORD_RESET_ENABLED` | `true` | Disponibilidad efectiva = `bandera AND (is_mock() OR smtp_configurado())`. En producción **sin** cuenta SMTP, el enlace de `/login` no se pinta y las rutas devuelven 404: una recuperación cuyo correo nunca llega es peor que no ofrecerla, porque la persona se queda esperando en vez de llamar |
| `LEGACY_JSON_AUTH_ENABLED` | `false` | `/api/auth/*` → 404 + `audit`. Solo para marcha atrás |
| `PUBLIC_BASE_URL` | — | No es bandera: base del enlace absoluto del correo |

Banderas existentes que **no** se tocan: `ADMIN_LOGIN_PATH`, `REQUIRE_TOTP_FOR_ALL`, `TENANT_MODULE_ENABLED`.

Dos aclaraciones que evitan malentendidos con otras áreas:

- **`TENANT_MODULE_ENABLED` apagada no apaga la recuperación.** `_require_tenant` devuelve 503 (tenant.py:68-70), pero recuperar la clave no le da acceso a nada mientras la bandera esté abajo. `/recuperar` no se condiciona a ella.
- **`REQUIRE_TOTP_FOR_ALL` sigue mandando.** Como el restablecimiento no inicia sesión, el usuario vuelve a `/login` y el segundo factor se aplica igual. La recuperación no es un rodeo del TOTP.

**Planes y trial (punto 7.2 del CEO): la autenticación y la recuperación NO se limitan por plan.** Están disponibles en el trial de 90 días y en Standard, Standard+, Enterprise y Enterprise+. Un producto que vende control de acceso no cobra por poder entrar, y ligar la recuperación al plan convertiría un impago en una pérdida de acceso irreversible. **El área de planes no debe meter estas dos funciones en su tabla de características.**

---

## 10. Migración

> ⚠️ `platform.db` es la base **real** con los propietarios del CEO y está **sin migrar desde E1**: le faltan 9 tablas y 7 columnas de `users`. Los respaldos automáticos están cancelados por decisión del CEO, así que la copia manual es la única red.

0. **Con la app detenida**, copiar `platform/data/platform.db` a `platform/data/platform.db.AAAAMMDD.bak` y verificar con `sqlite3 ... "PRAGMA integrity_check"`. Ensayar los pasos 1-7 contra la **copia** y solo después contra el original.
1. `models.py`: declarar `PasswordResetToken` y `OutboxEmail`; añadir `LoginAttempt.kind` (VARCHAR nullable) y `User.password_changed_at` (DATETIME nullable). **Ningún Enum nuevo. Ninguna columna NOT NULL sin default.** Son las tres cosas que SQLite no perdona.
2. `Base.metadata.create_all()` (main.py:227) ya crea las dos tablas nuevas en cualquier base. Cero ALTER para ellas.
3. Añadir `"password_changed_at": "ALTER TABLE users ADD COLUMN password_changed_at DATETIME"` al diccionario `wanted` de `_ensure_user_security_columns()` (main.py:161-173). No hay que tocar nada más: la función ya aplica solo lo que falta.
4. Nueva `_ensure_login_attempt_columns()`, calcada de `_ensure_ticket_columns` (main.py:183-218): `PRAGMA table_info(login_attempts)` → si falta `kind`, `ALTER TABLE login_attempts ADD COLUMN kind VARCHAR`. Si la tabla no existe, salir (de eso se ocupa `create_all`).
5. Nueva `_ensure_auth_indexes()`, patrón de `_ensure_property_site_ref` (main.py:132-147): `CREATE UNIQUE INDEX IF NOT EXISTS ux_password_reset_tokens_hash ON password_reset_tokens(token_hash)`; `CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user ON password_reset_tokens(user_id, used_at)`; `CREATE INDEX IF NOT EXISTS ix_login_attempts_email_created ON login_attempts(email, created_at)`. `IF NOT EXISTS` la hace idempotente; `create_all` no añade índices a tablas preexistentes.
6. Nueva `_purge_expired_reset_tokens()`: `DELETE` de las filas con `expires_at < ahora - 7 días`. Minimización de datos: una fila de recuperación es el registro de que una persona concreta olvidó su contraseña un día concreto desde una IP concreta. Se ejecuta al arrancar; no hay planificador y el arranque es suficientemente frecuente.
7. Registrar las tres funciones en `on_startup()` justo detrás de las tres `_ensure_*` existentes (main.py:227-230).
8. **`security.py`, cambio de una línea que no es opcional:** añadir `LoginAttempt.kind.is_(None)` al filtro de `ip_is_rate_limited` (security.py:471-479). Va en el mismo commit que la columna. Sin él, `/recuperar` bloquea `/login`.
9. `security.py`: añadir `validar_fuerza_contrasena` y `resolve_session_user`. Reescribir `pages._current_user_or_none` y `auth.get_current_user` como envoltorios. **Este paso solo mueve código: se hace y se corren las 10 suites antes de tocar nada más.**
10. `auth.py`: poner las tres rutas JSON detrás de `LEGACY_JSON_AUTH_ENABLED`. Actualizar el docstring de auth.py:6, que dice literalmente «No OAuth/JWT/password-reset — out of scope for 2a» y ya es falso en las tres cosas.
11. `main.py:71`: `docs_url`/`redoc_url`/`openapi_url` a `None` en producción.
12. Registrar `ForcePasswordChangeMiddleware` **antes** de la llamada a `SessionMiddleware`.
13. **Resembrar las suites existentes:** poner `must_change_password=False` explícitamente en los usuarios de prueba de `test_tenant.py`, `test_owner_portal.py` y `test_ui.py`, o el middleware las redirigirá y romperá la línea base de 261 pruebas. Es el efecto esperado, no un fallo.
14. Añadir `/login`, `/recuperar`, `/recuperar/nueva` y `/cambiar-contrasena` a la lista de URLs de `test_ui.py:90` que se revisan buscando código en línea (hoy solo cubre 4 pantallas de owner).
15. Script nuevo `platform/scripts/migrar.py`: abre el `DATABASE_URL` indicado, ejecuta `create_all` + las cinco `_ensure_*` e imprime qué añadió. Hace falta porque en live la app se niega a arrancar sin `LEGAL_CLEARANCE_REF` y hoy el único camino de migración es el arranque. Ejecutar primero contra el `.bak`, comparar `PRAGMA table_info` antes y después, y solo entonces contra `platform.db`.
16. Script nuevo `platform/scripts/restablecer_admin.py`: recuperación fuera de banda del administrador. Pide la contraseña por consola, valida los 12, escribe el hash, pone `must_change_password=True`, revoca todas las sesiones y anota `audit_log` con actor NULL y acción `admin.password_reset_cli`. Bandera opcional `--reset-totp` que borra `totp_secret` y obliga a re-enrolar (perder el teléfono es una avería distinta de perder la contraseña). *[supuesto]* el CEO tiene acceso de consola a la máquina; la fase local en curso lo respalda.
17. Actualizar `docs/phase2/SECURITY.md` §1.2 y §5 (pasan de plan a implementado) y `docs/ARCHITECTURE_STATE.md:159-161`, que lista `/api/auth/login` como «vivo» y quedaría mintiendo.

**Reversión:** las dos tablas nuevas quedan huérfanas y vacías; las dos columnas quedan nullable y sin lectores. SQLite no permite `DROP COLUMN` y no hace falta: sin código que las lea son inertes.

---

## 11. Handoff

- [ ] Tabla `password_reset_tokens` + 2 índices
- [ ] Tabla `outbox_emails` + índice
- [ ] Columnas `users.password_changed_at` y `login_attempts.kind`
- [ ] Filtro `kind IS NULL` en `ip_is_rate_limited`
- [ ] Router `acceso.py` con las 7 rutas de recuperación + las 2 de cambio
- [ ] Pantalla `/admin/correos` (admin + mock)
- [ ] Botón «ver contraseña» en `platform.js` + `platform.css` + 5 plantillas
- [ ] `app/textos/acceso_es.py` expuesto como `T`
- [ ] Guarda `emails_are_sent()` dentro de `email_utils` + `send_password_reset_email`
- [ ] Arreglo de argumentos en `owner_portal.py:344`
- [ ] `security.validar_fuerza_contrasena` aplicada en los 5 puntos
- [ ] `security.resolve_session_user` única, con `pages` y `auth` como envoltorios
- [ ] `/api/auth/*` detrás de `LEGACY_JSON_AUTH_ENABLED=false` + audit
- [ ] `/docs` y `/openapi.json` ocultos en producción
- [ ] `ForcePasswordChangeMiddleware` con lista blanca de 9 entradas
- [ ] Suite `tests/test_acceso.py` con la línea `RESULTADO:`
- [ ] `python tests/run_all.py` en verde: 261 + las nuevas, 0 fallidas

**Estado: 0 de 17 hechos.**
