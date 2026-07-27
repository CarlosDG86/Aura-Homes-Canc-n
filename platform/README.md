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

- `GET /login` — email/password form, posts to the existing
  `POST /api/auth/login` JSON endpoint from an inline handler, sets the
  session cookie, redirects to `/admin` or `/owner` based on role.
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

- `POST /api/auth/login` — email + password, sets a signed session cookie.
- `POST /api/auth/logout` — clears the session.
- `GET /api/auth/me` — current user, 401 if not logged in.
- Routes are gated with a `require_role()` FastAPI dependency: 401 if not
  logged in, 403 if logged in with the wrong role.
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
