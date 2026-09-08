# Pendientes — prioridades para la próxima sesión

**Actualizado:** 2026-08-12
**Estado general:** el proyecto pasa a **desarrollo local**. Nada desplegado se
toca; se congela como está.

---

## 0. Contexto: qué está arriba y qué no

| | Estado |
|---|---|
| Sitio público (Cloudflare Worker `aura-homes-cancun`) | 🟢 Arriba, congelado |
| Plataforma (Fly `aura-homes-plataforma`) | 🔴 **Suspendida** — terminó el periodo de prueba de Fly |
| Respaldos automáticos | ⚫ Cancelados por el CEO |
| Datos del volumen de Fly | ⚫ Inaccesibles y **no se necesitan** (decisión del CEO) |

**Decisión tomada el 2026-08-12:** no se recupera nada de producción, no se
destruye nada, y el trabajo continúa en local con retroalimentación de usuarios.

> ⚠️ Un `push` a `main` **republica el sitio público**: Cloudflare está
> conectado al repositorio. Para trabajar sin publicar, usar una rama.

---

## 1. Prioridad alta

### 1.1 El correo del sitio no existe

`hola@aurahomescancun.com` aparece en el pie de todas las páginas, en el
formulario y en el botón de contacto. **El dominio no está registrado**
(verificado en dos resolutores DNS: sin registro A, sin MX).

El formulario tampoco envía por su cuenta — abre el cliente de correo del
visitante hacia esa dirección. Resultado: **toda consulta que no llegue por
WhatsApp se pierde sin dejar rastro.**

- Parche inmediato: cambiar `brand.email` en `data/site.json` por un correo que
  exista.
- Solución: registrar el dominio (12–15 USD al año).

### 1.2 Seis de siete fichas no son inventario real

Solo `AUR-001` (La Rioja) es real. Dos son demos con imágenes grises y cuatro
son de prueba, con precios y zonas inventados — llevan `"mock": true` en
`data/properties.json` para poder filtrarlas de un golpe.

`build.py` ya respeta un campo `placeholder` para ocultar fichas sin borrarlas
(`LIVE = [p for p in props if not p.get("placeholder")]`).

---

## 2. Prioridad media

### 2.1 CI ya no ejecuta las pruebas

El paso `Suite completa` se retiró de `.github/workflows/deploy.yml`. Las 261
comprobaciones siguen en `platform/tests/` pero nada las corre solo.

A mano: `cd platform && python tests/run_all.py`

### 2.2 El logo está oculto en el sitio publicado

`.brand-logo{height:1px}` en `dist/assets/css/styles.css`. Con la cabecera
actual de 120 px, unos 80 px de logo quedan proporcionados.

### 2.3 Lighthouse nunca se ha medido

El plan pide 90+ en móvil. Se quitaron los dos frenos evidentes (cabecera de
216 px y logo de 1.5 MB), pero **eso no es lo mismo que haberlo comprobado**.

### 2.4 Aviso de privacidad y términos

Ambas páginas dicen que el texto "se publicará muy pronto" mientras el
formulario ya pide nombre, correo y teléfono. Depende del texto de Legal.

---

## 3. Prioridad baja

- Tres archivos de logo conviviendo: `logo.png`, `logo1.png`, `logoold.png`.
- `banner.jpg` pesa 280 KB.
- La rama `docs/architecture-and-phase2` está detrás de `main`; el trabajo real
  va en `main`.
- Agente AI de tickets: construido y probado, sin llave de API (1–2 USD/mes).
- Google SSO: construido y probado, sin credenciales.

---

## 4. Cómo retomar en local

Dos terminales, desde `C:\Aura\claude-code`:

```
cd platform && .venv\Scripts\Activate.ps1 && uvicorn app.main:app --reload --port 8010
```

```
python build.py --serve
```

- Plataforma: `http://127.0.0.1:8010` — usa `data/platform-mock.db`
  (`DATA_MODE` por defecto es `mock`), sin segundo factor.
- Sitio: `http://localhost:8000/es/`

**Acceso:** el usuario admin es `admin@aura-homes-cancun.local`. La contraseña
**no es la de siembra** — se cambió y bcrypt no permite recuperarla. Para poner
una nueva:

```
cd platform && python scripts/reset_local_password.py admin@aura-homes-cancun.local
```

La pide por teclado (no se muestra ni queda en el historial) y hace una copia
de la base antes de escribir.

---

## 5. Documentación de referencia

| Tema | Archivo |
|---|---|
| Diseño de la fase 2 | `docs/phase2/DESIGN.md` |
| Seguridad | `docs/phase2/SECURITY.md` |
| Despliegue | `docs/phase2/DEPLOY.md` |
| Respaldo y restauración | `docs/phase2/BACKUP.md` |
| Reportes por departamento | `docs/reports/` y Google Drive `Aura/Reports/` |
| Grafo de conocimiento | `graphify-out/graph.html` (773 nodos) |
