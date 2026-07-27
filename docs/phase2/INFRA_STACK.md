# Phase 2 — Infra Stack Decision (2a, scaffolding 2b/2c)

**Status:** Planning only. Nothing in this document has been deployed,
provisioned, or purchased. See §6.

## 1. Backend framework: **FastAPI**

Not Flask. Reasons: FastAPI gives request validation + typed schemas
(Pydantic) essentially for free, which matters a lot here because the
schema in `DB_SCHEMA.md` has ~11 entities and role-based access rules —
hand-rolling validation in Flask invites bugs. FastAPI's dependency-
injection pattern also maps cleanly onto "require role=admin/owner" auth
checks per route. Cost vs. Flask: one more concept to learn (async), but
the toolchain stays small — `fastapi`, `uvicorn`, `sqlalchemy`,
`passlib[bcrypt]`, `python-multipart`, `itsdangerous` (or
`starlette-session`) is the whole dependency list. Still plain Python,
still no Node/JS backend toolchain. This is the one open call the task
asked me to make — made.

## 2. Database: **SQLite**, confirmed

SQLite satisfies "locally hosted" literally: it's a single file shipped
inside the app's own storage, not a network service, not a third-party
product, not billed separately. Access via SQLAlchemy so a future move to
Postgres (if traffic/concurrency ever demands it) is a config change, not
a rewrite. No proposal to use anything else — the CEO's constraint is
narrow enough that SQLite is the direct answer, not one option among many.

Caveat that must be flagged now (see §5): SQLite's durability depends
entirely on the disk it sits on being persistent. On most free-tier PaaS
hosts, disk is ephemeral by default.

## 3. Auth for 2a

- Password hashing: `passlib` with `bcrypt` scheme.
- Sessions: server-side, signed cookies via Starlette's
  `SessionMiddleware` (`itsdangerous` under the hood) — no external
  session store (no Redis) needed at this scale (2a = admin + owner users
  only, low volume).
- Roles enforced with a FastAPI dependency (`require_role("admin")`,
  `require_role("owner")`) checked per route against `users.role`.
- No OAuth/SSO, no JWT, no password-reset email flow yet — plain
  session-cookie login is sufficient for 2a and keeps the stack minimal.
  Password reset can be added in 2b once email sending is needed anyway
  (for tenant notifications).

## 4. Repo layout — new top-level app, static site untouched

```
/data, /build.py, /dist          # unchanged — public showcase site, stays static
/platform/                       # NEW — Phase 2 backend, fully separate
  app/
    main.py                      # FastAPI app entrypoint
    models.py                    # SQLAlchemy models (from DB_SCHEMA.md)
    auth.py                      # login, session, role dependencies
    routers/
      admin.py
      owner.py
      tenant.py                  # 2b — scaffolded, no PII stored yet
      payments.py                # 2c — scaffolded, no payment data stored yet
    db.py                        # SQLite engine/session setup
  data/
    platform.db                  # SQLite file — gitignored, never committed
  requirements.txt
  .env.example                   # SECRET_KEY, DATABASE_URL — no real secrets committed
  README.md                      # how to run platform/ locally
```

Rationale: `build.py`/`data/*.json`/`dist/` is the public site's entire
world and must keep working unmodified — no shared imports, no shared
config, no shared deploy pipeline. `platform/` is a self-contained Python
app with its own `requirements.txt` and its own deploy target (see §5).
Two `README.md`s, two mental models, zero risk of a platform change
breaking the showcase build. `platform/data/platform.db` is gitignored;
2b/2c routers exist in code (scaffolded, return `501`/empty state) but
write no real tenant PII or payment rows until Legal clears each phase —
enforced by simply not building the data-writing logic yet, not by a
feature flag that could be flipped by accident.

## 5. Free-tier hosting (name only — do not provision)

1. **Render (free web service tier)** — supports a Python/FastAPI +
   Uvicorn app directly, includes free-tier disks are NOT persistent
   across deploys/restarts on the free plan; would need Render's paid
   persistent disk add-on for durable SQLite. **On free tier, treat
   `platform.db` as disposable** unless CEO later approves a paid disk
   or accepts periodic backup-to-git as a workaround.
2. **Fly.io (free allowance)** — supports persistent volumes even on
   the free allowance (small volume, e.g. 1-3GB), which makes it the
   better fit for durable SQLite specifically. Slightly more setup
   (flyctl CLI, `fly.toml`) than Render.

**Recommendation once CEO is ready to deploy 2a: Fly.io**, specifically
because it's the one of these two where SQLite durability doesn't require
a paid upgrade. Flagging clearly: "free tier" + "durable SQLite" is a
real tension on most PaaS free tiers — Fly.io is the option that resolves
it without moving off free tier, but the CEO should know this constrained
the choice.

## 6. No deployment performed

This document is planning only. No hosting account, domain, or service
has been provisioned or will be provisioned by Infra without explicit CEO
approval, per this repo's standing rule. When 2a is ready to ship, Infra
will return with exact account-creation and deploy steps for CEO sign-off.
