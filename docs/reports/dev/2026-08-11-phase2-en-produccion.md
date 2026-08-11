# Desarrollo e Infraestructura — Reporte de estado

**Fecha:** 2026-08-11
**Periodo:** Phase 2 completa (diseño, construcción y publicación)
**Archivado en:** Aura/Reports/Development/2026-08-11.md

---

## 1. Resumen (3 líneas)

**En marcha.** La plataforma de gestión y el sitio público están publicados en
internet, conectados entre sí y con HTTPS. 237 pruebas automatizadas en verde.
**Opera en modo simulación:** no puede guardar datos reales de inquilinos hasta
que Legal firme, por diseño y no por disciplina.

| | Dirección |
|---|---|
| Sitio público | `https://aura-homes-cancun.carlosdg0101.workers.dev` |
| Plataforma | `https://aura-homes-plataforma.fly.dev` |

**Costo mensual: $0** (ambos en capas gratuitas).

---

## 2. Completado

### 2.1 Cimientos de seguridad (etapa E1)

Lo que existía antes de esta fase tenía huecos serios. Se corrigieron:

| Control | Antes | Ahora |
|---|---|---|
| CSRF | **No existía** | Middleware en todos los formularios |
| Revocar sesiones | Imposible | Tabla `sessions`; revocar expulsa al instante |
| Fuerza bruta | Sin límite | 5 fallos → bloqueo; 10/min por IP |
| `SECRET_KEY` | Valor de ejemplo público | La app **no arranca** con él en producción |
| Cabeceras | Ninguna | CSP, HSTS, nosniff, frame-ancestors |
| Auditoría | No existía | `audit_log` con accesos y acciones sensibles |

Restablecer una contraseña **cierra todas las sesiones** de esa cuenta: si se
restablece porque se comprometió, dejar sesiones vivas anularía el propósito.

### 2.2 Aislamiento entre propietarios (`scoping.py`)

El control más importante del sistema. El filtro de pertenencia estaba
**copiado cinco veces solo en un archivo**; ahora vive en un módulo con cuatro
funciones. Auditar la seguridad de acceso pasó de revisar 60 rutas a revisar 4.

Verificado con dos propietarios y dos inquilinos: un identificador ajeno
devuelve **404, no 403** (un 403 confirmaría que el objeto existe).

### 2.3 Módulo de inquilinos (2b)

Tickets de mantenimiento con fotos, historial y comentarios. Las fotos se
**re-codifican al subirlas**, lo que destruye archivos disfrazados y borra el
EXIF —incluidas las coordenadas GPS: publicar dónde vive un inquilino sería una
fuga de datos personales. Se sirven por una ruta con autorización, nunca como
archivos públicos.

**Detección de emergencia del lado del servidor:** un reporte que menciona gas,
fuego o inundación se eleva a emergencia aunque el inquilino haya elegido
prioridad baja.

Agente AI (`claude-haiku-4-5`, ~$0.012 por ticket) construido y probado; hoy
inactivo por falta de llave de API, con formulario manual como respaldo.

### 2.4 Portal del propietario (E4)

Alta de inquilinos, gestión y resolución de tickets (**resolver exige explicar
qué se hizo**), reporte por unidad con descarga CSV, comunicados, mensajes 1:1
y asignación de responsable. Bandejas en ambos sentidos con contador de no
leídos.

### 2.5 Identidad reforzada (etapa E2)

| Control | Estado |
|---|---|
| Segundo factor obligatorio para administrador | ✅ Activo |
| Puerta de administración no enlazada | ✅ Opcional (`ADMIN_LOGIN_PATH`) |
| Acceso con Google (SSO) | ✅ Construido; requiere credenciales |

**La contraseña por sí sola ya no autentica a un administrador.** Probado: con
la contraseña correcta pero sin el código, no se entra.

Google SSO se probó contra un proveedor simulado (llaves propias firmando
tokens como lo haría Google): firma falsificada, token de otra aplicación,
token caducado, `nonce` ajeno, `state` repetido y correo sin verificar, todos
rechazados. **No crea cuentas**: un correo no registrado se rechaza.

