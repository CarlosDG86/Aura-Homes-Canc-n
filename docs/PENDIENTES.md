# Pendientes — prioridades para la próxima sesión

**Actualizado:** 2026-09-08
**Estado general:** desarrollo local. La Fase 2.1 está **diseñada y sin construir**.

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

### 1.1b Siguiente: E9 — cuentas, aislamiento y migración

**Desbloqueada** al cerrarse D-018, D-019 y D-020 el 2026-09-08. Es la raíz de la que
dependen E11, E12, E13 y E14. 5 días.

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
