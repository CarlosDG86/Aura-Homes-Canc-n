# Handoff a Dev — Phase 2

**Fecha:** 2026-08-08 · Lee primero `../DESIGN.md`, `../SECURITY.md`, `../AI_TICKET_AGENT.md`.

## Antes de escribir código

1. **No arranques por el módulo del inquilino.** El orden de abajo no es sugerencia: los cimientos
   de seguridad (E1) deben existir antes de que haya un solo dato de inquilino en la base.
2. **`platform/data/platform.db` tiene datos reales del CEO** (owners y propiedades). Respalda antes
   de cualquier prueba que escriba: `cp platform/data/platform.db platform/data/platform.db.bak-<fecha>`.
3. Decisiones del CEO ya tomadas (2026-08-08) — **no vuelvas a preguntar**:
   - El módulo Owner **se conserva**, tras `OWNER_PROPERTY_MANAGE_ENABLED` (interfaz **y** servidor).
   - 2b se enciende en **modo mock** (`DATA_MODE=mock`) con base de datos aparte. Legal llega después.
   - Pagos (2c): solo conexiones y requisitos, en un submenú de Admin. Sin cobro.
4. Pendiente de visto bueno del CEO: sustituir el enlace "Administración" por el desplegable
   "Ingresar" (`DESIGN.md §3`) — es un cambio visible en el sitio público.

## Etapas

### E1 — Cimientos de seguridad (bloquea todo lo demás)

**Estado: 5 de 7 hechos y verificados (2026-08-08).** Código en `platform/app/security.py`.
26 pruebas automatizadas en verde; migración probada sobre copia de la base real sin pérdida.

- [x] Tokens **CSRF** en los 9 formularios — implementado como **middleware**, no como dependencia
      por ruta: así una ruta nueva queda protegida sin que nadie recuerde añadir nada
      (deny-by-default). El middleware reinyecta el cuerpo de la petición para no romper las
      subidas `multipart`.
- [x] La app **no arranca** en producción con `SECRET_KEY` por defecto o de menos de 32 caracteres.
      `APP_ENV` se asume `production` si no está definida: un descuido de configuración falla del
      lado seguro.
- [x] Límite de intentos + `login_attempts` + bloqueo por cuenta (5 fallos → 15 min) **e IP**
      (10/min). Mensaje genérico único: no revela si el correo existe.
- [x] Cabeceras de seguridad (middleware) y tabla `audit_log` con los eventos de acceso.
- [x] Migraciones idempotentes (`_ensure_user_security_columns()`), mismo patrón que
      `_ensure_property_site_ref()`.
- [x] Parcial — rotación de sesión al iniciar (anti-fijación), caducidad por inactividad
      (30 min / 15 min admin) y absoluta (12 h), cookie `Secure` fuera de desarrollo, expulsión
      inmediata de cuentas desactivadas.
- [x] **Tabla `sessions` hecha y verificada** (2026-08-08, 23 pruebas). La cookie ya **no** lleva
      el `user_id` como única prueba: lleva un `sid` opaco que apunta a una fila, y el servidor
      decide en cada petición si sigue viva. Probado: revocar la fila **expulsa a esa cookie de
      inmediato**. Se revoca en cerrar sesión, al restablecer contraseña (cierra todas), por
      inactividad, por límite absoluto y desde `/sesiones` ("cerrar las demás"). Cada revocación
      guarda su motivo.
- [x] **`scoping.py` hecho y verificado** — `scoped_properties/tickets/leases/users`,
      `owned_properties` y `assert_can_assign_property`. `owner.py` refactorizado: el filtro
      `owner_id == user.id` estaba copiado 5 veces y ahora vive en un solo sitio.
      27 pruebas de aislamiento entre propietarios en verde.
- [ ] **Pendiente:** sacar el CSS en línea de las plantillas para poder quitar `'unsafe-inline'`
      de `style-src` en la CSP.

### E2 — Identidad
- [ ] Google OIDC con PKCE, `state`, `nonce`; validación completa del `id_token`
- [ ] Vinculación por `google_sub`; **sin auto-registro** (rechazar correos desconocidos)
- [ ] Rutas `/acceso/propietarios` y `/acceso/inquilinos`
- [ ] Admin en `ADMIN_LOGIN_PATH` + **TOTP obligatorio** + alerta por correo
- [ ] Activación de cuenta y recuperación con token de un solo uso

### E3 — Sitio público
- [ ] Desplegable "Ingresar / Log in" en `build.py` (`topbar()`), bilingüe, accesible por teclado
- [ ] Retirar `admin-link`; cadenas nuevas en `data/site.json` (ES y EN)
- [ ] `noindex` para la ruta de admin

### E4 — Módulo Owner

**Estado: completo y verificado (2026-08-08), 38 pruebas en verde.**
Archivo: `routers/owner_portal.py` + 7 plantillas.

- [x] Alta de inquilinos + vínculo vía `leases`, validando pertenencia con
      `assert_can_assign_property` (probado: asignar a la casa de otro → 404 y **no se crea nada**)
- [x] Tickets: listado con filtros, detalle, comentar, marcar en proceso, resolver, reabrir,
      todo en `ticket_events`. **Resolver exige nota** — sin ella el inquilino no sabe qué se hizo
      y el historial no sirve ante una disputa
