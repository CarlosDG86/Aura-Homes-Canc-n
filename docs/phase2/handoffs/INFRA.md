# Handoff a Infra — Phase 2

**Fecha:** 2026-08-08 · Lee primero `../DESIGN.md`, `../SECURITY.md`, `../INFRA_STACK.md`.

> **Regla vigente del repositorio:** no desplegar, no comprar dominios, no tocar DNS. Prepara todo y
> entrega al CEO los pasos exactos para que él apruebe o ejecute.

## 1. Tensión a resolver: SQLite + fotos + capa gratuita

Phase 2 añade **archivos** (fotos de tickets) junto a la base SQLite. Ambos requieren **disco
persistente**, que es justo lo que la mayoría de capas gratuitas no ofrece.

- **Render (capa gratuita):** disco efímero. La base y las fotos **se pierden** en cada despliegue.
  Inviable sin el disco de pago.
- **Fly.io (asignación gratuita):** volumen persistente de 1–3 GB. **Recomendado**, como ya
  concluía `INFRA_STACK.md §5`.

Presupuesto de espacio a validar antes de comprometerse:

| Concepto | Estimación |
|---|---|
| `platform.db` | < 50 MB en el piloto |
| Fotos (5 por ticket, ~250 KB tras re-codificar) | ~1.25 MB por ticket |
| 100 tickets/mes | ~125 MB/mes → **1 GB ≈ 8 meses** |

Se necesita **alerta al 70 % de ocupación** y una política de retención. Si el volumen se queda
corto, la migración natural es Cloudflare R2 (10 GB gratis), diseñada para no requerir cambios en el
modelo de datos (solo cambia `ticket_photos.file_path` por una clave de objeto).

## 2. Entregables

### 2.1 Variables de entorno (documentar, no publicar valores)
```bash
SECRET_KEY=                  # aleatoria; la app NO debe arrancar con el valor por defecto
DATABASE_URL=
ADMIN_LOGIN_PATH=            # ruta oculta del admin
ADMIN_IP_ALLOWLIST=          # opcional
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=
ANTHROPIC_API_KEY=
AI_AGENT_ENABLED=true
AI_MONTHLY_BUDGET_USD=15
OWNER_PROPERTY_MANAGE_ENABLED=true   # el CEO decide si el owner administra propiedades
TENANT_MODULE_ENABLED=true           # encendido para pruebas (decisión CEO 2026-08-08)
DATA_MODE=mock                       # mock | live — 'live' exige LEGAL_CLEARANCE_REF
LEGAL_CLEARANCE_REF=                 # vacío = la app se niega a arrancar en modo 'live'
MOCK_DATABASE_URL=sqlite:///data/platform-mock.db   # NUNCA platform.db
PAYMENTS_MODULE_ENABLED=false        # submenú de config sí; cobro no
SMTP_HOST= SMTP_PORT= SMTP_USER= SMTP_PASSWORD= SMTP_FROM=
UPLOAD_DIR=/data/uploads
```
Ningún valor real en el repositorio. `platform/.env` sigue en `.gitignore`.

### 2.2 Google Cloud (preparar, que el CEO apruebe la creación)
- Proyecto + pantalla de consentimiento OAuth (externa, modo producción)
- ID de cliente OAuth 2.0 tipo aplicación web
- URI de redirección: `https://<dominio>/auth/google/callback`
- Ámbitos mínimos: `openid`, `email`, `profile`. **Nada más.**
- Entregar al CEO la lista de pasos con capturas; él crea las credenciales y las comparte.

### 2.2b Dos bases de datos a partir de ahora
`platform.db` (datos reales del CEO) y `platform-mock.db` (simulación). Ambas en `.gitignore`.
**Solo `platform.db` se respalda.** La de simulación es desechable por diseño — si hay que
restaurarla, se purga y se vuelve a sembrar. Verificar que el proceso de respaldo no las confunda.

### 2.3 Respaldos (bloqueante para producción)
- `sqlite3 .backup` diario (no copiar el archivo en caliente) + `tar` de `uploads/`
- Cifrado en reposo, copia **fuera del host**
- Retención 30 días
- **Restauración probada mensualmente por QA.** Un respaldo sin restaurar no cuenta.

### 2.4 Dominio y TLS
- Subdominio propuesto: `app.aurahomescancun.com` (aislado del sitio estático)
- TLS automático, HSTS, redirección HTTP→HTTPS
- Preparar los registros DNS exactos **para que el CEO los aplique**

### 2.5 Operación
- Registro estructurado sin datos personales ni secretos
- Comprobación de salud `/api/health` (ya existe) + alerta si cae
- Alerta de disco al 70 %
- `pip-audit` en cada despliegue
- Tablero de gasto del agente AI (desde `ai_usage`)

## 3. Costos a presentar al CEO

| Concepto | Estimado mensual |
|---|---|
| Hosting Fly.io (asignación gratuita) | $0 — confirmar que el volumen entra |
| Dominio/subdominio | $0 (ya se posee el dominio) |
| Google SSO | $0 |
| SMTP (Gmail con contraseña de aplicación) | $0 en volumen bajo |
| **API de Anthropic (agente AI)** | **~$1–2 USD** a 100 tickets/mes |
| **Total** | **≈ $1–2 USD/mes** |

Este es el primer costo recurrente real del proyecto. Es pequeño, pero **rompe el "$0"**: el CEO
debe conocerlo y aprobarlo explícitamente, junto con el método de pago de la API.
