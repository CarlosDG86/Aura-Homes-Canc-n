# Aura Homes Cancún — Showcase site (MVP build)

Built by Design (acting as Dev at CEO request) from the approved design system and handoff spec.
This is a **real, deployable static site** for the first property (AUR-001), scoped to the approved MVP: **showcase only — no accounts, no payments, no booking calendar.**

## What's here
```
data/
  site.json          → brand config + all UI strings (ES/EN) — the i18n string table
  properties.json    → property content (AUR-001 real; 2 demo entries flagged placeholder)
build.py             → static site generator (Python, no deps beyond stdlib + Pillow for image prep)
dist/                → the generated site (this is what you deploy)
  index.html         → root, redirects to /es/ (Spanish default) + hreflang
  es/ en/            → one folder per language (single language per URL — SEO-friendly)
  assets/css|js|img
```

## Run
```
python3 build.py          # regenerates dist/ from data/
```
No framework required. It's plain static HTML/CSS/JS — deploy `dist/` to any static host (Netlify, Vercel, Cloudflare Pages — all free tier).

> Note on stack: the handoff spec named Next.js; I built framework-free static HTML for speed and zero cost. It migrates cleanly to Next.js later if Dev prefers. This is a Dev/Infra call to ratify — the content model (JSON) and markup port directly.

## Key decisions already implemented
- **Bilingual = single language per URL** (`/es`, `/en`) with an ES|EN toggle in the top bar. **No dual-language inline text** (fixes the regression in the Claude Design export).
- **Price by language:** ES shows MXN; EN shows USD with `≈` (approximate). FX rate lives in `data/site.json → brand.fxRate` (**placeholder 18.15 — Finance/Marketing must set the real value**).
- **Contact = 3 channels:** web form (composes an email via `mailto` for now; set `data-endpoint` on the form to a free form service like Formspree to send without opening a mail client), direct email, and WhatsApp.
- **CTA buttons** use `#C0492B` (AA contrast). Full palette + type per the approved system.
- **Rented state, map at neighborhood level, rental requirements, sticky mobile bar, floating WhatsApp** — all built.

## Content editing (the "admin module")
Structure is **Decap-CMS ready**: content is data (`data/*.json`), not hardcoded. To wire Decap:
1. Put this repo on GitHub (Infra).
2. Add `admin/config.yml` mapping collections to `data/properties.json` fields.
3. Decap gives a hosted admin UI (no login system to build, no database) that commits to git and triggers a rebuild.
This satisfies "editar datos a futuro" **without** a custom login/portal.

## ⚠️ Before going live
- **Privacy photo review (blocking):** `vistaFrente`, `Entrada`, `Entrada2` may show house number / plates. Confirm before publishing — the CMS can't un-publish what's already public.
- **Legal:** `Aviso de Privacidad` and `Términos` footer links are placeholders. Legal drafts + **Mexican attorney review required before launch** (LFPDPPP).
- **Photos:** AUR-001 images are the 840px WhatsApp interim set (approved exception). Desktop hero uses the split layout so low-res width is not exposed. Replace via CMS post-launch.
- **FX rate:** set the real value.
- **WhatsApp number / email:** `data/site.json` currently has placeholders — set real ones (number is intentionally temporary per CEO).
- **Specs confirmation:** AUR-001 set to 3 rec / 2.5 baños / 192 m² / $24,500 MXN — CEO to confirm the real price and bath count.

## OUT OF SCOPE (do NOT build for launch)
The Claude Design export also contained a **3-role management platform** (login, admin/owner/tenant dashboards, rent payments, maintenance tickets). This is **not** the approved MVP and is **not** included in this build. It requires a separate CEO decision (and Legal review for tenant PII + payments) as a possible Phase 2.
