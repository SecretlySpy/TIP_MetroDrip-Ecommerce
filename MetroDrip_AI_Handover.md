# MetroDrip — AI Development Handover

**Version 1.3 — amended post-implementation to record the administrator / merchant console separation** (FR-22, NFR-9/10, D-10 to D-12).
Version 1.2 amended v1.1 to record the two-level category taxonomy (FR-21, NFR-7/8, D-07 to D-09).
Version 1.1 amended v1.0 to satisfy the IT 009 Project Checklist (customer accounts, wishlist, reviews, order history, support pages, invoices, CMS-lite).

> **Instructions to the AI developer:** This document is the approved pre-implementation plan. Build exactly what is specified. Do not add features from the Out-of-Scope list. Follow the task order strictly — no task may depend on an unbuilt component. When a detail is unspecified, choose the simplest option consistent with the Hard Invariants and flag it in a DECISIONS.md file in the repo.

> **v1.3 amendment note.** Everything marked *v1.3* documents work already built and merged, not new scope. §4 gains `Customer.role`, §5 gains FR-22, §6 gains NFR-9/10, §8 lists the console modules, §9 extends Epic F with F-5 to F-8, and §11 records D-10 to D-12. Rationale lives in `DECISIONS.md` (ADR-F-001, ADR-F-002, ADR-C-004); module-level detail in `AI Documentation Notes.md`. **Nothing in §3 Hard Invariants or §12 Out of Scope changed.** The v1.2 note below still applies.
>
> **v1.2 amendment note.** Everything marked *v1.2* documents work already built and merged, not new scope. The plan is amended rather than rewritten so the original intent stays legible: §4 gains the `Category` entity and the hierarchy rules, §5 gains FR-21, §6 gains NFR-7/8, §8 lists the new modules, §9 extends Epic C with C-5 to C-8, and §11 records D-07 to D-09. Rationale lives in `DECISIONS.md` (ADR-C-002, ADR-C-003); module-level detail in `AI Documentation Notes.md`. **Nothing in §3 Hard Invariants or §12 Out of Scope changed.**

---

## 1. Product Summary

**MetroDrip** is a B2C e-commerce web application + inventory system for a Metro Manila–based streetwear/apparel brand.

- Responsive **web only** (mobile-first). No native apps in v1.
- **Guest checkout supported**, plus optional customer accounts (registration/login, profile, saved addresses, order history, wishlist).
- **Single warehouse** inventory, tracked per variant (Size × Color × Fit = one SKU).
- Payments via **PayMongo** (cards, GCash, Maya). Shipping via **J&T Express**.
- Solo developer, bootstrap budget (infra ≤ ~$25/month), flexible quality-first timeline.
- Fully custom build — the brand owns the platform end-to-end.

## 2. Tech Stack (Locked)

| Layer | Choice |
|---|---|
| Language/Framework | **Python / Django** |
| Database | **MySQL 8, InnoDB engine only, `utf8mb4` charset** |
| ORM | Django ORM (`select_for_update` + `transaction.atomic` for stock ops) |
| Frontend | Django Templates + **HTMX + Alpine.js** (server-rendered, no SPA) |
| Background jobs | APScheduler in-process for v1 (reservation expiry, low-stock scan); Celery+Redis later if needed |
| Media | Object storage + CDN for product images (never app-server disk) |
| Testing | pytest; lint with ruff; CI on every push |

## 3. Hard Invariants (Non-Negotiable)

1. **No overselling, ever.** `available = qty_on_hand − qty_reserved`. All stock mutations inside `transaction.atomic()` with `select_for_update()`. Concurrency test (N parallel buyers, limited stock → exactly stock-count successes) is a release gate.
2. **Money is integer centavos.** No floats anywhere. `INT` columns; format at display time only.
3. **Webhooks are payment truth.** Orders flip `Pending → Paid` ONLY via signature-verified PayMongo webhook. Client redirects are never trusted. Webhook handlers are idempotent (safe on replay).
4. **Append-only stock audit.** Every stock change writes a `StockMovement` row (delta, reason: sale/restock/adjustment/return, ref order).
5. **Order state machine enforced in code.** `Pending → Paid → Packed → Shipped → Delivered`, plus `Cancelled`/`Refunded`. Illegal transitions must raise.
6. **MySQL: InnoDB + utf8mb4 from the first migration.** Never MyISAM, never legacy utf8.
7. Card data never touches the server — PayMongo hosted checkout/elements only.

