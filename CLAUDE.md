# Aura Enterprise Solutions — aura-web

This repository is the rentals website of Aura Enterprise Solutions. The person you work with is the CEO and sole decision-maker.

## Product (CEO-approved, do not change without CEO approval)
- Showcase website for the CEO's OWN long-term rental properties. No marketplace, no user accounts, no payments.
- Pilot scope: Mexico City (CDMX) properties only.
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
2. All CDMX properties rendered from content files with complete photos.
3. Inquiry form working; WhatsApp deep link working.
4. Lighthouse mobile scores 90+ across the board.
5. QA checklist passed; privacy notice and terms pages present (text supplied by Legal via the CEO).
