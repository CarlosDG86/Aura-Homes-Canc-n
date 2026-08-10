# Publicar en internet — pasos exactos para el CEO

**Fecha:** 2026-08-10 · **Estado: preparado, NADA desplegado.**
Según la regla del repositorio, Infra prepara y el CEO ejecuta o aprueba. No se
ha creado ninguna cuenta, comprado ningún dominio ni tocado ningún DNS.

---

## 0. Resumen honesto: qué puede salir hoy y qué no

Son **dos aplicaciones distintas** y su riesgo no se parece en nada.

| | Sitio público | Plataforma (API + login) |
|---|---|---|
| Qué es | HTML estático | Login, base de datos, datos personales |
| Si alguien la ataca | Ve lo que ya es público | Accede a datos de propietarios e inquilinos |
| ¿Lista para internet? | **Sí** | **No todavía** — ver §1 |

**Recomendación: publica el sitio público ahora y deja la plataforma para
después de cerrar la etapa E2 (identidad).** No es prudencia excesiva: hay dos
problemas concretos, no hipotéticos, descritos abajo.

---

## 1. Bloqueadores de la plataforma (no del sitio público)

### 1.1 🔴 La cuenta de administrador usa la contraseña de ejemplo
Se verificó el 2026-08-10: `admin@aura-homes-cancun.local` sigue con
`ChangeMe123!`. Esa contraseña está escrita en `platform/README.md`, o sea **en
el repositorio**. Publicar el login sin cambiarla equivale a publicar la llave
junto a la puerta.

**Cómo se corrige:** iniciar sesión, ir a Admin → Usuarios → esa cuenta →
restablecer contraseña. Toma un minuto y es obligatorio.

### 1.2 🔴 La etapa E2 (identidad) no está construida
El diseño aprobado (`DESIGN.md §3.2`, `SECURITY.md §1.3`) pide tres cosas para
el acceso de administrador que **hoy no existen en el código**:

| Control aprobado | Estado |
|---|---|
| URL de admin no enlazada (`ADMIN_LOGIN_PATH`) | ❌ No implementado — el admin entra por `/login`, igual que todos |
| Segundo factor (código de 6 dígitos) obligatorio | ❌ No implementado |
| Acceso con Google (SSO) | ❌ No implementado |

Hoy la única defensa de la cuenta de administrador es una contraseña. En tu
equipo eso basta; expuesto a internet, no. El límite de intentos y el bloqueo
por IP ya funcionan y ayudan, pero no sustituyen al segundo factor.

### 1.3 🟡 Hay datos personales reales en la base
`platform.db` contiene a Mayra Pichardo con su correo real. No es un dato de
prueba: es una persona. Publicar la plataforma con esa base es tratamiento de
datos personales, con las obligaciones que eso implica (LFPDPPP).

`DATA_MODE=mock` **no protege esa base**: solo impide capturar datos reales
*nuevos*. Los que ya están, ahí siguen.

---

## 2. Publicar el sitio público (se puede hacer hoy)

Es HTML estático: sin login, sin base de datos, sin datos personales.

### Opción recomendada: Cloudflare Pages (gratis)
1. Entra a `dash.cloudflare.com` → **Workers & Pages** → **Create** → **Pages**.
2. **Connect to Git** → autoriza y elige `CarlosDG86/Aura-Homes-Canc-n`.
3. Configuración de compilación:
   - Build command: `python build.py`
   - Build output directory: `dist`
   - Rama de producción: `main`
4. **Save and Deploy**. Queda en `<proyecto>.pages.dev`.
5. Para tu dominio propio: **Custom domains** → añadir → Cloudflare indica los
   registros DNS exactos.

**HTTPS es automático.** No hay servidor que mantener ni costo.

> Alternativa equivalente: Netlify, con los mismos tres valores del paso 3.

### Antes de publicar el sitio
- [ ] Quitar la propiedad de prueba "Casa Bien Chida" de `data/properties.json`
- [ ] Optimizar `logo.png` (hoy 1.5 MB; debería estar por debajo de 100 KB)
- [ ] Actualizar `brand.platformUrl` en `data/site.json`: hoy apunta a
      `http://localhost:8010`, así que el botón **Ingresar** no funcionará para
      nadie fuera de tu equipo
