# Aura Enterprise Solutions — aura-web

This repository is the rentals website of Aura Enterprise Solutions. The person you work with is the CEO and sole decision-maker.

## Product (CEO-approved, do not change without CEO approval)
- Showcase website for the CEO's OWN long-term rental properties. No marketplace, no user accounts, no payments.
- Pilot scope: Cancún (Quintana Roo) properties only.
- Bilingual: Spanish (primary, default) and English, with routes `/es` and `/en`.
- Contact: inquiry form (sends to CEO email) + prominent WhatsApp button (dominant rental contact channel in Mexico).
- Mobile-first: most renters browse on phones.

## Technical direction
- Next.js with static generation. Listings live as structured data files (JSON or MDX) in `content/properties/` — one file per property, with `es` and `en` fields. No database in the MVP.
- i18n via Next.js routing; every user-facing string must exist in both languages. Missing translations are build errors, not silent fallbacks.
- Images: optimized, lazy-loaded, consistent aspect ratio per the Design handoff spec in the repo (`docs/design-spec.md` when delivered).
- Keep dependencies minimal; free-tier deployable.

## Organization rules
- The CEO approves anything user-visible before it is considered done.
- Delegate work to the department subagents: `dev` builds, `infra` handles deployment/domain/config, `qa` reviews and tests. QA sign-off is required before any deploy is proposed to the CEO.
- Never deploy to production, purchase domains, or modify DNS — prepare everything and give the CEO the exact steps or ask for explicit approval.
- Status reports use the template in `docs/REPORT_TEMPLATE.md`; write reports to `docs/reports/<department>/` so the CEO can copy them to Google Drive.

## Definition of done (MVP)
1. Homepage, listings index, property detail pages, contact page — all in ES and EN.
2. All Cancún properties rendered from content files with complete photos.
3. Inquiry form working; WhatsApp deep link working.
4. Lighthouse mobile scores 90+ across the board.
5. QA checklist passed; privacy notice and terms pages present (text supplied by Legal via the CEO).

## Phase 2 (CEO-approved 2026-07-22 — see `docs/phase2/PLAN.md` and `docs/phase2/DB_SCHEMA.md`)
- Approved: build a login-gated owner/tenant management platform layered on top of the public showcase site (the showcase site's MVP scope above is unchanged — it stays a static, no-login, no-database public site).
- Approved sequencing: **2a → 2b → 2c**, in that order.
  - **2a (build now):** Admin + Owner login; property management; owners directory. No tenant accounts, no payments, no tenant PII.
  - **2b (build now, gated):** tenant portal + maintenance tickets. Scaffold the module and schema now, in parallel with Legal review, but **do not store real tenant PII or go live with real tenant accounts until Legal clears it.**
  - **2c (build now, gated):** rent payments + payment documents. Scaffold the module and schema now, in parallel with Legal review, but **do not process or store real payment data until Legal clears it.** Highest-risk phase — no real money/PII flows through 2b/2c until Legal signs off.
- Hosting/DB: stay on free-tier hosting; database is **locally-hosted/embedded (e.g. SQLite)** alongside the app rather than a paid managed database service.
- Legal is being engaged in parallel with this build per the CEO — do not treat that as a green light to launch 2b/2c with real data; that requires a separate explicit CEO confirmation once Legal signs off.
