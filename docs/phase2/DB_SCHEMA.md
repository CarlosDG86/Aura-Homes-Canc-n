# Phase 2 — Proposed Database Schema (DRAFT / PROPOSAL)

**Status: PROPOSAL, not final.** This is derived from the Phase 2 mockup's
markup and mock data arrays only — it has not been reviewed by the CEO,
Legal, or infra. Field names are illustrative; types should be revisited
by whoever implements this against a real database engine. See
`docs/phase2/PLAN.md` for the product-level plan and open decisions.

This schema only makes sense if Phase 2 is approved (see PLAN.md §2) — the
current MVP stays file-based, no database.

---

## Key assumption to confirm with the CEO

**Owner and Tenant are modeled as roles on one `users` table**, not
separate tables (Admin/Owner/Tenant all share the same login mechanism,
name/email/phone fields, and avatar-initials pattern in the mockup — the
only difference is a `role` field and which related records they can see).

- **Why this approach:** the mockup's `adminUsers` list mixes all three
  roles in a single table with a `role` badge, and a person could
  plausibly hold more than one relationship to the platform (e.g., the
  CEO's own family member could be both an owner and, elsewhere, listed as
  a delegated team member). One table with role-based permissions is
  simpler to maintain and avoids duplicate login/contact records.
- **Alternative worth confirming:** separate `owners` and `tenants` tables
  if the CEO anticipates owners/tenants needing very different fields
  later (e.g., tenants need credit-check data, owners need bank payout
  details) — that data would then live in role-specific "profile" tables
  (`owner_profiles`, `tenant_profiles`) that extend `users`. Flagging this
  as a call worth confirming before implementation, not deciding it here.

The schema below follows the single-`users`-table approach, with a
`role_context` table to handle the "team member manages this specific
property" case (see `property_team_members` below), since that's a
many-to-many relationship the mockup implies but doesn't fully spell out.

---

## Entities

| Entity | Purpose |
|---|---|
| `users` | Every person who can log in: Admin, Owner, or Tenant, distinguished by `role`. |
| `properties` | A rental listing/unit — the core asset, owned by one `users` row (role=owner). |
| `property_images` | Photos for a property (mockup shows image slots per card). |
| `leases` | Links a tenant to a property for a period — the "who lives where, since when" relationship. |
| `maintenance_tickets` | Issues tenants report against a property; tracked to resolution. |
| `payments` | Rent payment records tied to a lease. |
| `documents` | Files (contracts, IDs, policies, receipts) attached to a property, owner, and/or tenant. |
| `visits` | Scheduled property showings for prospective tenants. |
| `property_team_members` | Junction: people an owner delegates day-to-day property management to. |
| `notifications` | System-generated alerts shown to a user (payment reminders, ticket updates, visit notices). |
| `messages` | Free-text messages between a tenant and their owner/admin. |

## Fields per entity

### `users`
| Field | Type | Notes |
|---|---|---|
| id | uuid/int, PK | |
| name | string | e.g. "María Herrera" |
| email | string, unique | login identifier |
| phone | string, nullable | mockup implies WhatsApp contact per user |
| password_hash | string | never store plaintext |
| role | enum(admin, owner, tenant) | drives dashboard + permissions |
| avatar_initials | string, derived | mockup computes this from name; can be computed at read time instead of stored |
| created_at | timestamp | |
| updated_at | timestamp | |

### `properties`
| Field | Type | Notes |
|---|---|---|
| id | uuid/int, PK | |
| owner_id | FK → users.id | mockup shows one owner per property |
| title | string | e.g. "Casa Palmaris" |
| zone | string | neighborhood, e.g. "Res. Cumbres" |
| city | string | pilot is Cancún per this repo's approved MVP (confirmed 2026-07-22) — matches the mockup's branding |
| price_amount | decimal | |
| price_currency | string | MXN per mockup |
| status | enum(available, rented) | "Disponible" / "Rentada" |
| bedrooms | int | inferred from showcase site's existing property fields, not explicit in this mockup's dashboard cards but needed for listing parity |
| bathrooms | decimal | ditto |
| area_m2 | decimal | ditto |
| description | text | owner-editable per mockup ("Descripción" chip) |
| created_at | timestamp | |
| updated_at | timestamp | |

### `property_images`
| Field | Type | Notes |
|---|---|---|
| id | uuid/int, PK | |
| property_id | FK → properties.id | |
| url | string | |
| sort_order | int | for gallery ordering |

### `leases`
| Field | Type | Notes |
|---|---|---|
| id | uuid/int, PK | |
| property_id | FK → properties.id | |
| tenant_id | FK → users.id (role=tenant) | |
| start_date | date | mockup shows "Inquilino desde ene 2026" |
| end_date | date, nullable | mockup shows "vence ene 2027" on a contract document |
| monthly_rent | decimal | may duplicate properties.price_amount at time of signing — kept separate since rent can change independent of current listing price |
| status | enum(active, ended) | |