## 4. Data Model

```
Category 1──* Category (parent → children, max depth 2)
Category 1──* Product 1──* ProductVariant 1──1 StockRecord 1──* StockMovement
                 │                │
                 │                └──* OrderItem *──1 Order 1──1 Payment
                 │                                     ├──1 Shipment
                 │                                     └──1 Customer (nullable = guest)
Customer 1──* WishlistItem *──1 Product
Customer 1──* Review *──1 Product   (verified purchase only)
```

| Entity | Key fields |
|---|---|
| Category | id, name (unique per parent, **not** globally), slug (globally unique), parent_id (nullable self-FK, PROTECT) — **amended v1.2** |
| Product | id, name, slug, description, category_id, base_price (int centavos), images (json), is_active, is_mock (**amended v1.2**) |
| ProductVariant | id, product_id, sku (unique), size (enum), color, fit (enum: slim/regular/oversized), price_override (nullable int) |
| StockRecord | variant_id (unique), qty_on_hand, qty_reserved, low_stock_threshold |
| StockMovement | id, variant_id, delta, reason (enum), ref_order_id (nullable), created_at — append-only |
| Order | id, order_no (format `MD-YYYY-NNNNN`), status (enum), subtotal, shipping_fee, total (all int centavos), shipping_address (json), created_at |
| OrderItem | order_id, variant_id, qty, unit_price_snapshot |
| Payment | order_id, provider_ref, method (card/gcash/maya), status, amount, paid_at |
| Shipment | order_id, courier, waybill_no, tracking_url, status, booked_at |
| Customer | id, email, name, phone, addresses (json), password_hash (nullable — null = guest record), is_staff, role (customer/merchant/administrator, indexed) — **amended v1.3** |
| WishlistItem | customer_id, product_id, created_at (unique together) |
| Review | id, customer_id, product_id, order_id (proof of purchase), rating (1–5), body, status (pending/approved/rejected), created_at |

**Category hierarchy (amended v1.2 — see ADR-C-002).** Categories are two levels deep: main categories (`parent = NULL`) each with `Men` and `Women` children. A product still belongs to exactly one category, which may be a main category or a child.

- Child slugs are parent-prefixed (`hoodies-men`) because `name` is deliberately not globally unique — `Men` must exist under every parent. `slug` is the only stable identifier.
- Depth (max 2) and self-parenting are enforced in `Category.clean()`, **not** by the database: depth needs a join, and MySQL rejects a CHECK constraint referencing an AUTO_INCREMENT column (error 3818). Sibling-name uniqueness is split the same way — a `UniqueConstraint(parent, name)` covers children, but MySQL treats each NULL `parent_id` as distinct, so duplicate *root* names are caught only in `clean()`.
- `Product.is_mock` flags rows generated by `seed_mock_catalog`. It is bookkeeping only — `is_active` remains the sole storefront visibility boundary.

**Console roles (amended v1.3 — see ADR-F-001).** `Customer` is still the single `AUTH_USER_MODEL`; back-office staff are not a separate table. `role` selects which console an account may enter and `is_staff` is the gate that makes it effective — **both** are required, so clearing `is_staff` revokes access without discarding which console the account belonged to. A superuser is admitted to both consoles regardless of role.

- The role vocabulary lives in `apps/accounts/roles.py`, deliberately free of model imports: `config/consoles.py` needs it while the admin app is still starting, and importing `apps.accounts.models` there raises `AppRegistryNotReady`.
- Migration `accounts.0002_customer_role` promotes every pre-existing `is_staff` account to `administrator` — that is the console `/admin/` became, so nobody who could sign in before is locked out. Merchants are created deliberately afterwards, never inferred.
- `Customer.clean()` rejects a console role paired with `is_staff = False`, the same validation-only pattern `Category.clean()` uses. The runtime boundary is `ConsoleSite.has_permission`, checked on every console request.


