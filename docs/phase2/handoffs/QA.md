# Handoff a QA — Phase 2

**Fecha:** 2026-08-08 · Lee primero `../DESIGN.md`, `../SECURITY.md`, `../AI_TICKET_AGENT.md`.

> El visto bueno de QA es obligatorio antes de proponer cualquier despliegue al CEO.

## 0. Antes de probar

`platform/data/platform.db` contiene **datos reales del CEO**. Nunca pruebes contra esa base:
trabaja sobre una copia (`platform.db.test`) con datos sembrados. Respalda antes de cualquier prueba
que escriba.

---

## 1. Aislamiento entre owners — la prueba más importante

Una sola falla aquí es motivo de rechazo inmediato. Escenario: dos owners (A y B), cada uno con una
propiedad y un inquilino.

| # | Prueba | Resultado esperado |
|---|---|---|
| 1.1 | Owner A abre `/owner/propiedades/{id_de_B}` | **404** (no 403) |
| 1.2 | Owner A intenta vincular un inquilino a una propiedad de B (editando el formulario) | Rechazado en servidor |
| 1.3 | Owner A abre un ticket de una propiedad de B | 404 |
| 1.4 | Owner A abre una foto de un ticket de B (`/media/...`) | 404 / 403 |
| 1.5 | Inquilino de A abre un ticket de un inquilino de B | 404 |
| 1.6 | Inquilino intenta entrar a `/owner` o `/admin` | 403 / redirección |
| 1.7 | Owner A envía un comunicado: ¿llega a inquilinos de B? | **No** |
| 1.8 | Owner A ve en `/owner/inquilinos` a alguien de B | **No** |

**Método:** recorre cada ruta de `DESIGN.md §8` y repítela con un ID ajeno. Ninguna debe filtrar
datos, ni siquiera confirmar la existencia del objeto.

## 2. Autenticación

- Google SSO con correo **no registrado** → acceso rechazado (sin crear cuenta)
- Google SSO con usuario desactivado (`is_active=false`) → rechazado
- 5 contraseñas fallidas → cuenta bloqueada 15 min
- Recuperación de contraseña: mismo mensaje exista o no el correo (sin enumeración)
- Token de recuperación: un solo uso, caduca, no reutilizable
- Admin sin TOTP → no obtiene sesión
- Ruta de admin con contraseña correcta pero TOTP incorrecto → rechazado
- El ID de sesión **cambia** tras iniciar sesión (fijación de sesión)
- Cerrar sesión invalida en servidor (reusar la cookie anterior no funciona)
- Caducidad por inactividad y absoluta

## 3. CSRF y formularios

- POST sin token CSRF → rechazado, en **todos** los formularios
- Token de otra sesión → rechazado
- Campos ocultos manipulados (`owner_id`, `property_id`, `tenant_id`) → ignorados; el servidor toma
  el valor de la sesión

## 4. Carga de fotos

- Archivo `.jpg` que en realidad es HTML/PHP → rechazado (bytes mágicos)
- Nombre con `../../` → guardado con UUID, sin salirse del directorio
- Archivo de 50 MB → rechazado
- 6 fotos en un ticket → rechazado (tope 5)
- **Foto con GPS en EXIF → la copia almacenada NO conserva coordenadas** (fuga de datos personales)
- Imagen enorme (bomba de descompresión) → rechazada sin tumbar el servidor
- Foto solicitada sin sesión → 401/403

## 5. Agente AI

Ver `AI_TICKET_AGENT.md §9`. Mínimo:
- Ticket normal con fotos → categoría y prioridad razonables
- Fuga de gas → `emergencia` + aviso de seguridad + notificación al owner
- Inyección de prompt en texto **y dentro de una imagen** → ticket normal, sin obedecer
- Petición de consejo eléctrico riesgoso → el agente se niega
- Presupuesto agotado / API caída → formulario manual, sin error visible
- Confirmación humana: el ticket **no** se crea sin aprobación del inquilino

## 6. Bilingüe

- Toda cadena nueva existe en ES y EN — **sin excepciones** (regla del proyecto)
- Desplegable "Ingresar / Log in": ambos idiomas, ambas opciones, enlaces correctos
- Correos (invitación, recuperación, comunicados) en el idioma del destinatario (`users.locale`)
- El desplegable funciona con teclado y lector de pantalla

## 7. Modo mock, banderas y puertas legales

**Modo simulación (la prioridad ahora — 2b está encendido en mock):**
- Con `DATA_MODE=mock`, la app usa `platform-mock.db`; **verificar que `platform.db` NO se modifica**
  (comparar su hash antes y después de una sesión completa de pruebas)
- Alta de inquilino con correo real (`@gmail.com`) → **rechazada** con mensaje claro
- Alta con teléfono real → rechazada; solo `+52 555 01xx xxxx`
- Banda "MODO PRUEBAS" visible en **todas** las pantallas
- Ningún correo sale al exterior; enlaces de WhatsApp deshabilitados
- `POST /admin/mock/purgar` elimina todo lo ficticio y nada más
- `DATA_MODE=live` sin `LEGAL_CLEARANCE_REF` → la app **no arranca**

**Banderas:**
- `OWNER_PROPERTY_MANAGE_ENABLED=false` → el módulo desaparece de la interfaz **y**
  `POST /owner/propiedades` construido a mano devuelve **403** (probar ambas capas)
- `PAYMENTS_MODULE_ENABLED=false` → `/api/payments/*` → 501; el submenú de Admin sí abre

**`Property.owner_id` (`DESIGN.md §11`):**
- Enviar `owner_id` como campo oculto en cualquier formulario → **ignorado**
- `sync-site-properties` no altera `owner_id` (comparar antes/después)
- Reasignar una propiedad con tickets abiertos → los tickets no quedan apuntando al dueño anterior
- Toda reasignación aparece en `audit_log`

## 8. Regresión del sitio público

Phase 2 **no debe** romper el escaparate:
- `python build.py` genera sin errores
- `/es/` y `/en/` responden 200; propiedades, detalles y páginas legales intactos
- Formulario de contacto y enlace de WhatsApp siguen funcionando
- Lighthouse móvil 90+ en las cuatro categorías (criterio de terminado del MVP)
- El sitio público **sigue sin base de datos**

## 9. Infraestructura

- Respaldo automático se ejecuta **y la restauración se prueba** (mensual)
- Cabeceras de seguridad presentes (CSP, HSTS, nosniff, frame-ancestors)
- HTTP redirige a HTTPS
- La app se niega a arrancar con `SECRET_KEY` por defecto
- `pip-audit` sin vulnerabilidades altas

---

## Criterio de aprobación

QA firma solo si: **cero** fallas en §1 (aislamiento), **cero** en §2 y §3, **cero** en §7
(puertas legales), y la restauración del respaldo fue probada con éxito. Todo lo demás se reporta
con severidad, siguiendo `docs/REPORT_TEMPLATE.md`, en `docs/reports/qa/`.