### `maintenance_tickets`
| Field | Type | Notes |
|---|---|---|
| id | uuid/int, PK | |
| property_id | FK → properties.id | |
| reported_by_user_id | FK → users.id (role=tenant) | |
| title | string | e.g. "Fuga en la llave del baño principal" |
| description | text | |
| status | enum(open, in_progress, resolved) | "Abierto" / "En proceso" / "Resuelto" |
| created_at | timestamp | |
| updated_at | timestamp | |

### `payments`
| Field | Type | Notes |
|---|---|---|
| id | uuid/int, PK | |
| lease_id | FK → leases.id | ties payment to the property+tenant relationship |
| amount | decimal | |
| currency | string | |
| payment_date | date | |
| status | enum(received, pending_review) | "Recibido" / "Por revisar" |
| receipt_document_id | FK → documents.id, nullable | mockup shows a "Ver" action, implying an attached receipt |

### `documents`
| Field | Type | Notes |
|---|---|---|
| id | uuid/int, PK | |
| property_id | FK → properties.id, nullable | |
| owner_id | FK → users.id, nullable | |
| tenant_id | FK → users.id, nullable | at least one of property/owner/tenant should be set |
| file_name | string | |
| file_url | string | |
| doc_type | enum(contract, id_verification, policy, receipt, other) | |
| meta | string | free text mirroring mockup's subtitle, e.g. "Firmado · 12 meses", "Vigente" |
| uploaded_at | timestamp | |

### `visits`
| Field | Type | Notes |
|---|---|---|
| id | uuid/int, PK | |
| property_id | FK → properties.id | |
| prospect_name | string | mockup shows "Interesado: Fam. Gómez" — no account, just a name |
| prospect_contact | string, nullable | not shown in mockup but likely needed to actually run a showing |
| scheduled_at | timestamp | |
| status | enum(scheduled, completed, cancelled) | inferred; mockup only shows scheduled ones |

### `property_team_members` (junction)
| Field | Type | Notes |
|---|---|---|
| id | uuid/int, PK | |
| property_id | FK → properties.id | |
| user_id | FK → users.id | the delegated helper |
| role_description | string | mockup: "Administra Casa Ceiba" — free text, could later become a real permission enum |

### `notifications`
| Field | Type | Notes |
|---|---|---|
| id | uuid/int, PK | |
| user_id | FK → users.id | recipient |
| type | enum(payment, notice, ticket) | "Pago" / "Aviso" / "Ticket" tags in mockup |
| title | string | |
| body | text | |
| created_at | timestamp | |
| read_at | timestamp, nullable | |

### `messages`
| Field | Type | Notes |
|---|---|---|
| id | uuid/int, PK | |
| from_user_id | FK → users.id | tenant, typically |
| to_user_id | FK → users.id, nullable | owner or admin; mockup doesn't show a picker, implies "the owner/admin of my property" — **flag: confirm routing logic** |
| property_id | FK → properties.id, nullable | for context, since a tenant is tied to one lease/property |
| body | text | |
| created_at | timestamp | |

## Relationships (summary)

- `users` (role=owner) **1 → many** `properties`
- `properties` **1 → many** `property_images`
- `properties` **1 → many** `leases`; `users` (role=tenant) **1 → many** `leases` (a tenant could in theory have lease history across properties over time, even though mockup shows one active lease each)
- `leases` **1 → many** `payments`
- `properties` **1 → many** `maintenance_tickets`; `users` (role=tenant) **1 → many** `maintenance_tickets` (as reporter)
- `properties`, `users` (owner and/or tenant) **each optionally 1 → many** `documents`
- `properties` **1 → many** `visits`
- `properties` **many ↔ many** `users` via `property_team_members` (a helper can manage multiple properties; a property can have multiple helpers)
- `users` **1 → many** `notifications`
- `users` **1 → many** `messages` (as sender), optionally scoped by `property_id`

## Open assumptions to confirm before implementation

1. Single `users` table with `role` vs. separate owner/tenant tables (see
   top of this doc) — recommended: single table, but confirm.
2. One owner per property (mockup shows this) — if co-ownership is ever
   needed, `properties.owner_id` would need to become a junction table
   (`property_owners`). Not built now since the mockup gives no evidence
   of this need.
3. Whether `payments` records reflect money that actually moved through
   the platform (real payment processing — high Legal/PCI burden) or is
   just a manually-entered log of rent received outside the platform
   (lower burden, more like a receipt tracker). This materially changes
   both the schema (e.g., need for a payment-processor transaction ID)
   and the Legal review required — see PLAN.md §3. **Not assumed here.**
4. `messages` routing (who a tenant's message actually reaches) is
   inferred, not explicit in the mockup — needs product clarification.
