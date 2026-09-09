# Hallazgos de seguridad — 2026-09-08

**Estado:** dos defectos **confirmados con prueba reproducible**, ninguno corregido todavía.
**Contexto:** la plataforma está suspendida en Fly y solo corre en local, así que hoy ninguno
es explotable desde internet. Los dos dejan de estar contenidos en cuanto la plataforma vuelva
a estar en línea — y el segundo, antes: se activa al construir lo que el CEO pidió.

---

## H-1 · La API JSON permite adivinar contraseñas sin límite y salta todos los controles

**Severidad:** alta · **Ruta:** `POST /api/auth/login` ([auth.py:64-71](../../platform/app/auth.py))
**Corrige:** etapa E8 · **Depende de decisiones del CEO:** ninguna

### Qué pasa

`POST /api/auth/login` verifica el correo y la contraseña, y nada más. No llama a
`ip_is_rate_limited`, ni a `register_failed_login`, ni a `audit`. Establece la sesión
directamente. `get_current_user` ([auth.py:28-37](../../platform/app/auth.py)) solo lee
`request.session["user_id"]` y comprueba que el usuario exista.

Es decir, salta:

| Control | Qué protege | ¿Se aplica en la API? |
|---|---|---|
| Freno por IP (10 fallos/min) | Adivinación de contraseñas | **No** |
| Bloqueo por cuenta (5 fallos → 15 min) | Adivinación dirigida | **No** |
| `is_active` | Cuentas desactivadas | **No** |
| Segundo factor de administrador | La cuenta que lo ve todo | **No** |
| Puerta oculta de administración | Descubrimiento del panel | **No** |
| Tabla `sessions` | **Revocación de sesiones** | **No** |
| Registro en `login_attempts` y `audit_log` | Rastro del ataque | **No** |

La última fila importa más de lo que parece: **revocar todas las sesiones de un usuario no
cierra este acceso**, porque este camino no crea fila en `sessions`.

Estas rutas gobiernan `/api/admin/*` ([admin.py:21](../../platform/app/routers/admin.py)) y
`/api/owner/*` ([owner.py:27](../../platform/app/routers/owner.py)).

### Prueba reproducible

Sobre una base desechable, sin tocar `platform.db`:

```
20 intentos fallidos por CADA vía, mismo usuario

  HTML  /login          códigos: [401, 429]  últimos 5: [429, 429, 429, 429, 429]
  API   /api/auth/login códigos: [401]       últimos 5: [401, 401, 401, 401, 401]

  Filas en login_attempts: 10   (si la API registrara serían 40)
  Usuario -> failed_login_count=0  locked_until=2026-09-08 05:34:41

  ¿La API frena en algún momento? NO — 20/20 sin freno
  Clave CORRECTA por la API tras el bloqueo -> 200 (ENTRÓ)
```

Y con un administrador **desactivado, bloqueado una hora y con 99 fallos acumulados**:

```
GET /login                     -> 200, token CSRF obtenido
POST /api/auth/login           -> 200  (sesión establecida)
GET  /api/admin/users          -> 200  (2 registros: nombre, correo, teléfono, rol)
GET  /api/admin/owners         -> 200
GET  /api/admin/properties     -> 200
GET  /admin  (HTML)            -> 302  ← el camino HTML sí lo rechaza
```

### Lo que NO lo protege

El CSRF sí se aplica a esta ruta (`CSRF_EXEMPT_PATHS` contiene únicamente `/api/health`,
[security.py:40-42](../../platform/app/security.py)). Pero no es una defensa: un `GET` a
cualquier página devuelve un token de sesión válido que se manda en la cabecera
`x-csrf-token`. Sí demuestra, en cambio, que **ningún cliente está usando ese endpoint hoy**
— dato que hay que confirmar antes de retirarlo.

### Cómo se cierra (E8)

Extraer `resolve_session_user()` con el cuerpo de `pages._current_user_or_none`
([pages.py:63-94](../../platform/app/routers/pages.py)) y hacer que `auth.get_current_user`
lo use. Retirar las tres rutas JSON de autenticación detrás de una bandera, devolviendo
**404 y no 401** para no confirmar que existen.

---

## H-2 · El modo simulación no bloquea el correo donde se afirma que lo bloquea

**Severidad:** media hoy, **alta al construir el punto 3.2 del CEO**
**Ruta:** `send_temp_password_email` ([email_utils.py:63](../../platform/app/email_utils.py))
**Corrige:** etapa E10

### Qué pasa

`send_temp_password_email` **nunca consulta el modo simulación**. Solo comprueba si el SMTP
está configurado. La guarda `emails_are_sent()` existe únicamente en dos llamadas de
`owner_portal.py` ([:342](../../platform/app/routers/owner_portal.py) y
[:433](../../platform/app/routers/owner_portal.py)); el restablecimiento de contraseña del
administrador ([pages.py:827](../../platform/app/routers/pages.py)) llama a la función
directamente.

### Prueba reproducible

Interceptando `smtplib.SMTP`, sin conectar con ningún servidor:

```
DATA_MODE=mock?     True
emails_are_sent()?  False   ← la plataforma afirma que no envía

Resultado: sent=True configured=True

>>> SE INTENTÓ ENVIAR un correo real:
    servidor: smtp.ejemplo.test:587
    para:     persona.real@gmail.com
    asunto:   Tu acceso a la plataforma — Aura Homes Cancún
    contiene la contraseña EN CLARO: True
```

### Por qué importa más de lo que parece

Lo único que lo detiene hoy es que `SMTP_PASSWORD` está **vacío** en `platform/.env`.
`SMTP_HOST` y `SMTP_USER` **sí tienen valor**. La guarda efectiva es un campo en blanco, no
una decisión de diseño.

**Y el punto 3.2 del CEO —«olvidé mi contraseña»— exige llenar ese campo.** El día que se
configure el SMTP de producción, el modo simulación empieza a enviar correos reales con
contraseñas en claro a direcciones reales. El defecto se activa exactamente con lo que se
pidió construir.

### Contradice un reporte ya entregado

El reporte de Legal del 2026-08-11 lista, entre las barreras técnicas ya implementadas:
«No envía correos reales». Para esta ruta eso no es cierto. El reporte de Legal del
2026-09-08 lo corrige.

### Cómo se cierra (E10)

La guarda va **dentro de `email_utils`**, no en quien llama: es la única forma de que no se
olvide en la siguiente ruta que envíe correo. El diseño del área E añade además una tabla
`outbox_emails` y una pantalla `/admin/correos`, de modo que en simulación el mensaje quede
observable sin salir de la máquina.

---

## Cosas que se revisaron y están bien

Para que quede constancia de que se buscó y no se encontró:

- El aislamiento entre propietarios se sostiene: 27 comprobaciones lo verifican y lo ajeno
  devuelve 404 y nunca 403.
- Las fotos de tickets se re-codifican al subirlas y pierden el EXIF, incluidas las
  coordenadas GPS; se sirven por una ruta con autorización.
- El CSRF es por middleware y cubre por omisión; las excepciones son explícitas y hay una sola.
- La política de contenido prohíbe scripts y estilos en línea, y hay una prueba que falla si
  aparece `onclick=` o `style=` en el HTML servido.
- Las contraseñas se guardan con bcrypt; el restablecimiento revoca todas las sesiones del
  usuario.