### 2.6 Publicación

`Dockerfile`, `fly.toml`, `wrangler.jsonc`, workflow de GitHub Actions y
`docs/phase2/DEPLOY.md` con los pasos exactos.

---

## 3. En curso

Nada en construcción. El sistema está estable y publicado.

---

## 4. Bloqueadores

| Bloqueador | Qué impide | Qué lo desbloquea |
|---|---|---|
| **Visto bueno de Legal** | Operar con datos reales de inquilinos | Aviso de privacidad y consentimiento validados (LFPDPPP) |
| **Sin llave de Anthropic** | El agente AI conversacional | Aprobación del CEO (~$1–2 USD/mes) |
| **Sin credenciales de Google** | Acceso con Google | Crear el proyecto en Google Cloud (§7 de DEPLOY.md) |
| **Sin visto bueno de QA** | Considerar esto "listo para producción" | Ejecutar la lista de `handoffs/QA.md` |

Ninguno impide **usar** la plataforma hoy en modo simulación.

---

## 5. Decisiones que esperan al CEO

**5.1 Respaldos automáticos** — hoy no hay ninguno. Si se pierde el volumen de
Fly, se pierden los datos.
- A: Respaldo manual periódico (gratis, depende de acordarse)
- B: Automatizar con GitHub Actions a un almacenamiento cifrado (~1 hora de trabajo, $0)
- **Recomendación: B.** Un respaldo que depende de la memoria no es un respaldo.

**5.2 Datos reales que ya están en `platform.db` local** — contiene a una
persona real con su correo. No está publicado, pero existe.
- A: Dejarlo hasta que Legal firme
- B: Depurarlo y empezar limpio en producción
- **Recomendación: A**, sin urgencia: no salió del equipo del CEO.

**5.3 Logo de 1.5 MB** — 22 veces el tamaño recomendable; comprometería el
criterio Lighthouse 90+. Hoy **no está publicado**.
- **Recomendación:** optimizarlo antes de subirlo (trabajo de minutos).

**5.4 Casa de prueba "Casa Bien Chida"** — sigue en la copia local del CEO, sin
publicar. Decidir si se borra o se convierte en propiedad real.

---

## 6. Próximos pasos

1. **El CEO prueba el segundo factor** con el teléfono a mano y **guarda la
   clave de respaldo**. Es lo único que aún no se ha ejercitado en producción.
2. Recorrido funcional completo con datos ficticios (§ pruebas de `QA.md`).
3. Respaldos automáticos (decisión 5.1).
4. Activar Google SSO si el CEO lo quiere.

---

## 7. Costo

| Concepto | Mensual |
|---|---|
| Sitio público (Cloudflare) | $0 |
| Plataforma (Fly.io, se apaga sin tráfico) | $0 |
| Volumen 1 GB | $0 |
| **Total actual** | **$0** |
| Agente AI (opcional, si se activa) | ~$1–2 USD |

El agente AI sería **el primer costo recurrente del proyecto**. Requiere
aprobación explícita y método de pago.

---

## 8. Nota de transparencia sobre el proceso

El primer despliegue falló **tres veces**, siempre por el mismo patrón: código
que funcionaba en el equipo del CEO y fallaba dentro del contenedor. Las causas
fueron una ruta que se salía a la raíz del sistema, permisos del volumen y una
dependencia (`httpx`) instalada a mano pero no declarada.

Lo que cambió: ahora se verifica con **entorno virtual limpio + disposición de
contenedor** antes de proponer un despliegue. El workflow de GitHub Actions
incluye esa misma comprobación, y habría detectado dos de los tres fallos.

También se corrigieron dos errores propios encontrados al revisar:
la contraseña del administrador quedaba escrita en los registros del servidor,
y la política de seguridad bloqueaba los diálogos de confirmación, de modo que
las acciones destructivas se ejecutaban sin preguntar.