## 5. Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | Catalog with 3-axis variants (Size × Color × Fit); each variant = unique SKU with own stock |
| FR-2 | Storefront: browse, filter (size/color/fit/category/price), sort (price, name, newest, popularity), search, product detail with variant picker |
| FR-3 | Cart (client-side localStorage) + guest checkout |
| FR-4 | PayMongo payments: cards, GCash, Maya; order confirmed only on webhook |
| FR-5 | Stock reservation at checkout start (15-min hold), decrement on payment, auto-release on expiry |
| FR-6 | Order lifecycle state machine (see Invariant 5) |
| FR-7 | J&T integration: book shipment, store waybill, surface tracking to shopper. **Fallback: manual waybill entry field in admin** so launch never blocks on courier API access |
| FR-8 | Admin dashboard: CRUD products/variants (variant-matrix generator), stock adjustments with reason log, order management |
| FR-9 | Low-stock alerts per SKU (dashboard flag + email) |
| FR-10 | CSV exports: sales (Excel-generic, non-VAT: date, order_no, SKU, qty, unit_price, shipping, fees, net) + inventory snapshot |
| FR-11 | Transactional email: order confirmation, shipping notification |
| FR-12 | **SMS alerts via Semaphore API** at `Paid`, `Shipped`, `Out for Delivery` transitions |
| FR-13 | **Checkout address autocomplete via Google Places**; shipping zone (NCR/Luzon/VisMin) auto-derived from geocoded address — with manual zone dropdown fallback if API unavailable |
| FR-14 | Customer accounts (optional — guest checkout remains): registration/login (Django auth), email verification, profile with personal info + saved shipping addresses, password reset |
| FR-15 | Order history: logged-in customers see a list of their past orders with items, totals, status, and tracking; guest orders remain accessible via tokenized link and are claimable by matching email on registration |
| FR-16 | Wishlist: logged-in customers can save/remove products and view their wishlist |
| FR-17 | Reviews & ratings: verified-purchase customers can rate (1–5) and review products; admin moderation queue (approve/reject); approved reviews + average rating shown on product detail |
| FR-18 | Customer support: contact form (stored + emailed to admin) and FAQ page |
| FR-19 | Printable invoice and packing slip: print-formatted HTML views generated from order detail (admin) and invoice from customer order history |
| FR-20 | CMS-lite: admin-editable static pages (About, FAQ, Privacy, Contact info) via Django flatpages, plus homepage banner/promo content manager (title, image, link, active flag) |
| FR-21 | **Added v1.2.** Global category navigation: a "Browse Categories" disclosure in the site header listing every main category, an "All \<Category\>" link, and its Men/Women children with live active-product counts. The same two levels replace the flat category chips in the shop filter panel. Selecting a main category returns its directly-assigned products **plus** every child's; selecting a child returns only its own. Category, size, colour, fit, price, search, and sort all survive filtering and pagination |
| FR-22 | **Added v1.3.** The back office is two separate consoles. `/merchant/` holds catalog, variants, stock and the movement ledger, orders, payments, shipments, banners, flat pages, contact messages, and review moderation. `/admin/` holds customer accounts, roles and groups, shipping fees, and the audit trail. Every model belongs to exactly one console. Each console has its own login page and rejects the other console's credentials with an explanatory message rather than a redirect loop. A signed-in user who reaches the wrong console gets a 403 page naming the console they own; guessing the other console's model URL returns 404. Only superusers may change roles, staff/superuser status, groups, or permissions, and nobody may change their own |

## 6. Non-Functional Requirements

- NFR-1 Performance: LCP < 2.5s on 4G mobile; cache catalog pages (`cache_page`)
- NFR-2 Security: admin session auth + TOTP 2FA, rate-limited login, HTTPS, webhook signature verification, idempotency keys on payment/shipment calls
- NFR-3 Consistency: zero-oversell invariant (see §3)
- NFR-4 Privacy: PH Data Privacy Act (RA 10173) — minimal PII, privacy policy page, stated retention
- NFR-5 Cost: infra ≤ ~$25/month at launch scale
- NFR-6 Mobile-first responsive, WCAG AA contrast
- NFR-7 **Added v1.2.** Global navigation costs at most two catalog queries per request and never N+1: one query for main categories, one for prefetched children, both carrying counts. The context processor is lazy, so pages that do not render the menu issue neither
- NFR-8 **Added v1.2.** The category disclosure meets WCAG 2.2 AA interaction expectations — semantic `<details>`/`<summary>` (so it works with JavaScript disabled), visible focus, Escape and outside-click closing, no hover-only behaviour, usable at 320 CSS px with ~44 px touch targets
- NFR-9 **Added v1.3.** Console authorization is deny-by-default and verified server-side on every request, never by hiding interface controls. The role check runs in `AdminSite.has_permission` before any view body; revoking `is_active`, `is_staff`, or the role takes effect on the **next request**, not at the next login. Model ownership is enforced by disjoint registries, so the other console's URLs are not merely forbidden — they are unrouted
- NFR-10 **Added v1.3.** Any page that renders per-user chrome and is also page-cached must vary on cookie. `cache_page` stores a response *before* `SessionMiddleware` adds `Vary: Cookie`, so the header alone is not sufficient and asserting its presence is not a valid regression test (ADR-C-004)

