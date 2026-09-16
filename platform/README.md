# Aura Homes Cancún — Platform (Phase 2)

**Status: Phase 2a is fully functional locally. Phase 2b (tenant) and 2c
(payments) are scaffolded only — every route under `/api/tenant` and
`/api/payments` returns `501` and touches no database table. Not deployed
anywhere. Not linked to or shared with the public showcase site
(`../data`, `../build.py`, `../dist`), which is untouched by this app.**

## What's here

```
platform/
  app/
    main.py            FastAPI entrypoint, session middleware, startup seed
    models.py           SQLAlchemy models (users/properties/... + 2b/2c shape)
    schemas.py           Pydantic request/response models
    auth.py              login/logout, password hashing, require_role()
    db.py                SQLite engine + session
    routers/
      admin.py           role=admin: properties CRUD, owners directory, users/roles
      owner.py            role=owner or admin: properties CRUD scoped to self
      tenant.py            2b — stub, 501 on every route
      payments.py           2c — stub, 501 on every route
  data/                  SQLite file lives here (gitignored, not committed)
  requirements.txt
  .env.example
```

## Install & run

From `platform/` (not the repo root):

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

The API is at `http://127.0.0.1:8010`. Interactive docs at
`http://127.0.0.1:8010/docs`.

Port 8010 (not 8000) is deliberate: the public showcase site's local preview
server (`python build.py --serve`, in the repo root, separate from this app)
runs on port 8000, so the two can run side by side without conflicting.

## Browser UI (login + dashboards)

Server-rendered HTML pages (Jinja2 templates, no JS framework) live
alongside the JSON API so a human can actually log in and see something:

- `GET /login` — email/password form. `POST /login` is the only way in: it
  applies the per-IP throttle, the account lockout, `is_active`, the admin
  gate, TOTP and the server-side `sessions` row, then redirects to `/admin`,
  `/owner` or `/inquilino` based on role.
- `GET /admin` — role=admin only. Read-only dashboard: properties, owners,
  users tables. Queries the DB directly (same models/session pattern as
  `routers/admin.py`), not via an internal HTTP call.
- `GET /owner` — role=owner or admin. Same idea, scoped to the logged-in
  user's own properties via the same `Property.owner_id == current_user.id`
  pattern as `routers/owner.py`.
- `GET /logout` — clears the session, redirects to `/login`.

Login URL: `http://127.0.0.1:8010/login`

On first run, the app creates `platform/data/platform.db` (SQLite, gitignored)
and seeds **one admin user** so the CEO can log in and test. Credentials
print to the console on first startup, and default to the values in
`.env.example`:

- email: `admin@aura-homes-cancun.local`
- password: `ChangeMe123!`

**Change this password before any real deployment.** To use different seed
credentials, set `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` env vars before
starting the app (see `.env.example` — note there is no dotenv loader wired
in, so these must be exported in your shell, not just placed in a `.env`
file, unless that's added later).

## Auth model

- `POST /login` — the single entry point (HTML form). See E8 below.
- `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` —
  **retired in E8**; they return 404 unless `LEGACY_JSON_AUTH_ENABLED=true`,
  which exists only as a deployment rollback.
- Session resolution lives in **one** place, `security.resolve_session_user`:
  active account, live `sessions` row (revocation + idle/absolute expiry) and
  admin TOTP. Both the HTML pages and the JSON API call it.
- Routes are gated with a `require_role()` FastAPI dependency: 401 if not
  logged in, 403 if logged in with the wrong role.

> **Why E8 exists.** `POST /api/auth/login` used to check e-mail and password
> and nothing else — no throttle, no lockout, no `is_active`, no TOTP, no
> `sessions` row (so revoking sessions did not close it) and no audit trail.
> Measured: 20 failed calls returned 401 twenty times with no `429`, while the
> same attack on the HTML form stopped at the fifth; and a disabled, locked-out
> admin account read `/api/admin/users` through it. `tests/test_e8.py` keeps
> that path closed.
- `admin` router: role=admin only, sees/edits everything.
- `owner` router: role=owner or admin, but every query is scoped to
  `Property.owner_id == current_user.id` — this is what actually prevents
  cross-owner data leakage, not the role check alone.
- `tenant` / `payments` routers: no auth check needed since no route does
  anything but return a 501 stub — nothing to gate yet.

## This is 2a + scaffolded 2b/2c, not deployed anywhere

Per CEO-approved sequencing (`docs/phase2/PLAN.md`): 2a (admin/owner
property + user management) is real and working. 2b (tenant portal) and 2c
(payments) are wired into the app as routers so the shape exists, but store
no tenant PII or payment data — Legal review is required before either goes
live. No hosting, domain, or deploy pipeline has been set up; that is
infra's job once QA signs off and the CEO approves a deploy.

## Recuperación de contraseña (E10)

```
GET/POST /recuperar            — pedir el enlace. SIEMPRE responde igual
GET      /recuperar/enviado    — mensaje genérico, exista o no la cuenta
GET      /recuperar/{token}    — valida y saca el token de la URL. NO lo consume
GET/POST /recuperar/nueva      — elegir la contraseña nueva
GET      /recuperar/caducado   — destino único de todo enlace que no vale
GET/POST /cambiar-contrasena   — cambio voluntario, exige la contraseña actual
GET      /admin/correos        — buzón de salida (solo admin y solo en simulación)
```

Reglas que no son negociables:

- **El enlace no concede sesión.** Solo permite escribir una contraseña nueva.
  Nunca autologin, nunca administrador, nunca salta el segundo factor.
- **Todas las respuestas de `POST /recuperar` son idénticas**: mismo código,
  mismo `Location`, mismo cuerpo. Correo inexistente, cuenta inactiva, cuenta
  de administrador y límite superado responden lo mismo que el éxito. Nunca un
  429 con cuerpo distinto: el propio límite sería el oráculo de enumeración que
  este flujo intenta cerrar.
- **El token nunca se guarda**: se guarda su SHA-256.
- **El GET del enlace no lo consume**, porque los previsualizadores de correo
  siguen las URL y lo quemarían antes de que la persona lo abriera.
- El envío va en `BackgroundTasks`: `smtplib` es síncrono con 15 s de espera, y
  enviar en línea haría que un correo existente tardara y uno inexistente no —
  un oráculo cronometrable.
- **El administrador queda fuera** (D-022). Su rescate es
  `scripts/restablecer_admin.py`, que exige estar en la consola del servidor.
- **En modo simulación no sale ningún correo**, y la guarda vive dentro de
  `email_utils`, no en quien llama.
