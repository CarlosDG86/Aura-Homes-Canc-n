# Phase 2 — Owner/Tenant Management Platform: Plan (for CEO review)

**Status:** Planning only. No application code has been written. This is Dev's
recommendation for scoping a platform that already exists as a visual mockup
but was never approved or specced.

**Source:** `Design/aura-homes-canc-n-homepage/project/Aura Homes Cancún.dc.html`
(the "2a–2d" screens: login + 3 role dashboards, plus their mock data arrays).

---

## 1. What the mockup contains

The mockup adds a **login-gated management platform** on top of the public
showcase site, with three roles:

- **Administrador (Admin):** sees everything. Dashboard KPIs (total
  properties, owners, users, occupancy %); a full property list with owner
  and status; an owners directory; a users/roles list (Admin / Propietario /
  Inquilino badges) with invite capability.
- **Propietario (Owner):** sees only their own properties. Dashboard KPIs
  scoped to them; editable property cards (price, description, photos,
  status); maintenance tickets raised by their tenants; a tenants list with
  a messaging/WhatsApp shortcut; rent payments received (with a
  received/pending-review status); a documents shelf (leases, ID, legal
  policy); a scheduled-visits list (prospective tenant showings); and a
  small "team" list of people the owner has delegated property management
  to (e.g., an assistant who manages one specific property).
- **Inquilino (Tenant):** a mobile-first portal — notifications (payment
  reminders, maintenance visit notices, ticket updates), their own
  maintenance tickets (raise + track status), a message composer to the
  owner/admin (with a WhatsApp shortcut), and their own lease documents
  (contract, building rules, payment receipts).

In plain terms: this is a lightweight **property management system** —
owner/tenant accounts, maintenance ticketing, rent tracking, and document
storage — layered on top of the current listings showcase.

## 2. This contradicts the currently approved MVP scope

This repo's `CLAUDE.md` (CEO-approved) states the pilot is explicitly:
**"No marketplace, no user accounts, no payments... No database in the
MVP."** The mockup is a full accounts + database platform. Building any of
it means **formally revising that locked scope** — this plan does not
assume that revision has happened. It's presented here so the CEO can
decide with full visibility into what the mockup implies, not as a
green light to proceed.

## 3. Legal flag (already noted in this repo's README)

Once tenants have login accounts, rent payment records, and stored personal
documents (IDs, signed leases), this is materially different from a
showcase site: it involves **tenant PII and financial data**. The existing
README already flags that Legal (Mexican attorney, LFPDPPP compliance)
review is required before any such platform can launch — this is not
optional and should happen *before* build starts on payment/document
handling, not after.

## 4. Phased breakdown — options, not a decision

| Phase | Scope | Why it might go first / risk |
|---|---|---|
| **2a** | Admin + Owner property/owner management only (no tenant accounts, no payments). Admin and Owner can log in, manage listings, see an owners directory, edit property status. | Smallest slice that needs auth + a database, but delivers real value (owner self-service instead of asking Dev to edit JSON files). No PII/payments risk, so **no Legal blocker** — could ship soonest. |
| **2b** | Add the tenant portal + maintenance tickets (tenant accounts, notifications, ticket flow). No payments yet. | Introduces tenant PII (name, contact, lease association) — Legal review needed for account creation and data storage, though lighter than payments. |
| **2c** | Add rent payments + payment documents/receipts. | Highest risk and complexity: money changes hands or is recorded, receipts are stored, disputes can arise. Requires the most Legal and possibly financial/regulatory review (e.g., whether Aura is just recording payments made outside the platform, or actually processing them — very different liability). |

**Dev's recommendation:** sequence 2a → 2b → 2c as above, because each
phase is a strict superset of risk and complexity, and 2a alone already
solves a real pain point (the CEO/Dev currently hand-edit JSON files for
every listing change) without touching PII or payments. This is a
recommendation, not a decision — the CEO may prefer to bundle 2a+2b, skip
straight to what's most valuable, or defer all of Phase 2 indefinitely.

## 5. Technical implications (high-level only — infra owns the specifics)

- The current site is static HTML/generated pages with no server and no
  database — that's what makes it free-tier hosting and zero ongoing cost.
- Any of 2a/2b/2c requires: **user authentication** (login, password
  reset, sessions), a **real backend** (API to read/write data, enforce who
  can see what), and a **database** (the flat JSON content model won't
  support per-owner editing, tickets, or payment records safely).
- This is a genuine jump in cost and operational complexity versus the
  current $0 static site — hosting, database, auth provider, and ongoing
  maintenance all become recurring costs and recurring surface area to
  secure.
- **Not decided here:** which stack, which auth provider, which database,
  which hosting tier, and what it costs. Those are the **infra**
  department's call once (and if) the CEO approves a phase to build. This
  plan only flags that those decisions become necessary — it does not make
  them.

## 6. Decisions needed from the CEO

1. **Scope approval:** does the CEO want to revise the locked MVP scope to
   include any of Phase 2? If yes, which phase(s)?
2. **Sequencing:** does the CEO agree with 2a → 2b → 2c, or prefer a
   different order/bundling?
3. **Legal timing:** should Legal be engaged now (in parallel with 2a
   planning, since 2b/2c will need lead time), or only once a phase beyond
   2a is approved?
4. **Budget appetite:** is the CEO open in principle to moving off
   free-tier static hosting to a paid backend+database setup? (No numbers
   proposed here — that's infra's job once scope is set.)