## 7. External APIs (5) + Inbound Webhooks (2)

| API | Purpose | Notes |
|---|---|---|
| PayMongo | Cards, GCash, Maya | Hosted checkout; webhook = truth |
| J&T Express | Shipment booking + tracking | Adapter behind shared `ShippingProvider` interface; manual-waybill fallback |
| Transactional email | Order/shipping emails | Free-tier provider |
| Semaphore SMS | Order/delivery SMS (PH) | Enhancement-tier: failure must not block checkout |
| Google Maps Platform (Places + Geocoding) | Address autocomplete + zone detection | Enhancement-tier: manual zone dropdown fallback |
| Inbound: `/api/webhooks/paymongo/` | Payment confirmation | Signature-verified, idempotent |
| Inbound: `/api/webhooks/courier/` | Delivery status updates | — |

**Rule:** enhancement-tier APIs (SMS, Maps) must never sit on the critical checkout path — degrade gracefully.

## 8. Project Structure

```
metrodrip/
├── manage.py
├── config/settings/{base,dev,prod}.py
├── config/admin.py     # AdminConfig -> AdministratorSite (v1.3)
├── config/consoles.py  # AdministratorSite + MerchantSite, role gates (v1.3)
├── apps/
│   ├── catalog/        # Product, ProductVariant, Category (two-level)
│   │   ├── context_processors.py            # global category tree (v1.2)
│   │   ├── seed_catalog.py                  # deterministic seed vocabulary (v1.2)
│   │   └── management/commands/seed_mock_catalog.py   # placeholder catalog (v1.2)
│   ├── inventory/      # StockRecord, StockMovement, reservations (services.py = all stock math)
│   ├── orders/         # Order, OrderItem, state machine
│   ├── payments/       # PayMongo adapter + webhook view
│   ├── shipping/       # ShippingProvider interface, jnt.py adapter, zone mapper
│   ├── notifications/  # email + SMS (Semaphore) adapters, templates
│   ├── accounts/       # registration/login, profile, saved addresses, wishlist, order history
│   │   ├── roles.py                            # StaffRole, model-free (v1.3)
│   │   ├── admin.py                            # accounts, roles, audit trail (v1.3)
│   │   └── management/commands/
│   │       ├── sync_console_roles.py           # registry-derived grants (v1.3)
│   │       └── create_console_account.py       # scoped staff accounts (v1.3)
│   ├── reviews/        # Review model, submission rules (verified purchase), moderation
│   ├── cms/            # flatpages config, homepage banners, contact form, FAQ
│   └── storefront/     # public views, cart, checkout
├── templates/admin/console_denied.html         # wrong-console 403 page (v1.3)
├── templates/  static/  jobs/  tests/
├── index.html  .nojekyll  docs/images/   # GitHub Pages setup guide (v1.2)
└── requirements.txt
```

Business logic lives in each app's `services.py`; views stay thin. One courier/provider = one adapter file behind a shared interface.

## 9. Build Order (Strict Dependency Sequence)

**Epic A — Foundation:** A-1 scaffold+CI → A-2 schema/migrations/seed → A-3 money utils/config → A-4 staging deploy.

**Epic B — Inventory Core (build BEFORE storefront):** B-1 atomic stock ops → B-2 reservations w/ 15-min TTL + release job → B-3 movement audit log → B-4 low-stock scan.
*Write the failing concurrency tests in `tests/test_inventory.py` FIRST.*

**Epic C — Catalog & Storefront:** C-1 admin CRUD + variant-matrix generator (leverage Django Admin) → C-2 listing/filters/search → C-3 product detail + variant picker (out-of-stock variants disabled) → C-4 cart.

