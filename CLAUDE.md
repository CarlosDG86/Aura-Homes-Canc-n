# Aura Enterprise Solutions — aura-web

This repository holds **two independent applications** that share a git repo and nothing else — no code, no configuration, no deployment pipeline. The person you work with is the CEO and sole decision-maker.

1. **The showcase site** (`data/`, `build.py`, `dist/`) — static, public, no login, no database.
2. **The management platform** (`platform/`) — FastAPI + SQLite, login-gated, not public today.

Confusing the two is the most expensive mistake available here: a change to the first republishes a live site, and a change to the second touches a database with the CEO's real owners in it.

## Product (CEO-approved 2026-10-14, do not change without CEO approval)

### The showcase site — unchanged since the MVP
- Showcase website for the CEO's OWN long-term rental properties. No marketplace, no accounts, no payments on this surface.
- Pilot scope: Cancún (Quintana Roo) properties only.
- Bilingual: Spanish (primary, default) and English, with routes `/es` and `/en`.
- Contact: inquiry form + prominent WhatsApp button (dominant rental contact channel in Mexico).
- Mobile-first: most renters browse on phones.

### The platform — what it actually is now
Pivoted on 2026-08-11 (D-010): it is no longer a private tool for the CEO's own houses, it is a **product sold to other property-management companies**. That pivot is what makes everything below necessary.

- **The account (`accounts`) is the isolation boundary**, not the owner user (D-013). One company, several users.
- **Five plans** (D-018): trial of 90 days for one house, Standard, Standard +, Enterprise, Enterprise +. The `+` suffix always means *agent*; the base name means *scale*. Anything manual is free in every plan; what is charged for is automation.
- **Roles:** admin (Aura staff), owner (the client), tenant.
- **Built and working:** owner dashboard with indicators and filters, maintenance tickets with phone-camera photos, provider directory, itemised expenses, SAT/IRS fiscal catalogue, fiscal-year close, the export package an owner hands to their accountant, manual quotes, password recovery.
- **Built but disconnected:** AI ticket agent and Google SSO — no API key, no credentials.
- **Deliberately not built:** email intake of tickets, automatic quoting (a skeleton behind four locks that makes no outbound call), any search of angieslist.com (Phase 3, out of scope).
- **The platform never charges anything.** It records *which* plan an account has. It stores no amount, no billing cycle, no card, no CLABE, no tax ID.

## Technical direction
- **Showcase site:** a static generator in pure Python (`build.py`, stdlib only) reads `data/site.json` and `data/properties.json` and writes `dist/`. Every user-facing string exists in both languages. *(There is no Next.js here and there never was — that line in earlier versions of this file described a plan that was not the one built.)*
- **Platform:** FastAPI + SQLAlchemy 2.0 + Jinja2, server-rendered. SQLite in a single file, no Alembic: the schema is created by `create_all()` plus idempotent `_ensure_*` migrations that run at startup.
- **Two databases, never one:** `platform-mock.db` for simulation and `platform.db` for real data, chosen by `DATA_MODE`. Files uploaded and export packages are split the same way.
- **Strict CSP:** no inline JavaScript and no inline CSS anywhere in the platform's templates. A test enforces it.
- Keep dependencies minimal; everything must run on a free tier.

## Rules that are not negotiable
- **`platform/data/platform.db` holds the CEO's real owners.** Never point a test, a script or a migration at it. Take a snapshot before anything that writes. The dry run is `cd platform && python -m app.migrate --simular`.
- **A push to `main` republishes the public site.** Work on a branch; never push without explicit CEO approval.
- **Never deploy to production, purchase domains, or modify DNS** — prepare everything and give the CEO the exact steps.
- **No real tenant data, provider data or payment data until Legal signs off** (D-016). The gate is `DATA_MODE`; in `live` the app refuses to start without `LEGAL_CLEARANCE_REF`. Do not invent new legal criteria, and do not treat "Legal is being engaged" as a green light.
- **Isolation answers 404, never 403**, for anything belonging to another account: a 403 would confirm the object exists.
- **A plan limit blocks creating, never reading** — and never blocks a tenant from reporting a problem. A water leak knows nothing about subscriptions.
- **Nothing is deleted that serves as a record.** An expense is voided with a reason, a provider is archived, a document keeps its row when its bytes go.
- Fly.io is suspended and automatic backups are cancelled, both by CEO decision. Do not propose recovering them.

## Organization rules
- The CEO approves anything user-visible before it is considered done.
- Delegate work to the department subagents: `dev` builds, `infra` handles deployment/domain/config, `qa` reviews and tests. QA sign-off is required before any deploy is proposed to the CEO.
- Status reports use the template in `docs/REPORT_TEMPLATE.md`; write them to `docs/reports/<department>/` so the CEO can copy them to Google Drive.
- Decisions go in `docs/decisions/DECISION_LOG.md` with their reasoning, and open items in `docs/PENDIENTES.md`. If a decision is the CEO's, do not guess it — ask, and leave the work blocked until it is answered.

## Where things stand (2026-10-14)
- **Showcase site:** live on Cloudflare Workers. Its MVP checklist is still open on two points: Lighthouse mobile has never been measured, and the privacy and terms pages still have no text from Legal.
- **Platform:** Phase 2.1 (stages E8–E14) is **built and tested** on branch `work/feedback-usuarios`, 753 checks across 17 suites, **published nowhere**. Fly is suspended.
- **Current state and next steps:** [`docs/PENDIENTES.md`](docs/PENDIENTES.md).