- [ ] `python build.py` y revisar `/es/` y `/en/`

---

## 3. Publicar la plataforma (cuando se levanten los bloqueadores)

Todo está preparado: `platform/Dockerfile` y `platform/fly.toml`.

### 3.1 Instalar Fly.io y entrar
```powershell
winget install --id Fly.Flyctl
fly auth signup      # o: fly auth login
```

### 3.2 Crear la aplicación y el volumen
```powershell
cd C:\Aura\claude-code\platform
fly launch --no-deploy --name aura-homes-plataforma --region qro
fly volumes create aura_data --size 1 --region qro
```
El volumen es lo que hace que la base y las fotos sobrevivan a cada
actualización. Sin él se pierden.

### 3.3 Secretos (nunca en el repositorio)
```powershell
# Llave de sesión: si es débil, cualquiera puede falsificar una sesión de admin
python -c "import secrets; print(secrets.token_urlsafe(64))"
fly secrets set SECRET_KEY="<lo que imprimió>"

fly secrets set SEED_ADMIN_EMAIL="tu-correo@dominio.com"
fly secrets set SEED_ADMIN_PASSWORD="<una contraseña larga y única>"

# Correo saliente (opcional en modo pruebas)
fly secrets set SMTP_HOST="smtp.gmail.com" SMTP_PORT="587" `
                SMTP_USER="tu-correo@gmail.com" `
                SMTP_FROM="tu-correo@gmail.com" `
                SMTP_PASSWORD="<contraseña de aplicación de 16 caracteres>"

# Agente AI (opcional; ~$1-2 USD/mes)
fly secrets set ANTHROPIC_API_KEY="sk-ant-..."
```
La aplicación **se niega a arrancar** si `SECRET_KEY` falta o es la de ejemplo.
Es intencional: mejor un fallo ruidoso que un despliegue vulnerable.

### 3.4 Desplegar
```powershell
fly deploy
fly open /api/health      # debe responder {"status":"ok"}
```

### 3.5 Inmediatamente después
- [ ] Entrar y **cambiar la contraseña del administrador**
- [ ] Verificar que la banda "MODO PRUEBAS" se ve (confirma `DATA_MODE=mock`)
- [ ] `fly logs` sin errores
- [ ] Conectar el sitio público: actualizar `brand.platformUrl` en
      `data/site.json` con la URL real y recompilar

---

## 4. Respaldos (obligatorio antes de operar con datos reales)

Un volumen no es un respaldo: si se borra la aplicación, se va con ella.

```powershell
fly ssh console -C "sqlite3 /data/platform.db '.backup /data/backup.db'"
fly ssh sftp get /data/backup.db ./backup-$(Get-Date -Format yyyyMMdd).db
```
Guardar fuera del host, cifrado. **Y probar la restauración**: un respaldo que
nunca se restauró no es un respaldo, es una suposición.

---

## 5. Costos

| Concepto | Mensual |
|---|---|
| Sitio público (Cloudflare Pages) | $0 |
| Plataforma (Fly.io, se apaga sin tráfico) | $0 dentro de la asignación gratuita |
| Volumen de 1 GB | $0 dentro de la asignación gratuita |
| Dominio | ya lo posees |
| API del agente AI (opcional) | ~$1–2 USD |

El único costo recurrente es el agente AI, y solo si se activa.

---

## 6. Lo que falta antes de considerar esto "listo para producción"

1. Cambiar la contraseña del administrador (§1.1)
2. Construir E2: URL oculta de admin, segundo factor, Google SSO (§1.2)
3. Visto bueno de QA — no se ha ejecutado la lista de `handoffs/QA.md`
4. Visto bueno de Legal antes de `DATA_MODE=live`
5. Respaldo automático con restauración probada
6. Decidir qué hacer con los datos reales que ya están en `platform.db` (§1.3)