**Epic C (extended v1.2) — Category Navigation (FR-21):** C-5 `Category.parent` + depth/sibling validation + `Product.is_mock` + migration back-filling Men/Women children → C-6 hierarchy-aware catalog services (prefetched tree with counts; branch-spanning filter) → C-7 `seed_mock_catalog` for deterministic placeholder data at browsable scale → C-8 global context processor + header disclosure + shop filter tree + query-preserving pagination.
*C-5 depends on C-1; C-6/C-7 on C-5; C-8 on C-6. C-7 must not alter the ADR-A-012 seed contract.*

**Epic D — Checkout & Payments:** D-1 checkout flow + zone shipping fee + reservation → D-2 PayMongo (all 3 methods, sandbox) → D-3 webhook handler (verify → confirm → decrement, idempotent) → D-4 confirmation email + tokenized order-status page → D-5 Semaphore SMS adapter → D-6 Places autocomplete + geocode→zone mapper.

**Epic E — Fulfillment:** E-1 order management dashboard w/ state machine → E-2 J&T adapter (book + waybill) → E-3 tracking surface + shipping email/SMS → E-4 cancel/refund flow (stock restored with `return` movement).

**Epic G — Accounts & Community (checklist-required):** G-1 registration/login/password reset (Django auth) + profile & saved addresses → G-2 order history list + guest-order claiming by email → G-3 wishlist → G-4 reviews & ratings w/ verified-purchase rule + admin moderation queue → G-5 contact form + FAQ → G-6 CMS-lite (flatpages + homepage banner manager) → G-7 printable invoice/packing slip views.
*G-1 depends on D-4; G-2 on G-1+E-1; G-4 on G-1+E-1; G-5/G-6 depend only on A-4; G-7 on E-1. Saved addresses pre-fill checkout (integrates with D-1/FR-13).*

**Epic F — Reporting & Hardening:** F-1 CSV exports → F-2 admin 2FA + rate limits + admin audit log + customer-account admin view (view/edit/suspend) → F-3 performance pass (LCP target) → F-4 privacy pages.

**Epic F (extended v1.3) — Console Separation (FR-22):** F-5 `Customer.role` + `roles.py` + migration promoting existing staff → F-6 `AdministratorSite` / `MerchantSite` with role-gated `has_permission`, per-console login forms, and the wrong-console page → F-7 re-point every app's registrations so each model has exactly one owner, splitting shipping (zones administrator, shipments merchant) → F-8 `sync_console_roles` + `create_console_account`, the audit-trail admin, the superuser-only privilege tier, and the storefront console shortcut.

## 10. Milestones & QA Gates

| Milestone | Done when | Gate (must pass) |
|---|---|---|
| M1 Foundation | Staging live, seed browsable | Migrations reversible; money math unit tests pass |
| M2 Inventory+Catalog | Full catalog managed + browsable | **20 parallel buys of 10 units → exactly 10 orders, 0 oversells** |
| M3 Commerce | End-to-end sandbox purchase, all 3 payment methods | Webhook replay idempotent; abandoned checkout restores stock ≤16 min |
| M4 Fulfillment | Pack→book→track works incl. cancel/refund | State machine rejects illegal transitions; CSV validated |
| M4.5 Accounts & Community (Epic G) | Register→login→order history→review→wishlist all work; CMS pages editable; invoice prints | Guest checkout still works untouched; only verified purchasers can review; unapproved reviews never render publicly |
| M5 Beta | 10–20 real orders (mix of guest + account) | Zero discrepancies vs PayMongo dashboard; CSV reconciles to the centavo |
| M6 Release | Public launch | 5× load test; backup/restore drill |

## 11. Locked Decisions