- [x] Reporte por unidad + descarga CSV (incluye tiempo medio de resolución y emergencias)
- [x] Comunicados con `announcement_recipients` (probado: no llegan a inquilinos de otro owner)
- [x] Mensajes 1:1 acotados por `scoped_users` (escribir al inquilino de otro → 404)
- [x] `contact_phone` en el perfil, separado del teléfono personal
- [x] Terminar arrendamiento (corta el acceso del inquilino)
- [x] `OWNER_PROPERTY_MANAGE_ENABLED` aplicada **en el servidor**, no solo ocultando el botón
- [x] **Bandejas en ambos sentidos, hechas y verificadas** (2026-08-08, 21 pruebas):
      `/inquilino/mensajes` mezcla comunicados y conversación en una sola línea de tiempo;
      el inquilino responde a su propietario; ambos tienen contador de no leídos y resaltado
      de lo nuevo; se marca leído al abrir, conservando el resalte en esa misma vista.
      **El inquilino no elige destinatario**: se resuelve en el servidor desde su arrendamiento
      (probado: mandar `recipient_id` de otro propietario se ignora).
- [ ] **Pendiente:** asignar un ticket a un tercero (`assigned_to_user_id` existe pero no hay UI)

### E5 — Módulo Inquilino + agente AI

**Estado: base construida y verificada (2026-08-08), 33 pruebas en verde.**
Archivos: `routers/tenant.py`, `uploads.py`, `ai_agent.py`, `mockmode.py` + 5 plantillas.

- [x] Perfil editable; el correo de acceso **no** se cambia desde ahí (secuestro de cuenta)
- [x] Carga de fotos: validación por contenido (no por extensión), re-codificación a 1568 px,
      **EXIF/GPS verificado como eliminado en disco**, nombre UUID, fuera del árbol web
- [x] `GET /media/tickets/{id}/{photo_id}` con autorización vía `scoped_tickets`
      (probado: sin sesión → 401, otro inquilino → 404)
- [x] Agente AI con `output_config.format` y esquema estricto; **degrada al formulario manual**
      si falta la llave, se agota el presupuesto o la API falla
- [x] Palabras clave de emergencia del lado del servidor — probado: "huele a gas" con prioridad
      "baja" elegida por el inquilino se eleva igualmente a `emergencia`
- [x] `ai_usage` + tope mensual de presupuesto
- [x] **Formulario manual de respaldo** (hoy es la vía activa: no hay `ANTHROPIC_API_KEY`)
- [x] Botones de correo y WhatsApp usando `contact_phone`, desactivados en modo pruebas
- [x] Ticket con `public_ref`, categoría, prioridad, ubicación e historial (`ticket_events`)
- [ ] **Pendiente:** conversación real con el agente (hoy solo el formulario). Requiere que el
      CEO provea `ANTHROPIC_API_KEY`; el código ya está listo y probado para degradar sin ella.
- [ ] **Pendiente:** bandeja de mensajes 1:1 y comunicados (E4, módulo Owner)
- [ ] **Pendiente:** vista del propietario para leer/resolver estos tickets (E4)

### E6 — Banderas, modo mock y submenú de pagos
- [ ] `OWNER_PROPERTY_MANAGE_ENABLED`: oculta el módulo **y** devuelve 403 en servidor
- [ ] `DATA_MODE=mock` → usa `platform/data/platform-mock.db`, **nunca** `platform.db`
- [ ] Validación de altas en mock: solo dominios de prueba y teléfonos `+52 555 01xx xxxx`
- [ ] Banda permanente "MODO PRUEBAS — datos ficticios" en toda la interfaz
- [ ] Mailer en modo desarrollo y enlaces de WhatsApp deshabilitados mientras `DATA_MODE=mock`
- [ ] `POST /admin/mock/purgar` — borrado total de datos de simulación en un paso
- [ ] `DATA_MODE=live` exige `LEGAL_CLEARANCE_REF`; sin él la app **no arranca**
- [ ] Submenú Admin → Pagos: `/admin/pagos/metodos` y `/admin/pagos/requisitos`
- [ ] `PAYMENTS_MODULE_ENABLED=false` mantiene cerradas las rutas de cobro

### E7 — Blindaje de `Property.owner_id` (hallazgo del grafo, `DESIGN.md §11`)
- [ ] `owner_id` jamás se lee de un campo del formulario; solo de una acción explícita de Admin
- [ ] Toda reasignación queda en `audit_log`
- [ ] Reasignar propiedad → revisar/reasignar sus tickets abiertos (no dejarlos huérfanos)
- [ ] `sync-site-properties` **no puede escribir `owner_id`** (prueba de regresión que lo verifique)

## Convenciones

- Español para lo que ve el usuario; inglés para nombres de código.
- Toda cadena visible existe en ES y EN.
- Sin frameworks JS nuevos: Jinja2 + JS mínimo, como ya está.
- Dependencias fijadas en `requirements.txt`. Nuevas: `authlib` o `httpx`+`python-jose` (OIDC),
  `pyotp` (TOTP), `Pillow` (imágenes), `anthropic` (agente AI).
- Sin `|safe` sobre contenido de usuario.
