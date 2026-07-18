# MetroDrip — AI Development Handover

**Version 1.1 — amended to fully satisfy the IT 009 Project Checklist** (adds customer accounts, wishlist, reviews, order history, support pages, invoices, CMS-lite).

> **Instructions to the AI developer:** This document is the approved pre-implementation plan. Build exactly what is specified. Do not add features from the Out-of-Scope list. Follow the task order strictly — no task may depend on an unbuilt component. When a detail is unspecified, choose the simplest option consistent with the Hard Invariants and flag it in a DECISIONS.md file in the repo.

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
Product 1──* ProductVariant 1──1 StockRecord 1──* StockMovement
   │                │
Category *──* Product└──* OrderItem *──1 Order 1──1 Payment
                                          ├──1 Shipment
                                          └──1 Customer (nullable = guest)
Customer 1──* WishlistItem *──1 Product
Customer 1──* Review *──1 Product   (verified purchase only)
```

| Entity | Key fields |
|---|---|
| Product | id, name, slug, description, category_id, base_price (int centavos), images (json), is_active |
| ProductVariant | id, product_id, sku (unique), size (enum), color, fit (enum: slim/regular/oversized), price_override (nullable int) |
| StockRecord | variant_id (unique), qty_on_hand, qty_reserved, low_stock_threshold |
| StockMovement | id, variant_id, delta, reason (enum), ref_order_id (nullable), created_at — append-only |
| Order | id, order_no (format `MD-YYYY-NNNNN`), status (enum), subtotal, shipping_fee, total (all int centavos), shipping_address (json), created_at |
| OrderItem | order_id, variant_id, qty, unit_price_snapshot |
| Payment | order_id, provider_ref, method (card/gcash/maya), status, amount, paid_at |
| Shipment | order_id, courier, waybill_no, tracking_url, status, booked_at |
| Customer | id, email, name, phone, addresses (json), password_hash (nullable — null = guest record) |
| WishlistItem | customer_id, product_id, created_at (unique together) |
| Review | id, customer_id, product_id, order_id (proof of purchase), rating (1–5), body, status (pending/approved/rejected), created_at |

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

## 6. Non-Functional Requirements

- NFR-1 Performance: LCP < 2.5s on 4G mobile; cache catalog pages (`cache_page`)
- NFR-2 Security: admin session auth + TOTP 2FA, rate-limited login, HTTPS, webhook signature verification, idempotency keys on payment/shipment calls
- NFR-3 Consistency: zero-oversell invariant (see §3)
- NFR-4 Privacy: PH Data Privacy Act (RA 10173) — minimal PII, privacy policy page, stated retention
- NFR-5 Cost: infra ≤ ~$25/month at launch scale
- NFR-6 Mobile-first responsive, WCAG AA contrast

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
├── apps/
│   ├── catalog/        # Product, ProductVariant, Category
│   ├── inventory/      # StockRecord, StockMovement, reservations (services.py = all stock math)
│   ├── orders/         # Order, OrderItem, state machine
│   ├── payments/       # PayMongo adapter + webhook view
│   ├── shipping/       # ShippingProvider interface, jnt.py adapter, zone mapper
│   ├── notifications/  # email + SMS (Semaphore) adapters, templates
│   ├── accounts/       # registration/login, profile, saved addresses, wishlist, order history
│   ├── reviews/        # Review model, submission rules (verified purchase), moderation
│   ├── cms/            # flatpages config, homepage banners, contact form, FAQ
│   └── storefront/     # public views, cart, checkout
├── templates/  static/  jobs/  tests/
└── requirements.txt
```

Business logic lives in each app's `services.py`; views stay thin. One courier/provider = one adapter file behind a shared interface.

## 9. Build Order (Strict Dependency Sequence)

**Epic A — Foundation:** A-1 scaffold+CI → A-2 schema/migrations/seed → A-3 money utils/config → A-4 staging deploy.

**Epic B — Inventory Core (build BEFORE storefront):** B-1 atomic stock ops → B-2 reservations w/ 15-min TTL + release job → B-3 movement audit log → B-4 low-stock scan.
*Write the failing concurrency tests in `tests/test_inventory.py` FIRST.*

**Epic C — Catalog & Storefront:** C-1 admin CRUD + variant-matrix generator (leverage Django Admin) → C-2 listing/filters/search → C-3 product detail + variant picker (out-of-stock variants disabled) → C-4 cart.

**Epic D — Checkout & Payments:** D-1 checkout flow + zone shipping fee + reservation → D-2 PayMongo (all 3 methods, sandbox) → D-3 webhook handler (verify → confirm → decrement, idempotent) → D-4 confirmation email + tokenized order-status page → D-5 Semaphore SMS adapter → D-6 Places autocomplete + geocode→zone mapper.

**Epic E — Fulfillment:** E-1 order management dashboard w/ state machine → E-2 J&T adapter (book + waybill) → E-3 tracking surface + shipping email/SMS → E-4 cancel/refund flow (stock restored with `return` movement).

**Epic G — Accounts & Community (checklist-required):** G-1 registration/login/password reset (Django auth) + profile & saved addresses → G-2 order history list + guest-order claiming by email → G-3 wishlist → G-4 reviews & ratings w/ verified-purchase rule + admin moderation queue → G-5 contact form + FAQ → G-6 CMS-lite (flatpages + homepage banner manager) → G-7 printable invoice/packing slip views.
*G-1 depends on D-4; G-2 on G-1+E-1; G-4 on G-1+E-1; G-5/G-6 depend only on A-4; G-7 on E-1. Saved addresses pre-fill checkout (integrates with D-1/FR-13).*

**Epic F — Reporting & Hardening:** F-1 CSV exports → F-2 admin 2FA + rate limits + admin audit log + customer-account admin view (view/edit/suspend) → F-3 performance pass (LCP target) → F-4 privacy pages.

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

## 15. First Three Tasks (Start Here)

1. Task A-1: repo + Django scaffold with the 7 apps + CI (pytest, ruff); first migration sets InnoDB + utf8mb4.
2. Commit failing concurrency tests in `tests/test_inventory.py` (2 buyers / 1 unit → exactly 1 success).
3. Task A-2: full Prisma-equivalent Django models per §4 + seed script (5 products × Size×Color×Fit matrix).