| ID | Decision |
|---|---|
| D-01 | Courier = J&T only in v1 |
| D-02 | Shipping = zone-based flat rates (NCR / Luzon / VisMin), stored in config table; zone auto-detected via FR-13 with manual fallback |
| D-03 | Non-VAT registered (CSV format excludes VAT columns) — confirm before F-1 |
| D-04 | No promo codes in v1 |
| D-05 | **REVISED v1.1:** Guest checkout remains the default flow; optional customer accounts added per project checklist (registration, profile, order history, wishlist). Guest order status still via tokenized emailed link |
| D-06 | CSV = Excel-generic format |
| D-07 | **Added v1.2 (ADR-C-002):** Category taxonomy is a self-referencing `parent` capped at two levels, not separate main/sub tables. Main-category slugs are preserved; children are `Men`/`Women` with parent-prefixed slugs. Deeper nesting and dedicated `/category/<a>/<b>/` routes are out of scope — browsing stays on `/shop/?category=<slug>` |
| D-08 | **Added v1.2 (ADR-C-003):** Bulk placeholder data lives in `seed_mock_catalog`, never in `seed_demo`. `--count` is the number of *placeholders* to maintain (default 100), independent of the hand-authored catalog. Idempotency comes from natural keys, so reruns write nothing and never reset existing stock |
| D-09 | **Added v1.2, extended v1.3:** Django Admin is branded via a custom `AdminSite`, installed by replacing `django.contrib.admin` with `config.admin.MetroDripAdminConfig` in `INSTALLED_APPS`, so existing `admin.site.register(...)` calls are untouched. As of v1.3 that site is `AdministratorSite`; its login page reads "Administrator Login" and the merchant console's reads "Merchant Login" |
| D-10 | **Added v1.3 (ADR-F-001):** Two `AdminSite` instances, not one site with per-model permissions. Django builds the admin index from the *registry*, not from permissions, so a single site would still show a merchant empty "Accounts" and "Audit Trail" headings — the separation would be presentational. `admin.site` stays the administrator console so the `admin:` URL namespace is preserved; `/merchant/` gets the new `merchant:` namespace |
| D-11 | **Added v1.3 (ADR-F-002):** Group permissions are derived from the console registries by probing each `ModelAdmin`, never from a hand-written list, so moving a model between consoles is picked up automatically and read-only admins (`StockMovement`, `Reservation`, `Payment`, `LogEntry`) resolve to view-only without being named. `create_console_account` exists because `createsuperuser` produces an account that reaches both consoles and so proves nothing about the separation |
| D-12 | **Added v1.3:** The audit trail is Django's `LogEntry`, surfaced read-only on the administrator console and nowhere else. No add, change, or delete for anyone including superusers — the same append-only guarantee `StockMovement` gives the stock ledger. Both consoles write to it |

## 12. Out of Scope for v1 (Do NOT Build)

Native/PWA apps · multi-warehouse · wholesale/B2B pricing · promo-code/discount engine (homepage promo *banners* are in via FR-20; discount *codes* are not) · direct accounting API sync · loyalty points · live chat (contact form + FAQ only) · returns portal (manual via order status + refund action) · public REST API (future mobile-app requirement).

## 13. Top Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Overselling race condition | Reservations + `select_for_update`; M2 concurrency gate |
| Payment/order mismatch | Webhook-as-truth, idempotency, daily reconcile vs PayMongo |
| Courier API access delays | Apply at M1; manual-waybill fallback keeps launch unblocked |
| Scope creep (solo dev) | §12 is contractual; flexible timeline absorbs delay, never new features |
| Enhancement API outage (SMS/Maps) | Graceful degradation: email-only alerts, manual zone dropdown |
| Review spam/abuse | Verified-purchase-only rule + admin moderation queue (FR-17); nothing renders publicly until approved |

## 14. UI Reference

A 6-screen UI kit exists (Home, Shop/Listing, Product Detail, Cart, Checkout, Admin Dashboard). Design language: paper white base, ink `#141414`, volt accent `#C8F031`, surface `#F4F4F2`, muted `#75756E`, border `#E4E4DF`, danger `#E5484D`. Type: Anton (display), Inter (body), IBM Plex Mono (SKUs/prices/waybill data). Signature motifs: dashed waybill-style summary cards, mono SKU tags, barcode strip. Implement templates to match these screens.

**Amended v1.2 — category menu.** The kit predates FR-21, so the header disclosure has no reference screen. It is built from the existing tokens: a mega-dropdown on desktop anchored to the toggle's right edge, and the same markup rendered inline inside the mobile drawer. One template partial serves both breakpoints — the presentations differ only in CSS, so they cannot drift apart.

## 15. First Three Tasks (Start Here)

1. Task A-1: repo + Django scaffold with the 7 apps + CI (pytest, ruff); first migration sets InnoDB + utf8mb4.
2. Commit failing concurrency tests in `tests/test_inventory.py` (2 buyers / 1 unit → exactly 1 success).
3. Task A-2: full Prisma-equivalent Django models per §4 + seed script (5 products × Size×Color×Fit matrix).
