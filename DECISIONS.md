# MetroDrip Architecture Decision Register

- **Scope:** Tasks A-1 through A-4, Epic B, and the Epic C/D/G storefront-commerce layer (through the 2026-07-19 QA/hardening pass)
- **Status:** Accepted
- **Authority:** Extends the locked decisions in `AI Documentation Notes.md`.
- **Change rule:** Update this register when an implementation intentionally changes one of these contracts.

## ADR-A-001 — Domain application count

- **Status:** Accepted
- **Decision:** MetroDrip has 10 first-party Django apps: `catalog`, `inventory`, `orders`, `payments`, `shipping`, `notifications`, `accounts`, `reviews`, `cms`, and `storefront`.
- **Rationale:** The project structure and current functional requirements define 10 domain boundaries. The phrase "7 apps" in Task A-1 is a stale count from before the checklist-driven account, community, and content additions.
- **Consequences:** Keep all 10 apps installed. Do not merge or remove apps merely to satisfy the stale count.

## ADR-A-002 — Product category cardinality

- **Status:** Accepted
- **Decision:** A `Product` belongs to exactly one `Category` through a required foreign key.
- **Rationale:** The schema field list specifies singular `category_id`; the ER diagram's many-to-many-looking marker is ambiguous.
- **Consequences:** Category filtering and administration use one category per product in v1. Multiple categories require a future explicit migration to a join table. A category referenced by a product is protected from deletion.

## ADR-A-003 — Authentication model

- **Status:** Accepted
- **Decision:** `accounts.Customer` is the custom `AUTH_USER_MODEL` from the initial migration. It uses unique email authentication and has no username field.
- **Rationale:** Customer profiles, saved addresses, wishlists, order history, and Django permissions need one stable account identity. Replacing Django's user model after migrations is unsafe.
- **Consequences:** All user relations use `settings.AUTH_USER_MODEL`; no code imports Django's concrete `User`. `AUTH_USER_MODEL = "accounts.Customer"` must be set before the first migration is generated or applied.

## ADR-A-004 — Guest identity and checkout ownership

- **Status:** Accepted
- **Decision:** Guest checkout creates no `Customer` row. A guest `Order` has `customer = NULL`; its immutable checkout snapshot in `shipping_address` must include the guest's email, name, phone, and delivery address.
- **Rationale:** An order is a commercial record, while a customer row represents an actual registered account. Creating passwordless pseudo-accounts would conflate those identities and collide with later registration by the same unique email.
- **Consequences:** Guest status is determined by `Order.customer_id is None`. Guest orders remain
  unowned and are accessed only through their signed public status and invoice links; registration
  never attaches them to an account, and there is no later claim endpoint. Deleting a customer sets
  existing registered-customer order ownership to `NULL` and does not delete the orders.

## ADR-A-005 — Unusable passwords

- **Status:** Accepted
- **Decision:** An unusable password is an authentication state, not a guest-identity marker.
- **Rationale:** Registered accounts created for invitation, administrative setup, or password-reset workflows may temporarily have unusable passwords; guests have no customer row at all.
- **Consequences:** Do not implement `Customer.is_guest` as `not has_usable_password()`. Do not create a guest with `create_user(email, password=None)`. Code determines guest ownership only from the nullable order relation.

## ADR-A-006 — MySQL driver

- **Status:** Accepted
- **Decision:** PyMySQL is the v1 MySQL driver and is installed through `pymysql.install_as_MySQLdb()` before Django initializes its MySQL backend.
- **Rationale:** It is pure Python, works consistently across the supported development platforms, and supports the transactions and row locks required by the inventory design without a native compiler toolchain.
- **Consequences:** `PyMySQL` is a runtime dependency. Django continues to use `django.db.backends.mysql`; application code does not depend on driver-specific APIs.

## ADR-A-007 — Storage engine and character set

- **Status:** Accepted
- **Decision:** Every environment uses MySQL 8 with InnoDB tables and `utf8mb4`; this is configured before the first migration rather than repaired afterward.
- **Rationale:** Inventory correctness depends on real row-level locking and transactions, and the storefront must preserve the full Unicode range.
- **Consequences:** The MySQL server starts with `character-set-server=utf8mb4` and `collation-server=utf8mb4_0900_ai_ci`. Each Django connection sets `charset=utf8mb4`, `default_storage_engine=INNODB`, and strict SQL mode. The first catalog migration alters and verifies the active database defaults before creating domain tables and normalizes Django's pre-created migration-recorder table. Test databases explicitly use the same charset and collation. Migration QA verifies table engines and collations through MySQL metadata.

## ADR-A-008 — Inventory concurrency red contract

- **Status:** Fulfilled by Epic B-1 — the marker is removed and the gate runs live.
- **Decision:** The two-buyers/one-unit concurrency test was committed as `pytest.mark.xfail(strict=True)` while the atomic inventory service did not exist; B-1 implemented `reserve_stock` with `transaction.atomic()` + `select_for_update()`, removed the marker, and the same test now passes normally.
- **Rationale:** The repository instructions require post-change QA to remain green, while the handover requires the failing concurrency contract to exist before implementation.
- **Consequences:** The gate runs on real MySQL/InnoDB on every push and asserts exactly one successful buyer. The M2 release gate (20 parallel buyers, 10 units, exactly 10 successes and 0 oversells) runs alongside it in `tests/test_inventory.py`.

## ADR-A-009 — Annual order number allocation

- **Status:** Accepted
- **Decision:** Order numbers use `MD-YYYY-NNNNN`, where `YYYY` is the `Asia/Manila` business year and the counter starts at 1 for each year.
- **Rationale:** Computing `MAX(order_no) + 1` races under concurrent checkout.
- **Consequences:** One unique `OrderNumberSequence` row exists per four-digit year. Allocation occurs inside `transaction.atomic()` while holding `select_for_update()` on that row; Django recovers a first-row creation race under the unique year constraint. Numbers are unique and increasing within a year, but gaplessness is not promised. Allocation stops explicitly after `99999` so the locked five-digit format never widens. Sequence rows are retained.

## ADR-A-010 — Deletion policy

- **Status:** Accepted
- **Decision:** Historical commerce and inventory evidence is retained; disposable/profile-owned data cascades; identity removal detaches orders.

| Parent or reference | Policy | Required behavior |
|---|---|---|
| `Category → Product` | `PROTECT` | A used category cannot be deleted. |
| `Product → ProductVariant` | `CASCADE` | Removing a never-used product removes its variants; protected history can still block the operation. |
| `ProductVariant → StockRecord` | `CASCADE` | A removable variant also removes its current counter row. |
| `OrderItem → ProductVariant` | `PROTECT` | A sold SKU cannot be hard-deleted. |
| `StockMovement → ProductVariant` | `PROTECT` | A SKU with ledger history cannot be hard-deleted; deactivate it instead. |
| `Order → Customer` | `SET_NULL` | Account erasure preserves the order and its checkout snapshot. |
| `WishlistItem → Customer/Product` | `CASCADE` | Profile-owned bookmarks disappear with either owner. |
| `Review → Customer/Product` | `CASCADE` | Removing the author or product removes its public review content. |
| `Review → Order` | `PROTECT` | Verified-purchase evidence protects its order. |
| `StockMovement → Order` | `PROTECT` | Referenced audit evidence protects its order. |
| `OrderItem/Payment/Shipment → Order` | `CASCADE` | Children follow an explicitly authorized order purge; normal application flows never hard-delete orders. |

- **Consequences:** `StockMovement` is append-only: application updates and deletes are rejected. Orders and catalog entities with history are archived or deactivated, not hard-deleted.

## ADR-A-011 — Cancellation and refund state edges

- **Status:** Accepted
- **Decision:** The only legal order transitions are:

| From | To |
|---|---|
| `pending` | `paid`, `cancelled` |
| `paid` | `packed`, `refunded` |
| `packed` | `shipped`, `refunded` |
| `shipped` | `delivered`, `refunded` |
| `delivered` | `refunded` |
| `cancelled` | none; terminal |
| `refunded` | none; terminal |

- **Rationale:** Cancellation applies only before confirmed payment. Once payment has been confirmed, the compensating exit is a refund.
- **Consequences:** Cancelling a pending order releases reservations but does not write a stock movement because reservations never changed `qty_on_hand`. Refunding restores stock exactly once with positive `return` movements and updates payment/order state atomically and idempotently. Direct status assignment is forbidden; services use the transition API.

## ADR-A-012 — Demo catalog and inventory seed

- **Status:** Accepted
- **Decision:** `seed_demo` creates the following stable catalog:

| Product | Category | Code | Colors | Base price (centavos) |
|---|---|---|---|---:|
| Metro Essential Tee | T-Shirts | `MTEE` | Jet Black (`JBLK`), Concrete White (`CWHT`) | 89900 |
| Skyline Pullover Hoodie | Hoodies | `SHOD` | Midnight Navy (`MNAV`), Asphalt Gray (`AGRY`) | 189900 |
| Transit Utility Cargo Pants | Pants | `TCAR` | Route Olive (`ROLV`), Signal Black (`SBLK`) | 219900 |
| Platform Twill Overshirt | Overshirts | `POVR` | Rust Line (`RUST`), Steel Blue (`STBL`) | 169900 |
| Night Route Windbreaker | Outerwear | `NRJK` | Neon Lime (`NLIM`), Carbon Black (`CBLK`) | 249900 |

- **Axes:** Each product gets all sizes `XS`, `S`, `M`, `L`, `XL`, `XXL` × its two listed colors × all fits `slim`, `regular`, `oversized`: 36 variants per product and 180 variants total.
- **SKU:** `MD-{PRODUCT_CODE}-{SIZE}-{COLOR_CODE}-{FIT_CODE}`, with fit codes `SLM`, `REG`, and `OVR`.
- **Initial stock:** Every newly created variant has `qty_on_hand = 10`, `qty_reserved = 0`, and `low_stock_threshold = 5`.
- **Audit:** Creating a stock row and its single `+10` `restock` movement is one atomic operation.
- **Idempotency:** Stable category/product slugs and deterministic SKUs are natural keys. Re-running the command may update catalog metadata, but it never duplicates rows, resets an existing stock counter, or creates another initial movement for existing stock.

## ADR-A-013 — Integer-centavo utility boundary

- **Status:** Accepted
- **Decision:** Shared money helpers accept actual Python integers only, reject Booleans and implicit numeric coercion, and enforce the MySQL unsigned-INT ceiling of `4_294_967_295` centavos before persistence or arithmetic.
- **Rationale:** A single strict boundary prevents float precision loss, Python's `bool`-as-`int` behavior, inconsistent formatting, and late database overflow errors.
- **Configuration:** `CURRENCY_CODE = "PHP"`, `CURRENCY_SYMBOL = "₱"`, and `CURRENCY_MINOR_UNITS = 2` live in shared settings. Presentation reads these settings rather than embedding currency literals.
- **Arithmetic:** `multiply_centavos()` requires quantity of at least one. `sum_centavos()` accepts nonnegative integer iterables. Both reject an overflowed result.
- **Signed values:** `require_centavos(..., allow_negative=True)` is an explicit opt-in for future signed report calculations. Ordinary formatting, prices, and totals remain nonnegative.
- **Presentation:** `format_centavos()` is the sole domain formatter. The storefront `peso` template filter delegates valid values to it and renders an empty string for malformed context so a presentation defect cannot produce a page-level server error.

## ADR-A-014 — Provider-neutral single-host staging topology

- **Status:** Accepted; public deployment evidence remains pending.
- **Decision:** M1 staging uses one Linux host running Caddy, one non-root Gunicorn/Django container, and MySQL 8.4 through Docker Compose. Only Caddy publishes host ports. MySQL is isolated on an internal Docker network and persists in a named volume.
- **Rationale:** One host is the smallest topology consistent with HTTPS, InnoDB, persistent data, the approximate USD 25 monthly infrastructure ceiling, and a provider-neutral handoff. A managed application plus managed database is not assumed to fit the locked budget.
- **Application runtime:** Gunicorn uses one worker with four threads. Source is root-owned; UID/GID `10001` can write only generated static output and its home. Capabilities are dropped and `no-new-privileges` is enabled.
- **Startup:** The entrypoint validates `STAGING_SEED_DEMO`, collects static files, applies migrations, optionally runs the idempotent demo seed, and then replaces itself with Gunicorn. This startup sequence assumes exactly one application container.
- **Ingress and static assets:** Caddy performs automatic HTTPS, redirects HTTP, adds conservative response headers, compresses responses, and proxies to Gunicorn. WhiteNoise serves hashed collected assets; product media remains reserved for object storage and CDN work in a later epic.
- **Configuration:** Production and staging imports fail on missing values, weak/example application secrets, weak/example application database passwords, wildcard/URL/public-IP host values, malformed database ports, non-HTTPS or malformed CSRF origins, ambiguous Boolean flags, or disagreement among the proxy hostname and Django allowlists. The insecure HTTP override is limited to localhost smoke tests. CI runs Django deployment checks at warning level while staging silences only `security.W021`, because HSTS preload is deliberately deferred until the public-domain bake-in is complete.
- **Temporary seed browser:** `/staging/seed/` is a GET-only, feature-gated M1 acceptance surface that lists active seeded products and aggregate variant counts. It returns 404 for every method while disabled and must be disabled or removed when C-2 supplies the real catalog.
- **Operations:** All service logs rotate at three files of 10 MiB. Database and Caddy state use named volumes. Database dumps, environment files, and SQL files are excluded from Git and Docker build contexts. Backup commands create a mode-0700 directory under a restrictive umask and keep the root password out of the `mysqldump` argument list. The runbook verifies forced container recreation rather than a process-only restart.
- **Continuous verification:** CI checks migration drift and forward/reverse/forward execution, validates shell/Compose/Caddy/Dockerfile contracts, builds the staging image, verifies UID/GID/mode/write boundaries, and runs an ephemeral localhost HTTPS stack through seed, admin/static, forced-recreation, and exact persistence checks before removing its volumes.
- **Scaling consequence:** Do not scale the app container or Gunicorn worker count while migrations and future APScheduler jobs run in-process. Horizontal scaling requires a separate release migration job and dedicated scheduler process.
- **Gate consequence:** Local disposable HTTPS validation proves deployability but does not satisfy “staging live.” The public M1 evidence (real hostname, DNS record, trusted certificate, public smoke checks) requires operator-held host/DNS access and remains an open operator action; Epic B implementation proceeded because it has no technical dependency on the public host, only on the schema and QA gates, and deferring it would idle the only workstream available to this repository.

## ADR-B-001 — Reservation lifecycle and locking discipline

- **Status:** Accepted
- **Decision:** A `Reservation` row represents one checkout hold: `active → committed | released | expired`; the three non-active states are terminal.
- **Semantics:**
  - Reservations mutate only `qty_reserved`; they never change `qty_on_hand` and therefore never write `StockMovement` rows. Only committing a reservation (payment confirmed) decrements both counters and appends the single `sale` movement in the same transaction.
  - `release_reservation` is idempotent for already-ended holds because the shopper-abandon path and the TTL sweep race legitimately; releasing a `committed` hold raises.
  - An `active` hold past `expires_at` is still committable: only the sweep expires holds, so a payment that lands before the sweep is honored rather than oversold or refunded.
  - `reserve_stock` raises `StockRecord.DoesNotExist` for untracked SKUs — an unstocked variant must never be silently sellable.
- **Locking:** Every mutation runs inside `transaction.atomic()` with `select_for_update()`. Global lock order is Reservation before StockRecord wherever both are needed; `reserve_stock` locks only the StockRecord. One global order makes lock-cycle deadlocks impossible. The TTL sweep collects candidate IDs without locks, then re-validates each row under its own per-row transaction so a poisoned row cannot roll back the rest of the sweep and a racing commit/release always wins or loses cleanly.
- **Consequences:** `apps/inventory/services.py` is the only writer of stock counters and movements. Epic D must call `commit_reservation` from the webhook handler and treat `InvalidReservationState` as "re-reserve or refund".

## ADR-B-002 — Stock adjustment boundary

- **Status:** Accepted
- **Decision:** `adjust_stock` accepts only `restock`, `return`, and `adjustment` reasons; `sale` is rejected because sales exist only as committed reservations (single ledger writer per reason).
- **Semantics:** Restock/return must be positive; adjustment must be nonzero; any change that would leave `qty_on_hand` below `qty_reserved` is rejected because it would strand promised holds and violate `chk_reserved_lte_on_hand`.
- **Consequences:** Epic E-4 refunds restore stock through `adjust_stock(reason="return", ref_order=...)`, giving the return movement its order reference for free.

## ADR-B-003 — In-process job schedule

- **Status:** Accepted
- **Decision:** One APScheduler process (the `run_scheduler` management command) runs two jobs: the reservation sweep every 60 seconds and the low-stock scan every 60 minutes, both with `coalesce=True` and `max_instances=1`.
- **Rationale:** A 15-minute TTL plus a 60-second sweep bounds abandoned-checkout stock restoration at ~16 minutes, exactly the M3 gate ceiling. Hourly low-stock scans match a single-warehouse restock cadence without alert spam.
- **Consequences:** Exactly one scheduler instance may run per environment (ADR-A-014). Jobs call `close_old_connections()` around their work because no request cycle recycles MySQL connections for them. Low-stock alerting degrades to a log line when `LOW_STOCK_ALERT_RECIPIENTS` is empty — the email leg is an enhancement around the scan, never a dependency.

## ADR-C-001 — Client-side cart contract

- **Status:** Accepted
- **Decision:** The cart lives in `localStorage` under `metrodrip_cart` as a list of `{variantId, sku, productName, size, color, fit, price, priceDisplay, qty}` objects (camelCase keys). Checkout maps lines to the API's `{variant_id, qty}` shape and the server re-prices every line from the database.
- **Rationale:** One canonical shape ends the camelCase/snake_case split that silently broke the cart→checkout handoff; client-held prices are display hints only, never billing inputs.
- **Consequences:** `/api/cart/availability/` is advisory (cart page badges); the checkout POST is the authoritative stock/price validation. Cart quantities are clamped server-side to 1–99 across at most 20 lines.

## ADR-D-001 — Development-only mock payment completion

- **Status:** Accepted
- **Date amended:** 2026-08-24
- **Decision:** Development selects the registered `simulated` or `paymongo` provider through
  `PAYMENT_PROVIDER`. An explicit valid value wins. When the value is unset/blank, development
  selects PayMongo only when a non-empty `PAYMONGO_SECRET_KEY` exists and otherwise selects the
  simulator. Invalid values and explicit keyless PayMongo fail during settings import. Deployed
  settings pin PayMongo and refuse simulated payments. The simulated confirmation path remains
  server-gated as specified by ADR-H-003 and calls the same idempotent `confirm_order_paid()` service
  as the signature-verified webhook.
- **Rationale:** The demo must complete end-to-end (pay → stock decrement → email) without provider credentials, while Hard Invariant 3 (webhook = payment truth) stays intact everywhere deployed.
- **Consequences:** An operator with sandbox credentials can still force a simulated walkthrough,
  while a typo cannot survive until checkout. All confirmation side effects (payment flip,
  reservation commit, sale movement, Paid transition, notifications) live in
  `confirm_order_paid()`; the webhook and simulator remain thin callers.

## ADR-D-002 — Checkout transaction shape

- **Status:** Accepted
- **Decision:** Checkout validates the payload, then in ONE `transaction.atomic()` block: creates the Order with final totals (subtotal from effective variant prices + zone fee) so `chk_order_total_reconciles` holds at INSERT, reserves stock per line with the reservation linked to the order, and writes the order items. Any `InsufficientStock` raises out of the block, rolling back everything (order number included).
- **Rationale:** The prior flow committed half-built orders (early `return` inside atomic), billed `base_price` ignoring overrides, and left holds without an order link that the webhook could only match heuristically — able to commit another shopper's hold.
- **Consequences:** A PayMongo session failure after commit releases the order's holds immediately instead of stranding them for the TTL; the shopper gets a retryable 502. The webhook commits exactly `order.reservations`, with a re-reserve fallback (and CRITICAL log, never an oversell) if the TTL sweep won the race.

## ADR-D-003 — Webhook signature policy

- **Status:** Accepted
- **Decision:** The PayMongo webhook verifies `Paymongo-Signature` (HMAC-SHA256 of `<t>.<raw body>` against `te`/`li`) with constant-time comparison before any parsing; a missing `PAYMONGO_WEBHOOK_SECRET` rejects every event (fail closed). Verified events with an unknown order reference are acknowledged with 200 and an ERROR log so PayMongo stops retrying while the daily reconciliation surfaces the mismatch.
- **Rationale:** Hard Invariant 3 — unsigned or unverifiable events must never flip payment state; retry storms on unknown references would only amplify noise.
- **Consequences:** Tests pin: valid-signature confirm, bad/missing-signature 400, missing-secret 400, replay idempotency, unknown-reference 200.

## ADR-D-004 — Tokenized success and status pages

- **Status:** Accepted
- **Decision:** Both `/checkout/success/<token>/` and `/order/<token>/` accept only the `Signer`-signed order id. The raw `MD-YYYY-NNNNN` number never appears in a URL.
- **Rationale:** Order numbers are sequential and guessable; both pages render checkout PII, so numbering must not be an access credential (FR-15's tokenized-link requirement applies to both pages).
- **Consequences:** Emails, templates, and views all mint tokens with the same default `Signer`, so links are interchangeable; templates use the `sign` filter in `storefront_tags`.

## ADR-C-002 — Two-level category taxonomy

- **Status:** Accepted. Revises ADR-A-002: a product still belongs to exactly one category, but a category may now itself belong to a parent.
- **Decision:** `Category` gains a nullable self-referencing `parent` (PROTECT, `related_name="children"`) capped at two levels. Every main category gets `Men` and `Women` children whose slugs are parent-prefixed (`hoodies-men`). `Category.name` loses its global uniqueness so "Men" can repeat under every parent; `slug` remains globally unique and is the only stable identifier.
- **Rationale:** The alternative — separate `MainCategory` and `Subcategory` tables — enforces exactly two levels structurally but duplicates every category behaviour, forks `Product.category`, and doubles the admin surface. A self-reference is the smallest extension of the existing domain and keeps one FK on `Product`.
- **Consequences:**
  - Depth and self-parenting are enforced in `Category.clean()`, not by the database. MySQL rejects a CHECK constraint that references an AUTO_INCREMENT column (error 3818), so even `parent_id <> id` is unavailable; depth needs a join and could never have been a CHECK. Code paths that bypass ModelForms are trusted to supply valid data.
  - Sibling-name uniqueness is likewise split: `UniqueConstraint(parent, name)` covers children, but MySQL treats each NULL `parent_id` as distinct, so duplicate *root* names are caught only by `clean()`. A conditional constraint is not an option — MySQL has no partial indexes and Django would silently skip it (models.W036).
  - Filtering a main category must span the branch: `category__slug=X OR category__parent__slug=X`. Products assigned directly to a root before the hierarchy existed keep working, and a child slug matches only its own products because the tree cannot go deeper.
  - Every storefront page now issues two extra catalog queries for the menu. The context processor is lazy, so pages that do not render navigation pay nothing.

## ADR-C-003 — Placeholder catalog as a separate command

- **Status:** Accepted
- **Decision:** Bulk placeholder data lives in `seed_mock_catalog`, not in `seed_demo`. Products are flagged `is_mock`; `--count` (default 100) is the number of *placeholders* to maintain, independent of the hand-authored catalog. Each placeholder gets one variant, one stock record, and one opening restock movement, created in a single transaction.
- **Rationale:** The five-product / 180-variant output fixed by ADR-A-012 is a contract the staging preview and several tests assert against. Inflating it to reach a catalog-size target would break those; a separate command leaves the contract intact.
- **Consequences:**
  - Idempotency comes from natural keys — `mock-<parent>-<audience>-<seq>` — not from counting, so a rerun resolves to the same slugs and writes nothing. Existing stock, reservations, and thresholds are never read back or rewritten.
  - The command re-establishes the audience children itself rather than trusting migration 0003, which back-fills only the categories that existed when it ran. A database migrated before being seeded has none.
  - A rerun heals a placeholder missing its inventory rows (partially reversed migration, partial restore) but posts an opening movement only when the ledger is empty. StockMovement is append-only, so a duplicated opening balance could never be corrected.
  - Exceeding the target is reported, never corrected: the command has no delete path.

## ADR-F-001 — Two back-office consoles, not one admin with permissions

- **Status:** Accepted. Realises Epic F-2 and separates the Merchant/Seller requirements from the Administrator requirements.
- **Decision:** The back office is two Django `AdminSite` instances mounted at different paths. `/admin/` is `AdministratorSite` — accounts, roles, shipping fees, platform settings, audit trail. `/merchant/` is `MerchantSite` — catalog, inventory, orders, payments, shipments, site content, review moderation. Every model is registered on exactly **one** of them; a test asserts the intersection is empty. `Customer.role` (`customer` | `merchant` | `administrator`) selects the console and `is_staff` remains the gate, so both are required. Superusers are admitted to both.
- **Rationale:** A single site plus per-model permissions was the obvious alternative and is not equivalent. Django builds the admin index from the **registry**, not from permissions, so a merchant would still be shown "Accounts", "Shipping Zones" and "Audit Trail" headings with empty tables beneath them — the separation would be presentational. Two registries make it structural: the URL for an administrator model does not exist under `/merchant/`, so guessing it returns 404 rather than 403. Separate sites also give each console its own login form, branding, and denial page for free.
- **Consequences:**
  - `admin.site` stays the administrator console (`AdminConfig.default_site`), which preserves the `admin:` URL namespace that Django's own templates and every existing `reverse("admin:…")` call depend on. Only the merchant console needed a new namespace.
  - `config/consoles.py` must not be imported before the app registry is ready, so `default_site` is a dotted string resolved in `AdminConfig.ready()` and the role vocabulary lives in `apps/accounts/roles.py`, which imports no models.
  - Role checks had to be added to the **login form**, not just to `has_permission`. `AdminAuthenticationForm` only checks `is_staff`, which a merchant has, so `/admin/login/` would have accepted merchant credentials, redirected to the index, been refused, and bounced back to the form — an endless loop. Rejecting at the form turns it into one clear message.
  - A signed-in user who lands on the wrong console gets a 403 page naming their own console, not a second login form. Re-prompting would imply their password was wrong. That page cannot use `admin/base_site.html`, which builds a sidebar from `available_apps` the user has no permission to enumerate, so it is standalone with inlined CSS.
  - `django.contrib.flatpages` registers itself on the default site during autodiscovery; `apps.cms` unregisters and re-registers it on the merchant console. This depends on `flatpages` sorting before `apps.cms` in INSTALLED_APPS.
  - Shipping is deliberately split across both consoles: `ShippingZone` (what customers are charged) is administrator, `Shipment` (this parcel's waybill) is merchant. A merchant can dispatch all day without repricing delivery.
  - Payments and orders live only on the merchant console. Administrator oversight is the audit trail, not a duplicate screen; an administrator who genuinely needs the row holds a superuser account.

## ADR-F-002 — Console permissions derived from the registries

- **Status:** Accepted
- **Decision:** `sync_console_roles` builds the `Merchants` and `Administrators` groups by walking each console's `_registry` and probing each `ModelAdmin`'s `has_add/change/delete_permission` with a stub request whose user passes every permission check. `view` is granted unconditionally; the other three are granted only where the ModelAdmin allows them. Membership is synced from `role` in the same pass and is exclusive — a re-roled account loses the old group.
- **Rationale:** The role gate is not the only check; Django still asks `has_perm` per model. A new merchant with the correct role and no permissions signs in to a completely empty console, which reads as a bug and gets "fixed" by granting superuser — destroying the separation the role was introduced to create. Deriving grants from the registry rather than a hand-written list means moving a model between consoles (a one-word change at the `admin.register` call) is picked up on the next run instead of leaving a stale grant behind.
- **Consequences:**
  - Read-only admins are respected automatically: `StockMovement`, `Reservation`, `Payment`, and `LogEntry` come back view-only without being named anywhere in the command. The probe is what makes this work, and it is the reason the command reads `_registry` — a private attribute, used deliberately so ownership stays declared at the registration site.
  - `permissions_for_site` pairs `(content_type_id, codename)` exactly rather than filtering the two columns independently, which would over-match where two models share a codename.
  - Permissions that `post_migrate` has not created yet are reported, not raised on: the remaining grants are still correct and a later `migrate` completes the set.
  - `create_console_account` exists because `createsuperuser` only makes superusers, and a superuser reaches both consoles — using it is the fastest way to accidentally prove nothing about the separation.

## ADR-C-004 — Per-visitor correctness beats a shared homepage cache

- **Status:** Accepted. Fixes a live defect found while verifying ADR-F-001.
- **Decision:** `storefront.homepage` keeps `@cache_page(60 * 5)` but adds `@vary_on_cookie` **below** it, so the Vary header is patched before `cache_page` chooses its key.
- **Rationale:** The homepage renders `base.html`, whose navbar is per-user — "Log In" vs "Account", and now the staff console shortcut. `cache_page` is a view decorator and stores the response before `SessionMiddleware.process_response` adds `Vary: Cookie`; the header reached the browser but arrived too late to affect the cache key. The first render of `/` was therefore replayed to every visitor for five minutes, in both directions.
- **Consequences:**
  - Anonymous visitors have no session cookie until something writes to the session, so they still share one cache entry — the NFR-1 benefit is kept for the traffic that dominates this page. Signed-in visitors each get their own entry.
  - Asserting `Vary: Cookie` on the response is **not** a regression test for this: the header is present with or without the fix. Only the cached body distinguishes the two states, so the tests compare rendered content across sessions.
  - The suite's settings use `DummyCache`, which makes every page-cache assertion vacuous. The three tests that cover this install a real `LocMemCache` through a fixture and clear it on both sides.

## ADR-P3-001 — Microservice refactor (Strangler Fig)

- **Status:** Accepted
- **Decision:** The inventory domain logic has been extracted into a standalone FastAPI microservice. The Django monolith now uses HTTP calls to interact with inventory during synchronous requests (e.g., checkout reservations) and Redis Pub/Sub events for asynchronous updates (e.g., checkout completion/cancellation).
- **Rationale:** Separates the catalog read-heavy workload from the write-heavy inventory ledger while preserving Hard Invariant 1 (No overselling).
- **Consequences:** The \pps.inventory\ models remain in Django for now but are no longer directly queried by storefront views for live stock availability. Local dev requires running the FastAPI service and a Redis instance (added to docker-compose).


## ADR-P3-002 — Inventory provider registry; `local` is the default

- **Status:** Accepted (amends ADR-P3-001)
- **Decision:** `apps/inventory/services.py` is a thin facade over an `InventoryProvider` chosen by `INVENTORY_PROVIDER` (`local` | `service`), mirroring the payments/shipping/notification registries. **`local` is the default.**
- **Rationale:** The Strangler-Fig extraction replaced the row-locked in-process implementation outright, and the service does not yet honour the full contract: `commit_reservation` and `release_reservation` are fire-and-forget Redis publishes with no transactional guarantee, and `adjust_stock`, `release_expired_reservations`, and `scan_low_stock` were stubs that raised or returned empty. That silently broke Hard Invariants 1 and 4 — 19 tests, including the M2 no-oversell release gate, were failing.
- **Consequences:** The proven Epic B implementation lives in `providers/local.py` and is what every environment runs unless explicitly opted out. `providers/service.py` preserves the HTTP/Redis client verbatim for continued microservice work, but `INVENTORY_PROVIDER = "service"` must not be used where the hard invariants are load-bearing until the service implements commits, adjustments, the TTL sweep, and the low-stock scan transactionally. Domain exceptions moved to `apps/inventory/exceptions.py` so providers and callers share one taxonomy.

## ADR-H-001 — Public mobile API surface

- **Status:** Accepted
- **Decision:** The mobile app consumes a dedicated public API at `/api/mobile/v1/` (D-12), separate from the internal service-to-service endpoints. It is JWT-authenticated (SimpleJWT, 30-minute access / 30-day refresh with rotation + blacklist), throttled (120/min per user, 60/min anonymous, 10/min on credential endpoints), paginated at 20 items maximum (NFR-18), and requires an `X-Client-Version` header on every request (NFR-22).
- **Rationale:** Internal endpoints assume a trusted network and carry no user-scoped auth, rate limiting, or versioning lifecycle. Exposing them publicly would be the single largest attack surface in the system (risk register).
- **Consequences:** Every non-2xx response uses one documented envelope — `{"error": {"code", "message", "fields?"}}` — so the client switches on `code` and maps `fields` onto form inputs. Breaking changes ship as `/v2` with `/v1` maintained at least 90 days; the version header makes app-version correlation possible.

## ADR-H-002 — One checkout service, many clients

- **Status:** Accepted
- **Decision:** `apps/orders/checkout.py::place_order()` is the single checkout implementation. The web storefront view and the mobile API endpoint are both thin callers that supply intent (variant ids, quantities, contact block, zone) and success/cancel URLs.
- **Rationale:** D-13 forbids business logic on the device, but the real risk is *duplicated* logic on the server — two checkout paths would drift, and one of them would eventually oversell. Prices, totals, and stock decisions are computed once, in one place, inside one atomic block.
- **Consequences:** Client-supplied prices and totals are ignored entirely (pinned by test). The mobile deep-link success URL is templated with `__TOKEN__` and substituted after the order row exists, because the signed status token needs the order id. Checkout retries up to three times on a MySQL deadlock (error 1213): the victim transaction rolls back completely, so rebuilding is safe and the 20-parallel-buyer gate stays deterministic.

## ADR-H-003 — Simulated payment completion is server-gated

- **Status:** Accepted
- **Decision:** `POST /checkout/confirm-simulated/` exists only while `PAYMENT_PROVIDER == "simulated"`; under any real provider it returns 404. It calls the same idempotent `confirm_order_paid()` service the signature-verified webhook uses.
- **Rationale:** The app must complete an end-to-end purchase in demo and grading environments without PayMongo credentials, while Hard Invariant 3 (webhooks are payment truth) stays intact everywhere deployed. Gating on the server — not on a client flag — means a tampered client cannot confirm its own payment.
- **Consequences:** Pinned by two tests: the endpoint 404s under `paymongo`, and replaying it never double-decrements stock or resends notifications.

## ADR-H-004 — Push notifications and the notification centre

- **Status:** Accepted
- **Decision:** `Order.transition_to()` fires a `transaction.on_commit` hook that writes a `Notification` row and pushes to the customer's registered devices; `Shipment.save()` does the same on the Out-for-Delivery edge (which has no order-status counterpart). Delivery goes through a `PUSH_PROVIDER` registry (`simulated` | `expo`), simulated by default.
- **Rationale:** FR-27 requires push at Paid / Shipped / Out for Delivery / Delivered, and FR-28 requires the in-app centre to mirror them. Hooking the transition itself means every path — admin action, webhook, mock confirmation — notifies identically and only after the state change actually commits.
- **Consequences:** Push failures are logged and swallowed; an outage can never fail or roll back a business transition (section 7 enhancement-tier rule). Guest orders (no customer row) are skipped silently. The centre's unread count is computed server-side across all pages, not per page.

## ADR-H-005 — Mobile session storage and biometric unlock

- **Status:** Accepted
- **Decision:** The JWT pair lives exclusively in `expo-secure-store` (Keychain / Keystore). Biometric unlock (FR-23) is an opt-in gate applied on cold start *after* an initial password sign-in; it never replaces the password as the credential.
- **Rationale:** NFR-19. Biometrics authorize access to an already-established session — treating them as a credential would mean the device, not the server, decides who you are.
- **Consequences:** With the preference on, a stored session starts locked and the splash screen prompts. Failing or cancelling leaves the app usable as a guest. Logout blacklists the refresh token server-side and clears the enclave.

## ADR-H-006 — Expo 57 and Continuous Native Generation

- **Status:** Accepted
- **Date:** 2026-08-24
- **Context:** The client was on an out-of-support mobile stack with duplicated native projects,
  stale Android targets, and application configuration split between generated files and
  `app.json`. Expo Doctor could not prove that changes to the config would reach a build. The 2026
  Android and Apple submission toolchains also moved beyond the checked-in targets.
- **Decision:** Upgrade to Expo 57.0.18, React Native 0.86.3, React 19.2.3, TypeScript 6.0.3, and
  React Navigation 7 under Node 22.13+. Use `expo-dev-client`, not Expo Go. Treat `app.json` and Expo
  config plugins as the durable native source of truth; ignore generated `android/` and `ios/`
  directories and recreate them with clean prebuild. Android compiles/targets API 36 with Build
  Tools 36.0.0 and minimum API 24 under JDK 17. A versioned config plugin enables Android
  core-library desugaring with `desugar_jdk_libs` 2.0.3 so Java time APIs remain compatible with
  API 24–25. iOS config declares minimum 16.4, local-network and Face ID usage,
  non-exempt-encryption status, and bundle identifier `ph.metrodrip.app`.
- **Patch alignment (2026-08-29):** The initial Expo 57 baseline was advanced to Expo 57.0.18,
  React Native 0.86.3, and the module patches reported by `expo install --check`. This is a
  compatibility patch within the accepted SDK/CNG architecture, not a new platform decision.
- **Lint compatibility constraint:** `eslint-config-expo` 57.0.2 declares `eslint >=8.10`, but its
  bundled `eslint-plugin-react` 7.37.5 crashes under ESLint 10.9.1 while loading
  `react/display-name`. Keep ESLint 9.39.5 until that preset/plugin contract is updated; the
  unsupported-line npm warning is preferable to a lint command that cannot execute.
- **Alternatives considered:** Keeping the native directories would preserve direct native editing
  but retain two sources of truth and require manual upgrades. Expo Go would shorten onboarding but
  cannot guarantee this app's native module set or SDK lifecycle. Both were rejected.
- **Consequences:** Durable native work must be represented in Expo config or a config plugin;
  hand-edits inside generated projects are disposable. CI checks Expo dependency alignment,
  Doctor, typecheck, flat-config lint, Android/iOS exports, clean Android prebuild, and an API 36
  debug assembly. Android-emulator transport is refined by ADR-H-007; physical-device and iOS
  development retain `npm run android`/`npm run ios` followed by LAN-oriented `npm start`. EAS
  owner/project ID, final API URLs, brand
  assets, signing/store accounts, and remote-push credentials remain external launch inputs.
- **Verification / review trigger:** Linux/Android passed the complete mobile gate; one clean debug
  APK (`compileSdk`/`minSdk`/`targetSdk` 36/24/36) rendered on real API 24 and API 36 emulators.
  Native iOS remains unverified until the macOS/iOS checklist in
  `docs/images/README.md` passes; review this ADR on the next Expo SDK or store-target change.

## ADR-H-007 — Deterministic Metro and API readiness for the named Android emulator

- **Status:** Accepted
- **Date:** 2026-08-31
- **Context:** Expo's development launcher persists recently opened bundle URLs. The API 36 client
  contained both `http://192.168.31.232:8081` from a default LAN launch and
  `http://127.0.0.1:8081` from a localhost launch. Metro was listening only on host loopback, while
  an emulator restart had removed the ephemeral ADB reverse rule. Reopening the LAN entry therefore
  failed before React Native or Django loaded. The repository mixed LAN and localhost commands and
  did not restore or verify bundle transport after a restart.
- **Decision:** Keep `npm start` LAN-oriented for physical devices. The dedicated
  `MetroDrip_Pixel_API36` AVD instead uses `npm run android:emulator` for the first build/install and
  `npm run start:android:emulator` later. A cross-platform Node launcher verifies
  `emulator-5554`, full boot completion, database-backed Django readiness on host port 8080,
  installed-client state, and
  `adb reverse tcp:8081 tcp:8081`; it then starts Expo in localhost development-client mode and
  opens the exact encoded loopback URL. Expo 57's `run:android --no-bundler` still opens a URL and
  exposes no host flag, so that subprocess receives `REACT_NATIVE_PACKAGER_HOSTNAME=127.0.0.1` and
  its transient post-install launch also uses the reversed endpoint. An existing port is reused only
  when its Expo manifest identifies MetroDrip, package `ph.metrodrip.app`, and loopback host mode.
  `--allow-offline` is the sole explicit bypass for intentional offline-state testing.
- **Alternatives considered:** LAN-only Metro remains sensitive to interface changes, firewalls,
  and persisted addresses. Making generic `npm start` localhost-only would break the intended
  same-Wi-Fi physical-device workflow. Clearing development-launcher or application data would hide
  the symptom while discarding customer session/cart state and would not survive the next restart.
  Automatically owning Docker and Django from the mobile helper would hide process lifecycles and
  duplicate the existing full-stack editor task, so the helper reports exact recovery commands.
- **Consequences:** ADB reverse is recreated on every emulator command, and saved LAN history is
  bypassed without deletion. Port 8081 conflicts fail with an actionable message instead of opening
  the wrong bundle. A stopped or database-unready API now fails before an expensive native build or
  opaque offline app screen. Metro bundle transport (`127.0.0.1:8081` through ADB reverse) remains
  separate from the Django API transport (`10.0.2.2:8080`). VS Code/Antigravity uses the
  deterministic first-install command; physical devices and iOS retain the generic workflow.
- **Verification / review trigger:** Executed 2026-08-31: 15 Node tooling contracts passed, including
  ready, unhealthy, and refused API responses plus explicit offline mode. The reported offline state
  was reproduced with no listener on port 8080; starting healthy data services and Django restored
  an HTTP 200 catalogue response and the Product screen on the API 36 emulator. Earlier checks also
  reproduced the persisted-LAN failure; a cold API 36 boot began with no reverse mapping; the
  command restored `tcp:8081`, refused a foreign manifest, built/installed with a loopback URL, and
  rendered a clean CNG APK with `MainActivity` resumed and no connection exception. Review if the
  AVD/serial, Metro port, Expo manifest shape, CLI host semantics, or
  `REACT_NATIVE_PACKAGER_HOSTNAME` compatibility changes.

## ADR-E-001 — Courier webhook is signature-verified and fails closed

- **Status:** Accepted
- **Decision:** `/api/webhooks/courier/` verifies an HMAC-SHA256 of the raw body under `COURIER_WEBHOOK_SECRET` before parsing anything, and rejects every request when that secret is unset — the same fail-closed posture as the PayMongo handler (ADR-D-003).
- **Rationale:** The endpoint can mark an order Delivered. Unauthenticated, it would let anyone close out someone else's order, and Delivered is the state that unlocks reviews (FR-17) and ends the support window.
- **Consequences:** Carrier status vocabulary is normalized through `COURIER_STATUS_MAP`; unmapped statuses and unknown waybills are acknowledged with 200 (so carriers stop retrying) but logged for reconciliation. Only `delivered` has an order-level counterpart — the rest are shipment detail. Re-delivering the same status is a no-op, so carrier retries are safe. The `out_for_delivery` edge is what fires FR-27's fourth push, via `Shipment.save()`.

## ADR-E-002 — Line totals are computed in Python, never in templates

- **Status:** Accepted
- **Decision:** `OrderItem.line_total` returns `unit_price_snapshot * qty` in integer centavos, and every surface showing a line total reads it.
- **Rationale:** The admin invoice used `{% widthratio item.unit_price_snapshot 100 item.qty %}`, which does integer division and rounds. A ₱899.50 item bought three times printed as ₱2,697 instead of ₱2,698.50 — a money error on a document the customer keeps, and a direct violation of Hard Invariant 2's "format at display time only".
- **Consequences:** Django templates cannot multiply money safely, so no template may try. Pinned by a test using a price with centavos (`89950`) precisely because a round-peso price would hide the bug.

## ADR-E-003 — Packing slip and invoice are different documents

- **Status:** Accepted
- **Decision:** FR-19 ships two documents. The **packing slip** (merchant console, `/merchant/orders/order/<id>/packing-slip/`) is a warehouse pick list: SKU, attributes, quantity, tick boxes, waybill — and deliberately **no prices**. The **invoice** exists twice: the merchant copy and a customer-facing copy at `/order/<token>/invoice/`, authorized by the same signed token as the status page (ADR-D-004).
- **Rationale:** They serve different readers. A picker needs SKUs and counts; putting prices in the box is how gift orders leak their cost. The customer needs a financial record they can print or save as PDF.
- **Consequences:** The customer invoice is a standalone print document — it does not extend `base.html`, because a navbar and cart badge have no place on an invoice. It is reachable from both order history and the tokenized status page, so guests get it too.

## ADR-P2-001 — Server-side shipping zone resolution (FR-13)

- **Status:** Accepted
- **Decision:** Province/city → `ShippingZone` mapping lives in `apps/shipping/zones.py` and is the single source of truth. Web Places autocomplete and `GET /api/mobile/v1/shipping/zones/resolve/` both call it. The zone `<select>` / picker remains visible and authoritative as graceful degradation.
- **Rationale:** Client-only heuristics diverged between surfaces and could not be tested in pytest. A Cebu address must always select VisMin with the seeded fee on every client.
- **Consequences:** Adding a province means updating the token sets (or a future DB-backed map). Empty/unknown input returns null suggestion; checkout still requires an explicit `zone_id`.

## ADR-P2-002 — Correlation IDs on every request (SI FR-05 / NFR-12)

- **Status:** Accepted
- **Decision:** `CorrelationIdMiddleware` mints or propagates `X-Correlation-ID`, binds it via contextvar for logging (`cid=…` in the shared LOGGING format), echoes it on every response, and includes it in mobile error envelopes and storefront JSON errors.
- **Rationale:** One checkout must be greppable end-to-end without a service mesh or broker.
- **Consequences:** Inbound ids must match `[A-Za-z0-9._-]{8,128}` or they are replaced. Clients may send their own id; none is required.

## ADR-P3-003 — Target service map and strangler order (SOA course alignment)

- **Status:** Accepted (migration in progress — do not claim microservices as shipped)
- **Decision:** Regroup the modular monolith into five logical services. Free-tier constraint: **one MySQL 8 instance**, separate logical databases when split. Synchronous versioned REST/JSON only. No broker, mesh, or Kubernetes.

| Service | Absorbs (apps) | Schema (target) | Status |
|---|---|---|---|
| Identity | `accounts` | `db_identity` | monolith |
| Catalog & Inventory | `catalog`, `inventory` | `db_catalog` | inventory FastAPI experimental; **default `local`** (ADR-P3-002) |
| Orders & Payments | `orders`, `payments`, `reviews` | `db_orders` | monolith |
| Fulfillment & Notifications | `shipping`, `notifications` delivery | `db_fulfillment` | **notifications delivery** FastAPI opt-in (`NOTIFICATION_PROVIDER=http`) |
| Storefront BFF + Mobile API | `storefront`, `cms`, `mobile_api` | `db_content` | monolith |

- **Strangler order:** (1) Notifications **delivery** only. (2) Fulfillment. (3) Catalog/Inventory out of Orders with stock ownership never leaving Catalog. (4) Schema split + drop cross-service FKs. (5) Checkout saga. (6) Compose/Caddy per service.
- **Status correction (ADR-P3-008):** steps 1 and 2 were recorded here as "done as opt-in". They were not. `prod.py` discarded the provider environment variable and reassigned a hardcoded value, so `=http` was unreachable in every deployed environment — the sidecars shipped, but nothing could cut over to them. Both seams became genuinely opt-in-capable only with ADR-P3-008/009/010/011. Step 4 is designed and **deliberately not executed** (see ADR-P3-013).
- **Notifications extraction rule:** `Notification` / `DeviceToken` rows and mobile inbox stay in Django until the mobile API is re-pointed. The sidecar accepts email/SMS/push DTOs only. Failures are enhancement-tier (logged, never fail checkout). Default provider remains `console` / `email_sms`.
- **Rationale:** Course requires an SOA framing; an accurate modular monolith + started strangler defends better than an aspirational "we have microservices" claim that collapses under one question about stock ownership.
- **Consequences:** README and handover §1 Architecture status describe reality. M2 concurrency gate stays on Catalog/local inventory. Incomplete services must never become the default (lesson from ADR-P3-001/002).

## ADR-P5-001 — Accessibility-hardened storefront palette

- **Status:** Accepted
- **Decision:** Live tokens in `static/css/storefront.css` are the palette of record: muted `#63635C`, danger `#C2282D`, plus `on-volt`, `accent-text`, `elevated`, `muted-on-dark`. Dark mode via OS preference + manual toggle. Volt is background-only on light; text on volt is always `on-volt`.
- **Rationale:** Pre-a11y muted/danger failed WCAG AA on white. Handover §14 and `index.html` are updated to match CSS, not the reverse.
- **Consequences:** New UI must use tokens, never raw hex. Invoice/print templates may keep a minimal local subset for print isolation.

## ADR-P3-004 — Checkout saga is deferred until stock leaves the orders transaction

- **Status:** Accepted
- **Decision:** Do **not** introduce a multi-service checkout saga module while inventory and orders share one MySQL transaction. Current checkout remains `place_order()` atomic block + payment-session compensation (`release_reservation` on provider failure).
- **Rationale:** A premature saga that HTTP-calls inventory would either no-op-wrap the atomic path (noise) or split the transaction and break M2 / Hard Invariant 1. Dual-ledger inventory FastAPI is still experimental (ADR-P3-002).
- **When unlocked (after Catalog owns stock via sync REST):** steps `ValidateCart → CreateOrder → ReserveStock → CreatePaymentSession` with compensations `ReleaseReservations` / cancel pending payment; propagate `X-Correlation-ID` (ADR-P2-002). No broker.
- **Consequences:** Fulfillment booking HTTP strangler (ADR-P3-003 step 2) may ship independently — packing is post-Paid admin work, off the M2 path.

## ADR-P3-005 — Fulfillment booking HTTP strangler

- **Status:** Accepted
- **Decision:** Opt-in `SHIPPING_PROVIDER=http` posts booking DTOs to `services/fulfillment` (`POST /v1/shipments/book`). Django keeps `Shipment` rows and applies waybill fields on success. Default remains `jnt` / `simulated`.
- **Rationale:** Same pattern as notifications delivery: extract I/O, keep domain state in the monolith, never flip default until parity.
- **Consequences:** Courier webhook, zones, and OFD push stay in Django. Manual waybill remains the failure fallback.


## ADR-P3-006 — Containerized strangler sidecars (Compose profile `services`)

- **Status:** Accepted
- **Decision:** `notifications`, `fulfillment`, and `inventory` FastAPI processes ship as Compose services under profile `services`, built from `docker/Dockerfile.services`. Public staging Caddy (`deploy/Caddyfile`) continues to reverse-proxy **only** the Django app. Internal routes live on `deploy/Caddyfile.internal` (:9080, loopback publish) under `/internal/{notifications,fulfillment,inventory}/*`.
- **Defaults:** Django still uses in-process providers. Opt-in only via `NOTIFICATION_PROVIDER=http`, `SHIPPING_PROVIDER=http`, `INVENTORY_PROVIDER=service`.
- **Verification:** `scripts/smoke-services.sh` asserts all three `/healthz/ready` return 200 and that a booking request's `correlation_id` appears in fulfillment logs.
- **Free-tier:** one MySQL instance; inventory uses logical DB `metrodrip_inventory`. No broker/mesh/K8s required for smoke (inventory Redis listener is optional/degraded).
- **Consequences:** Oral defense can demonstrate three healthy containers without claiming production cutover. Inventory remains experimental (ADR-P3-002).

## ADR-P3-007 — Checkout saga unlock condition remains unmet

- **Status:** Accepted
- **Decision:** Catalog does **not** yet own stock via production-grade sync REST. Unlock condition for ADR-P3-004 is **not met**. Checkout stays the atomic `place_order()` + payment-session compensation path. Do not implement multi-service saga orchestration.
- **Evidence:** `INVENTORY_PROVIDER` default is `local`; service adapter still dual-ledger / incomplete commit-release (ADR-P3-002). M2 gate depends on InnoDB `select_for_update` inside the same Django transaction as the order row.
- **Task list to unlock (future):**
  1. Single stock ledger owned by Catalog service (or shared schema with exclusive writer).
  2. Sync REST: reserve / commit / release with clear error codes; drop Redis as commit path.
  3. Django checkout calls reserve over HTTP *after* order row insert strategy is redesigned so compensation works without dual-write races.
  4. Re-point M2 gate at Catalog reserve endpoint; both web and mobile checkout must pass.
  5. Only then introduce saga module with ValidateCart → CreateOrder → ReserveStock → CreatePaymentSession.

## ADR-C-005 — Curated collection categories

- **Status:** Accepted
- **Decision:** The catalog supports thematic collections ("New Arrivals", "Best-Sellers", "On-Sale", "Pre-Order") as top-level root categories. These categories do not require gendered subcategories (e.g. "Men", "Women").
- **Rationale:** Marketing and curation require flexible grouping that breaks the strict structural taxonomy (Tops/Bottoms). Treating collections as root categories reuses the existing category navigation and filtering logic without requiring a separate "Collections" data model.
- **Consequences:** Product.category can point directly to a root collection category. Mass seeding scripts (seed_collections.py) apply static discount math (e.g., 30% off for "On-Sale") at generation time to preserve the no-client-math invariant.

## ADR-P3-008 — Deployed provider selection is an allowlist, not a hardcoded pin

- **Status:** Accepted (amends ADR-P3-003 steps 1 and 2)
- **Decision:** `config/settings/prod.py` validates `SHIPPING_PROVIDER`, `NOTIFICATION_PROVIDER`, and `INVENTORY_PROVIDER` against an allowlist and **returns the operator's value**. `PAYMENT_PROVIDER` stays an unconditional `paymongo` assignment.
- **Evidence of the defect:** the previous code read each variable only to reject one development-only value, then assigned a hardcoded good one (`SHIPPING_PROVIDER = "jnt"`, `NOTIFICATION_PROVIDER = "email_sms"`). `staging.py` does `from .prod import *`, so **`=http` was structurally unreachable in every deployed environment**. Steps 1 and 2 were described as "done as opt-in" while no deployed environment could take the opt-in.
- **Rationale:** the strangler's whole control surface is the provider key. A settings module that discards it converts an opt-in into dead code. Rejecting an unrecognised value at import also moves a typo's failure from a late registry lookup to boot.
- **Consequences:**
  - `INVENTORY_PROVIDER`'s allowlist is `{"local"}` today. **Widening it to `{"local", "service"}` is the step-3 cutover** — a one-line, reviewable, git-blameable change rather than an ops decision.
  - `=http` additionally requires a non-empty service token (see ADR-P3-009).
  - `PAYMENT_PROVIDER`'s asymmetry is deliberate and commented: Hard Invariant 3 leaves exactly one legal deployed value, so there is no operator choice to preserve.
  - Pinned by 12 cases in `tests/test_staging_settings.py`; the two `allow_http_strangler_opt_in` cases fail against the previous implementation.

## ADR-P3-009 — Sidecars and their adapters both fail closed

- **Status:** Accepted
- **Decision:** `services/_shared/security.py` gates every sidecar route. An unset service token means **refuse every request (503) and report not ready**, never "allow everything". Django's side refuses to send a request it cannot authenticate. Comparison uses `hmac.compare_digest`.
- **Evidence of the defect:** two independent fail-open defaults composed into no authentication at all — the Django adapters omitted the `Authorization` header when their token was empty, and each service skipped its check when its own token was empty. `services/inventory/api.py` had no check of any kind on `POST /reservations`, published on `0.0.0.0:8001`.
- **Readiness:** `/healthz/ready` returns 503 when unconfigured. The inventory probe also returns 503 when its database is unreachable; the previous version returned 200 with `db: degraded` and offered an `INVENTORY_READY_SKIP_DB` flag that skipped the probe entirely — **a readiness probe that cannot report "not ready" is not a probe**, and it made the Compose healthcheck and `scripts/smoke-services.sh` structurally incapable of failing.
- **Why not raise at import:** a crash-looping container hides its reason behind a restart counter; an unready one answering a documented 503 states it plainly and stays inspectable. The safety property is identical.
- **Consequences:** host port publishing is loopback-only (`127.0.0.1:PORT:PORT`). Local Compose supplies known development tokens; `prod.py` refuses to boot an `http` provider without a real one.

## ADR-P3-010 — One egress point, and a three-way failure taxonomy

- **Status:** Accepted
- **Decision:** Every provider adapter calls `apps/core/http.py::call()` instead of `requests` directly. Connect and read timeouts are separate, and failures are raised as one of three distinct types.
- **The taxonomy, which is the actual point:**
  - `ServiceRejected` — 4xx. Understood and declined. Nothing changed. Never retry.
  - `ServiceUnavailable` — connect refused or connect timeout. Provably pre-send. Nothing changed.
  - `ServiceUncertain` — read timeout, or 5xx after the body was sent. **May or may not have been applied.**
- **Rationale:** `requests` collapses all three into `RequestException`, which is why the adapters could only ever do `except Exception: return False`. That is survivable for notification delivery, where a dropped message is enhancement-tier. It is *not* survivable for stock reservation, where "maybe it was applied" is precisely the difference between under-selling and over-selling. Splitting connect from read timeout is what makes the distinction knowable at all. This lands in Phase A so the distinction exists **before** stock moves.
- **Consequences:**
  - `attempts > 1` without an idempotency key raises `ValueError` — a call that can silently double-apply on a network blip is not expressible.
  - The circuit breaker is process-local, not cache-backed: `config/settings/test.py` uses `DummyCache` and no deployed environment runs a shared cache, so a cache-backed breaker would silently never trip in exactly the environments it exists for.
  - Booking and delivery both stay `attempts=1` (neither is idempotent yet) and both still degrade to `False`, preserving the manual-waybill and enhancement-tier fallbacks.

## ADR-P3-011 — Contracts are shared code; seam tests are round trips

- **Status:** Accepted (supersedes the split assertions in the previous seam tests)
- **Decision:** `contracts/` holds one pydantic model per message. The FastAPI services declare them as body and `response_model` types; the Django adapters validate against the same models. Seam tests in `tests/contract/` drive a **real** Django provider against a **real** FastAPI app in-process, by redirecting the single egress point from ADR-P3-010.
- **Evidence of the defect:** the previous "contract tests" asserted the client's outgoing shape against a mocked `requests.post` and the server's shape against a `TestClient`, with nothing connecting them. Renaming a response field on the server left the client test green while every real call returned `False`. They proved each side self-consistent and said nothing about whether the two agreed.
- **Consequences:** a field rename is now impossible to do on one side only — both import the same model. Round trips need no subprocess, no port, and no second database. 10 cases cover success, auth rejection in both directions, unconfigured-token refusal on each side, and quiet degradation.

## ADR-P3-012 — The inventory sidecar is no longer started against Django's test database

- **Status:** Accepted (corrects the evidence base for ADR-P3-002 and ADR-P3-007)
- **Decision:** `tests/conftest.py` no longer starts a session-scoped uvicorn subprocess, and CI no longer starts one either.
- **Evidence of the defect:** both set `MYSQL_DATABASE_INVENTORY=test_metrodrip` — pytest-django's *own* test database for `metrodrip`. The FastAPI service was reading and writing `inventory_stockrecord` / `inventory_reservation` **inside Django's schema**, the same physical rows the ORM owns. Under Compose the same service points at `metrodrip_inventory`, a genuinely separate ledger, so the two modes had opposite semantics. It is also the only reason the dual-write in `apps/inventory/providers/service.py` appeared to work: the Django `UPDATE` found the row SQLAlchemy had just inserted because it was literally the same table.
- **Second defect:** nothing consumed it. `INVENTORY_PROVIDER` defaults to `local` and no test overrides it, so the subprocess answered zero requests while costing one process per run.
- **Consequences:** **any prior green result for the `service` provider should be treated as unverified.** Phase B must introduce a database that is *not* Django's test database, created and torn down explicitly, before the parity claim in ADR-P3-005 can be made.

## ADR-P3-013 — Step 4 (schema split) is designed, sequenced, and deliberately not executed

- **Status:** Accepted
- **Decision:** Do **not** split the five logical databases (`db_identity`, `db_catalog`, `db_orders`, `db_fulfillment`, `db_content`) or drop the 11 cross-app foreign keys. Phase A (seam hardening) and Phase B (stock ownership) proceed; step 4 stops here by choice, not by omission.
- **Rationale:**
  - **It buys nothing operationally at this scale.** One MySQL instance, one host, one developer. Five logical databases on one instance give no isolation, no independent scaling, no independent failure domain, and no independent deploy. The entire cost is paid for the *appearance* of separation.
  - **It is the only irreversible step.** Every other change in this plan reverts with an environment variable or `git revert`. After the data move, rollback is restore-from-dump.
  - **It permanently downgrades audit integrity.** `StockMovement.ref_order` and `Review.order` are `PROTECT` precisely because audit evidence must not be deletable. Across a service boundary those become application-level guards plus a detector — a real loss of evidentiary strength, traded for nothing the business needs.
  - **The SOA framing does not require it.** Three running services, a versioned sync-REST contract, consumer-driven contract tests, a fail-closed auth boundary, a three-way remote-failure taxonomy, correlation IDs end to end, and a documented architecture status already demonstrate the pattern. "We kept one MySQL instance with foreign-key integrity because a logical split on one host buys nothing at our scale, and here is the ADR" is a **stronger** position than a half-finished split — the same argument ADR-P3-003 already makes about not overclaiming.
- **If it is later required:** ship the reversible subset only — `db_constraint=False`, application-level guards, denormalised read models for catalog's `review_avg` / `review_count` / `total_sold`, and the state-only field swap. That delivers the whole "services own their data" story on one database and stops short of the one-way door.
- **Consequences:** ADR-P3-007's unlock list remains the gate for step 5. The checkout saga stays unbuilt; its **outbox**, however, is a prerequisite for flipping step 3's default and is built during Phase B, not after it.

## ADR-P3-014 — Orders holds a receipt (`StockHold`); the ledger is asked by `checkout_id`

- **Status:** Accepted (Phase B, step 3 in progress)
- **Decision:** Orders records a `StockHold` row per checkout attempt, keyed by a `checkout_id` it mints before any write. The paid path commits stock with `commit_holds(checkout_id=…)` and compensates with `release_holds(checkout_id=…)`. Nothing on the Orders side reads `inventory_reservation`.
- **The defect this closes:** both payment providers consumed stock by iterating `order.reservations.filter(status="active")` — a reverse foreign key into the ledger's table. That resolves only while Orders and the ledger share one schema. Against a separate ledger it returns **empty**, the commit loop does nothing, and the shortfall pass re-reserves and re-commits every line. The payment succeeds, `qty_on_hand` never moves, and **no `StockMovement` row is written** — Hard Invariant 4 failing silently on the money path, and untested.
- **Why `checkout_id` and not the order id:** the identity has to exist *before* the order row, so stock can be reserved first and compensation can name something the caller supplied. Passing an order id is what forced the old adapter to write back into Django's `Reservation` table after calling the service (ADR-P3-012).
- **Consequences:**
  - `commit_holds` returns `{variant_id: qty}` so the shortfall reconciliation works without reading rows it does not own.
  - Both providers now share `apps/payments/holds.py`; the duplicated loop is gone.
  - Pinned behaviourally by `tests/test_stock_holds.py`, and structurally by an AST check that no payments module accesses `.reservations` — behaviour alone cannot catch this while both halves share a database.
  - `StockHoldState.UNKNOWN` exists for commits that returned `ServiceUncertain`. Nothing resolves those yet; that is the reconciliation job in B6.

## ADR-P3-015 — Batch stock reads

- **Status:** Accepted
- **Decision:** `get_stock_records(variant_ids)` is the read primitive; `POST /v1/stock/batch` serves it. Every page that reads stock for a set of variants uses it.
- **Rationale:** the product page read one variant at a time — about 36 sequential HTTP calls per page on the seeded catalog under `INVENTORY_PROVIDER=service`, each with its own timeout budget, and the availability endpoint accepted 50 ids the same way. This alone made the service provider unshippable independent of correctness.
- **Consequences:** unknown ids read as zero availability rather than raising, matching the in-process provider — a never-stocked SKU and a sold-out SKU are the same answer to a shopper. Pinned by a call-count assertion, not by inspection.

## ADR-P3-016 — Idempotency by insert-then-mutate in one transaction

- **Status:** Accepted
- **Decision:** Every mutating ledger route claims an `IdempotencyRecord` row with `status_code = 0` and applies its stock mutation **in the same transaction**, then records the real status and body before commit. Missing `Idempotency-Key` on a mutating route is a 400.
- **Rationale:** under sync REST a read timeout is indistinguishable from success — the request was sent, so the mutation may or may not have landed (`ServiceUncertain`). Without a replay guard the caller's only safe move is to give up and compensate, turning every network blip into a lost checkout. Because the key row and the mutation commit together, "key present with a terminal status" is true exactly when the mutation was applied; a crash between them rolls back both, so a retry re-runs cleanly rather than finding a claim with nothing behind it. **The ordering is the guarantee — the table alone would not be one.**
- **Three distinct collision outcomes:** differing request fingerprint → `422 idempotency_key_reuse` (a client bug, never a retry; replaying the first response would be a lie); `status_code == 0` → `409 in_progress` with `Retry-After` (answering now would either double-apply or guess); otherwise replay the stored status and body with `Idempotency-Replayed: true`.
- **Consequences:** keys are namespaced by route (`sha256("{route}:{key}")`) so one `checkout_id` can guard reserve *and* commit without the commit replaying the reserve's response. Django owns the DDL; the service writes the rows (shared schema, exclusive writer).

## ADR-P3-017 — What Phase B has and has not proven

- **Status:** Accepted
- **Decision:** Record the boundary of the evidence, so no later reader mistakes "implemented" for "verified".
**Superseded in large part by ADR-P3-019/020/021 — kept for the record of what was true when written.** Current state:

- **Verified against a live ledger** (ADR-P3-019): reserve, commit, release, batch reads, and idempotency, via a harness that binds the service to Django's test schema deliberately rather than accidentally.
- **Parity proven, not asserted** (ADR-P3-021): 30 assertions across 15 scenarios and both providers, including adjustments, the TTL sweep, and low-stock SKU rendering.
- **Concurrency proven** (ADR-P3-020): G3 web and G4 mobile checkout gates, G5 concurrent idempotency, and G3 re-run with stock reserved **over HTTP** — 20 buyers, 10 units, exactly 10 sales with the lock behind a network call. That last result is the load-bearing one: it shows the row lock never needed to share the order's transaction, only to be atomic per reserve.
- ~~**Still not built:** the reserve-before-order restructure (ADR-P3-004's amended step order). Checkout remains order-then-reserve inside one atomic block.~~ **Superseded by ADR-P3-022** (2026-08-24): the restructure landed. `place_order` reserves before the order row; see `apps/orders/checkout.py`.
- ~~**`INVENTORY_PROVIDER` stays pinned to `{local}`** until that restructure lands.~~ **Superseded by ADR-P3-025**: the allowlist is `{local, service}` and the *default* stays `local`, which is a deliberate posture rather than a blocked one.

> **Why these two lines are struck through rather than deleted** (2026-08-24): they were read as current by an external completion plan, which then listed the saga as the project's top unbuilt P1 item — work that had in fact shipped months earlier. A superseded status line in an accepted ADR is not inert; it is actively misleading, because "Accepted" invites the reader to trust every line under it. The record of what was true is preserved above; the correction travels with it.

## ADR-P3-018 — Transactional outbox instead of a broker

- **Status:** Accepted
- **Decision:** `apps/orders/outbox.py` holds durable intent. `consume_order_holds` writes a `stock.commit` message **inside the payment transaction**, attempts the commit synchronously, and retires the message on success. A scheduler job drains anything left with `SELECT ... FOR UPDATE SKIP LOCKED`, exponential backoff with jitter, and a dead-letter state after 8 attempts.
- **Rationale:** while the ledger is in-process, the payment flip and the stock commit share a transaction and cannot disagree. Once the ledger is remote they are two systems: a commit that fails *after* the payment row commits means money taken and stock never decremented. Writing the instruction in the same transaction as the payment restores atomicity of **intent** — either both commit or neither does — and at-least-once delivery against the ledger's idempotency keys (ADR-P3-016) is exactly-once in effect.
- **Why no broker is needed:** MySQL 8's `FOR UPDATE SKIP LOCKED` lets concurrent drainers claim disjoint batches without blocking each other. That one feature is what makes a database-backed queue viable under ADR-P3-003's "no broker" constraint, and it also relaxes ADR-A-014's single-scheduler rule from a *correctness* requirement to an efficiency one — the sweep and the low-stock scan still need exactly one process, the drainer does not.
- **Sequencing correction to the Phase B plan:** the outbox is a **prerequisite** for flipping `INVENTORY_PROVIDER`, not a follow-on to it. It is built now, before cutover.
- **Consequences:**
  - Claiming and delivering are separate transactions. Holding a database transaction open across an HTTP call would put network latency inside a row lock, which is how a slow sidecar becomes a stalled database.
  - `attempts` is incremented while the claim lock is held, so a message that reliably kills its worker still counts a try instead of retrying forever.
  - The dead-letter queue is an `OutboxMessage` changelist filtered to `dead` — at this budget that is the right amount of infrastructure, and a better demo than a broker console.
  - Background work runs inside `bind_correlation_id`, so ADR-P2-002's "one checkout is greppable end to end" survives the move to asynchronous delivery.

## ADR-P3-019 — The live-ledger harness, and parity as evidence

- **Status:** Accepted (closes the gate ADR-P3-017 named)
- **Decision:** `tests/contract/conftest.py` provides a `live_ledger` fixture that rebinds the service's SQLAlchemy engine to Django's active test schema, and a `service_provider` fixture that additionally selects the provider, supplies a token, and redirects `apps/core/http.py` at the in-process FastAPI app. `tests/contract/test_provider_parity.py` runs every scenario against **both** providers.
- **Why this is not a return to the old arrangement:** ADR-P3-012 removed a session-scoped fixture that set `MYSQL_DATABASE_INVENTORY=test_metrodrip` — Django's own test database — with *no test using it*. Pointing the service at Django's schema is nonetheless correct under ADR-P3-013's shared-schema/exclusive-writer decision. What was wrong was that it was accidental, unexercised, and it masked the dual-write bug. It is now deliberate, documented, and exercised by 31 assertions.
- **Two details the harness depends on, both non-obvious:**
  - **`transaction=True` on every test.** The ledger reads on its own connection and cannot see an uncommitted Django transaction. Without a real COMMIT every read returns empty and the tests would assert the opposite of what they claim — the same failure mode as ADR-P3-012, one level up.
  - **`NullPool` for the test binding.** Starlette's `TestClient` runs each request on a fresh event loop, while a pooled aiomysql connection stays bound to the loop that opened it. The second request in a test would reuse a connection whose transport belongs to a closed loop and fail with `Event loop is closed`, which names nothing useful.
- **A real bug it caught immediately:** the insufficient-stock path returned **500 instead of 409**. `await db.rollback()` expires every loaded instance, so building the error message afterwards from `record.available` triggered lazy IO outside the async greenlet (`MissingGreenlet`). Every oversell rejection would have been a server error in production. Values are now read before the rollback, on all three rollback paths.
- **Consequence:** ADR-P3-005's "never flip a default until parity" now has evidence behind it for the reserve/commit/release/read surface. The remaining gates before a cutover decision are the concurrency ones (G3–G6) through the real checkout endpoints.

## ADR-P3-020 — Concurrency gates G3–G5, and the idempotency hole they found

- **Status:** Accepted (satisfies ADR-P3-007 unlock item 4)
- **Decision:** `tests/test_checkout_concurrency.py` races 20 buyers for 10 units through the **real web checkout endpoint** (G3) and the **real mobile API endpoint** (G4), and races 5 simultaneous retries sharing one `checkout_id` (G5).
- **Why these were needed:** the existing M2 gates race `reserve_stock` in isolation. That proves the row lock and says nothing about the surface customers use — order numbering, the deadlock retry, payment-session creation, and hold bookkeeping all sit between an HTTP request and that lock. ADR-P3-007 asked for exactly this ("both web and mobile checkout must pass") and neither existed.
- **G5 found a real bug on its first run.** `LocalInventoryProvider.reserve_lines` guarded replays with a plain `SELECT` on `checkout_id`. That is not a guard: five concurrent retries of one id each saw "nothing reserved yet" and all five proceeded, holding **9 units instead of 3**. Serial idempotency passed; concurrent idempotency did not, and only a concurrent test could tell them apart.
- **Fix:** the guard is now a *write*. `reserve_lines` claims a uniquely-keyed `IdempotencyRecord` inside the transaction, so the primary key arbitrates: the loser blocks until the winner commits and then takes the replay path via a locking read. This is the same mechanism the service already used (ADR-P3-016) — the local path needed it for the same reason, because a client can have several retries in flight at once.
- **Lesson worth keeping:** "in-process callers do not retry over a network" was the comment justifying the weaker guard. It was wrong. Concurrency, not remoteness, is what breaks a read-then-write check.

## ADR-P3-021 — The service provider now implements the whole contract

- **Status:** Accepted
- **Decision:** `ServiceInventoryProvider` implements `adjust_stock`, `release_expired_reservations`, and `scan_low_stock` against the ledger's endpoints. All three were stubs.
- **What the stubs actually meant**, which is worse than "incomplete":
  - `adjust_stock` **raised**, so a merchant could not restock at all.
  - `release_expired_reservations` **returned 0** behind a comment claiming the service ran its own sweep. It did not — nothing scheduled one — so abandoned holds would never expire and their stock would be silently unsellable forever.
  - `scan_low_stock` **returned `[]`**, so low-stock alerting stopped without a single error.
  These are exactly the gaps ADR-P3-002 reverted over, and every one of them fails silently. That is why parity has to be tested rather than reasoned about.
- **Shape parity, not just behaviour parity.** `send_low_stock_alert` renders `record.variant.sku`. A naive implementation would have returned integers and quietly changed every alert email from SKUs to numbers — a regression no test would have caught, because no test ever ran the alert under this provider. The ledger therefore joins `catalog_productvariant` and returns the SKU in the payload; the join stays local because catalog and inventory share a schema (ADR-P3-003), which is a concrete dividend of grouping them.
- **A routing bug the parity test caught:** `/v1/stock/{variant_id}` was declared before `/v1/stock/low`, so FastAPI matched the parameterised path first and rejected `"low"` as an invalid integer. The literal route is now declared first.
- **Cutover criteria, and where they stand.** Met: full contract implemented; 30 parity assertions across both providers; 9 live round trips; idempotency proven serially *and* concurrently; G3/G4 checkout gates green. ~~**Not yet met:** G3/G4 have only been run against `local`, and the reserve-before-order restructure is not built.~~

- **Status correction (2026-08-24).** Both "not yet met" items are stale:
  - The **reserve-before-order restructure shipped** in ADR-P3-022.
  - **G3 has since been run against a remote ledger** — `tests/contract/test_no_oversell_over_network.py::test_m2_gate_through_web_checkout_with_a_remote_ledger` races 20 buyers for 10 units through the real web checkout against a real uvicorn process.
  - **What is still genuinely open is narrower than the original line:** the *mobile* gate (G4) has no over-the-network equivalent — the remote-ledger coverage is web-checkout only. That is the accurate remaining gap, and it is smaller than "G3/G4 have only been run against `local`" implied.

## ADR-P3-022 — Reserve before the order row (amends ADR-P3-004's step order)

- **Status:** Accepted (amends ADR-P3-004)
- **Decision:** `place_order` now runs `ValidateCart → PriceCart → ReserveStock → CreateOrder → CreatePaymentSession`. ADR-P3-004 specified `CreateOrder → ReserveStock`; that ordering is the more dangerous one and is superseded.
- **Why order-then-reserve was wrong**, and none of these are hypothetical:
  - It **burned an order number on every sold-out attempt**. `next_order_no()` is a sequence, and the locked public format `MD-YYYY-NNNNN` allows only 99,999 per year.
  - It **committed a `pending` order before its stock was secured** — visible in the merchant console and at `/order/<token>/`, and briefly payable. A webhook arriving in that window would pay an order holding nothing.
  - It could not be cleaned up. Deleting such an order is blocked by the `PROTECT` edges from `StockMovement.ref_order` and `Review.order`, which exist precisely to stop audit rows being erased. Cancelling instead leaves a phantom cancelled order per failure.
- **Why it is safe now:** reserve is all-or-nothing, so a rejected cart writes *nothing anywhere* and there is nothing to compensate. Every later failure branch calls `_release_quietly(checkout_id)`, which is a documented no-op when nothing was reserved — so compensation never has to establish what actually landed, which is the property that makes it correct against an uncertain remote outcome.
- **The reserve moves outside the deadlock retry.** The retry now replays pure-Django work only: cheaper, and it removes the interaction between the stock lock and `OrderNumberSequence` entirely, since the two are no longer taken in the same transaction.
- **Payment-session failure now cancels the order.** It previously stayed `pending` forever, holding a place in the merchant console and keeping the late-webhook window open. Compensation failure is logged and never replaces the original error; the TTL sweep is the backstop, so the worst case stays bounded at `RESERVATION_TTL_MINUTES` of under-selling and can never become an oversell.
- **Consequence for the data model:** an ACTIVE reservation is no longer linked to an order, because it belongs to a *checkout attempt* that may never produce one. `Reservation.order` is populated at commit, when the hold stops being a hold and becomes a sale. The `StockHold` receipt carries the link in the meantime, and `mark_as_cancelled` in the merchant console releases by `checkout_id` rather than reading the ledger's rows.

## ADR-P3-024 — The Redis commit path is deleted, not deprecated

- **Status:** Accepted (closes ADR-P3-007 unlock item 2)
- **Decision:** `services/inventory/events.py` and the pub/sub listener in the lifespan are removed, along with the `REDIS_URL` / `INVENTORY_DISABLE_REDIS` wiring and the ledger's Redis dependency in Compose.
- **What it actually was.** The listener consumed `OrderConfirmed` from `inventory_events` and, on receipt, committed reservations and decremented `qty_on_hand` directly — **with no authentication and no idempotency guard**. Anything able to reach Redis could move stock. Once the Django provider moved to sync REST nothing published to that channel any more, so what remained was a dormant second writer, which is precisely what the exclusive-writer decision in ADR-P3-013 forbids.
- **Why deleting beats deprecating:** a disabled-by-default second write path is still a write path. The failure it invites is silent (stock moves with no audit trail tying it to a request), and the flag protecting it was a plain environment variable.
- **Consequence:** all stock mutation now enters through one authenticated, idempotent, versioned surface. ADR-P3-007 item 2 is satisfied.

## ADR-P3-025 — `INVENTORY_PROVIDER=service` is permitted; the default stays `local`

- **Status:** Accepted
- **Decision:** `prod.py` widens the inventory allowlist to `{local, service}` and requires `INVENTORY_SERVICE_TOKEN` whenever the remote provider is selected. **`default="local"` is unchanged.**
- **The distinction matters.** ADR-P3-005's rule is *never flip the default until parity*. Widening an allowlist does not flip a default — it makes the seam openable by an operator who sets the variable deliberately, which is the entire point of the strangler's control surface. Nothing about a deployed environment changes until someone chooses to change it.
- **Evidence that unlocked it:**
  - The full contract is implemented, including the three operations that were silently stubbed (ADR-P3-021).
  - 30 parity assertions run every scenario against **both** providers.
  - **No-oversell holds across a real network.** 20 concurrent buyers, 10 units, a real uvicorn ledger on real sockets: exactly 10 sales, `available == 0`. The M2 gate passes end to end through the web checkout with the ledger remote, and one checkout_id retried concurrently over HTTP still holds once. A negative control pointing at a dead port proves the suite can fail.
  - The sidecars are now **defined and deployable in staging** (they were absent entirely), behind the `services` Compose profile, internal-network only, fail-closed without their tokens. Deployable rather than *running*: the default staging stack is unchanged, which matches the provider defaults and keeps the single-host cost envelope.
- **Residual risk, stated rather than buried.** `consume_order_holds` runs inside the payment transaction, so under `service` a stock commit is an HTTP call made while holding a lock on the `Payment` row — up to the policy's timeout budget. That is a latency and throughput hazard, not a correctness one (the outbox makes the intent durable and the ledger de-duplicates), but it is the next thing to address before anyone selects `service` in production. Staging is where that should be measured; nothing has ever run this provider in a deployed environment.
- **Rollback remains an environment variable**, because the schema is shared and Django still owns the DDL (ADR-P3-013). That property is what made permitting this defensible at all.

## ADR-P3-026 — Opt-in sidecars belong behind a Compose profile in staging too

- **Status:** Accepted (corrects ADR-P3-025's deployment claim)
- **Decision:** The three staging sidecars sit behind the `services` profile, exactly as they already did in `docker-compose.yml` under ADR-P3-006. A default `docker compose up` brings up db + app + scheduler + caddy and nothing else.
- **What went wrong first.** Adding them as always-on services broke the `deployment-contracts` CI job with `No such image: metrodrip-services:staging`. That job builds only the app image and runs `up --no-build`, so any service outside a profile must already have its image built. The failure was immediate and obvious — but the underlying mistake was not the missing build step, it was making three containers run in every staging deployment when nothing calls them.
- **Why the profile is the right fix rather than "also build the image":** the deployment posture should match the provider posture. Every seam defaults to in-process, so the default deployment should have no sidecars in it. Running three idle containers on a single host also spends the NFR-5 cost envelope for nothing.
- **Guard added:** CI now asserts the default staging stack is exactly `app caddy db scheduler`, with an error message naming the `--no-build` constraint. It fails on the exact regression that caused this, verified by running it against both configurations. The profiled config is separately schema-validated so the sidecar definitions cannot rot while unused.
- **To open a seam in staging:** `docker compose --profile services up -d --build`, then set the matching provider key.

## ADR-P5-002 — Presentation-layer audit: what the brief got right, and what it did not

- **Status:** Accepted
- **Context:** A responsive/accessibility brief specified six fixes with file:line evidence. Each claim was verified against the code before any of it was implemented. Three were accurate, three were not, and the two most useful findings were not in the brief at all. Recorded because a later reader will otherwise re-derive the same corrections.

### Claims that held

- **Mobile fixed widths (P1):** all five line references were exact — `SplashScreen.tsx:80` (`width: 320`), `:110` (`300`), `HomeScreen.tsx:190` (`300`), `NotificationsScreen.tsx:135` (`250`), `ProductDetailScreen.tsx:234` (`250`). At 320pt these equal or exceed the viewport once screen padding is applied. Replaced with `alignSelf: 'stretch'`, `maxWidth`, and `flex: 1`; the product price additionally got `flexShrink: 0`, because it is the one server-computed figure on that screen and truncating it would misreport it.
- **No 320px or 1440px tier (P1):** correct. Both added.
- **`prefers-reduced-motion` under-covered (P2):** correct, and worse than stated — it covered **two selectors** in `storefront.css` and did not exist in `console.css` at all, while both files animate. Replaced with a blanket rule in each.

### Claims that did not hold

- **P0 root cause was misdiagnosed.** The brief attributed clipped console tables to `overflow: hidden` on `#changelist-form` and prescribed changing it to `overflow-x: auto`. **Measured at 320px, the changelist was already fine:** Django's own `.results` div wraps `#result_list` with `overflow-x: auto` (254px viewport around an 840px table) and the last column was reachable. Applying the prescribed change would have nested a second scroller inside Django's — two scrollbars for one table.
  **The real defect was `.dense-table` on the dashboards.** A 623px table sat in a 256px `.console-panel` with `overflow: visible`, so the overflow escaped to `#main`, whose `overflow-y: auto` computes `overflow-x` to `auto` — reading column 7 dragged the sidebar and topbar off screen. Fixed with a `.table-scroll` wrapper plus **`min-width: 0` on `.console-panel`**; without that one declaration the grid item refuses to shrink and nothing scrolls. Measured `#main` scrollWidth **679px → 320px**.
- **The five named grids do not overflow.** `.pdp-layout` does not exist in the codebase; the real selector is `.product-detail` and it is `1fr 1fr`, not `1fr 380px` (that is `.cart-layout`). All five collapse at ≤768px or are mobile-first. None needed changing.
- **P3 was already done.** `deploy/Caddyfile.internal` has routed `notifications`, `fulfillment` and `inventory` on `:9080` since ADR-P3-006, and the public `deploy/Caddyfile` proxies only `app:8000`. No work required; claiming otherwise would have meant re-adding existing routes.

### Not in the brief, found by verification

- **`--color-primary` was undefined** (`storefront.css`, loading spinner). The declaration was invalid, `border-top-color` fell back to `currentColor`, and the spinner had no visible rotating segment — an invisible loading indicator. Now `--color-volt`.
- **The select chevron was invisible in dark mode.** It is a data URI hardcoding `%2375756E` — the pre-a11y muted this file's own token comment says was removed — and it never inverted, leaving a near-black arrow on `#1A1A1A`. A regex hex audit misses it because the `#` is URL-encoded. Now a `--select-chevron` token overridden in all three theme blocks.

### Deviation from the brief's design-system table

The brief's 11-token camelCase palette (`onVolt`, `accentText`, `mutedOnDark`) matches **`mobile/src/theme/theme.ts` exactly** but matches neither stylesheet: `console.css` defined 13 `--c-*` tokens and ~~was dark-only with no theme mechanism~~ now has an explicit light/dark semantic palette under ADR-P5-005; `storefront.css` defines 24 `--color-*` tokens. Unifying the prefixes was **not** attempted — it is a rename across two large stylesheets with no behavioural benefit, and the brief scoped that audit to presentation defects. Every change in that audit resolved through tokens that already existed in the file being edited; it introduced no new colour values.

### Verification

`scripts/check-responsive.mjs` drives headless Chrome over the DevTools Protocol using Node 22's built-in `fetch` and `WebSocket` — no new dependency, consistent with the hand-rolled-frontend constraint. It measures two things per route per width: page-level horizontal scroll, and **tables that overflow with no scrollable ancestor**. The second check exists because the first passes *trivially* when content is clipped: `overflow: hidden` means the page cannot scroll precisely because the data has been cut off. Measuring only `scrollWidth` would have scored the P0 bug as a pass.

## ADR-P5-003 — P2 completion: states, targets, Dynamic Type, htmx

- **Status:** Accepted
- **Context:** The previous pass shipped P0/P1 and left P2 explicitly unfinished. Two audits found the remaining work — and two regressions introduced by that same pass.

### Regressions fixed, and the guard added

1. **Dead selectors in the 1440px tier.** It targeted `.contact-form`, `.developers-content` and `.empty-state__body`; none exist in the repo (the real element is `.empty-state__text`). The CSS parsed and the page rendered, so nothing failed — the rules were simply inert. `.prose` did exist but was neutralised by an inline `max-width: 65ch`.
2. **The blanket reduced-motion rule silenced the loading spinner.** `animation-duration: 0.01ms !important` on `*` stopped `@keyframes spin`, leaving a static ring signalling nothing. **Reduced motion means less motion, not no feedback** — progress indicators are now exempt at a calmer 1.5s.
3. **The console 320px tier targeted `.content`** while Django renders `id="content"`, so the padding never applied.

`scripts/check-css-selectors.mjs` now fails on any class targeted **inside an `@media` block** that no markup can produce. Scope is deliberately narrow: it must understand template-composed names (`kpi-card--{{ variant }}`) and Alpine `:class` bindings, and must not demand deletion of design-system variants authored ahead of first use. It caught regression 3 on its first run.

### The one genuine WCAG failure

`console.css` set the input focus ring to `rgba(212, 255, 63, 0.3)` — volt at 30% alpha, compositing to roughly `#3a4426` on the dark surface, nowhere near the 3:1 SC 1.4.11/2.4.11 require. Being more specific than the global `:focus-visible`, it **suppressed** the compliant indicator, leaving a border-colour change as the only cue. It was first replaced with full-opacity volt and is now a semantic dual light/dark ring under ADR-P5-005.

### Measurement beat estimation, repeatedly

Touch targets are now measured from rendered boxes in `check-responsive.mjs` and gate the run. The stylesheet-derived estimates were wrong in both directions: `.btn` was estimated at 50px and **measured 43**; `.navbar__toggle` passed on height and failed on width; Django's changelist search crushed its input to **26px** at 320px — three characters of a SKU search.

**On the bar itself:** 44×44 is SC 2.5.5 (**AAA**). WCAG 2.2 **AA** is SC 2.5.8 at 24×24. The brief asked for 44, so 44 is enforced — but the SC's own exceptions are honoured: inline links in text, UA-sized checkboxes, and skip links that are off-screen until focused.

### htmx: wired, not removed

The library shipped on every page and was used by nothing, while the server half (`views.py` answering `HX-Request`) was built and tested. Two details had to be right: **`hx-swap="outerHTML"`**, because the fragment emits its own `#product-results` wrapper and `innerHTML` would nest a duplicate per swap; and the **indicator lives outside the swapped region**, because one placed inside is destroyed by the swap it reports on. `hx-boost` is scoped to the filter `<aside>` and pagination `<nav>` so it can never catch a product-card link, which must navigate.

Verified in a real browser rather than by unit test alone: a filter click swaps without navigating, pushes `?category=hoodies`, leaves exactly one wrapper, and takes the grid from 6 cards to 2.

An existing test then caught a real bug in the change: **Django's `{# #}` is single-line only**, so multi-line comments render verbatim to the browser. Converted to `{% comment %}`.

### Dynamic Type — containers grow, no cap

React Native scales both `fontSize` and `lineHeight` through the native text renderer. Line-height
presets therefore store an unscaled ratio and rely on the platform to scale both values exactly once;
manually multiplying by `PixelRatio.getFontScale()` would double-scale only the line box. Twelve
interactive rows moved from `height` to `minHeight`. **No global `maxFontSizeMultiplier`** — the OS
setting is honoured in full; the prop remains forwardable per call site for a box that genuinely
cannot grow.

### Behavioural bugs fixed behind the presentation gaps

- **`CheckoutScreen` zone fetch had no `.catch`** — on failure `zone` stayed null, `disabled={!zone}` greyed out Pay permanently, and nothing explained why. A dead-end checkout recoverable only by force-quitting.
- **Shop / Wishlist / Notifications rendered their *empty* state on error**, telling a shopper their wishlist was empty when the request had failed.
- **Wishlist `remove()` dropped the row even when the server call failed**; now rolls back.

### Not done, stated plainly

**A complete 200% Dynamic Type pass across all twelve screens is not recorded.** The implementation
now avoids double scaling, but the full Android manual acceptance run remains required before making
a no-clipping claim.

Pre-existing dead CSS (`.account-grid`, `.announce-bar`) is recorded in the guard's allowlist rather than deleted — removing another author's unapplied layout is a separate call.

#### Amendment — the "no simulator" premise was wrong

**Historical correction:** the earlier text conflated an implementation correction with executed
200% verification. A legacy Android AVD and matching legacy client did exist in the environment; it
had not been looked for. That toolchain has since been superseded by the Expo 57 development-client/API
36 CNG contract in ADR-H-006.

The app has since been run on it and driven through a complete purchase: Home → Shop → variant selection → cart → checkout → **order `MD-2026-00001`, status `paid`**. The server-side invariants were then read back out of the database rather than assumed — `StockHold` `committed`, `OutboxMessage` `stock.commit` `sent`, and append-only `StockMovement` rows of `-2` and `-3` with reason `sale` against order 1, matching cart quantities exactly.

**What this does and does not change.** That legacy purchase run did not exercise 200% font scaling.
The reproducible check is `adb shell settings put system font_scale 2.0`, relaunch, and inspect all
twelve screen components. Current mobile acceptance uses the named API 36 AVD from ADR-H-006.

**The general lesson is the one worth keeping:** "I cannot verify this here" is a claim about the environment, and it needs checking with the same rigour as a claim about the code. This one was asserted rather than tested, and it was false.

Running the legacy app also surfaced a defect that the then-passing test suite did not: checkout
returned 500 with `Table 'metrodrip.inventory_idempotencyrecord' doesn't exist`. Not a code fault —
`makemigrations --check` reported no drift — but three migrations from that work stream had never
been applied to the development database. The test suite builds its own schema and therefore cannot
detect an operator's stale local schema.

## ADR-P5-004 — P2 completion: measure consume_order_holds latency in staging

- **Status:** Accepted
- **Context:** The consume_order_holds function iterated over every active stock hold on an order. For each hold, it enqueued a commit message and called the synchronous commit_holds service function. In local development (INVENTORY_PROVIDER=local), this resulted in redundant synchronous DB transactions. However, in staging (INVENTORY_PROVIDER=service), commit_holds makes an HTTP request to the inventory strangler sidecar. This caused a massive N+1 network latency during payment processing: an order with 10 items would make 10 sequential HTTP POST requests to the sidecar, blocking the payment confirmation thread and failing Hard Invariant 2 (payments should be fast and reliable).
- **Decision:** Group the active stock holds by checkout_id before committing. Since an order's active stock holds almost always share a single checkout_id generated during the cart checkout process, commit_holds (which acts on the entire checkout_id group) only needs to be called once per unique checkout session.
- **Consequences:** The N+1 bug is fixed. Orders with multiple items now make a single network call to the inventory sidecar, bringing the latency down to a single network round-trip. Using .update() instead of iterating .save() also reduces local database write latency.


## ADR-P3-027 — Refund and cancel are atomic per order, and the ledger boundary is named

- **Status:** Accepted
- **Date:** 2026-08-24
- **Context:** `OrderAdmin.mark_as_refunded` transitioned the order to REFUNDED and *then* restored each line in a bare loop. `AI Documentation Notes.md` recorded this honestly ("the multi-line orchestration is not yet one encompassing transaction") but it sat as a documented gap rather than a fix. `ATOMIC_REQUESTS` is not set anywhere in `config/settings/`, so nothing implicit was covering it either. `mark_as_cancelled` had the same shape.
- **Two defects, not one.** The documented one was partial restoration: a failure on line 2 of 3 leaves the order REFUNDED with part of its stock back. The undocumented one was worse — only `IllegalTransition` was caught, so any *other* exception (a ledger fault, a database error) escaped the admin action entirely, 500'd the request, and silently skipped every remaining order in the merchant's selection with no record of which ones were processed.
- **Decision:** Wrap each order's transition and all of its line restorations in one `transaction.atomic()` block, and catch non-`IllegalTransition` failures per order so one bad row cannot abort the rest of the selection.
- **The transaction is per order, not per queryset.** A refund is a complete unit of work on its own; order B failing is no reason to un-refund order A. A queryset-wide block would make a merchant's whole selection hostage to its worst row, which trades one partial-failure mode for a larger one.
- **The limit under `INVENTORY_PROVIDER=service`, stated rather than buried.** `adjust_stock` is then an HTTP call to a ledger writing on its own connection, so `transaction.atomic()` **cannot roll its writes back**. A mid-loop failure would roll back the order transition while the ledger keeps the lines it already applied, and a retry would apply them a second time because a signed delta is not idempotent. That direction is an *oversell* risk, whereas the pre-fix behaviour failed toward under-selling. **This makes the refund path an unmet precondition for selecting `service`** — a narrower, more concrete cutover blocker than the ones ADR-P3-021 listed, and one nothing had previously named. Closing it needs an idempotency-keyed restore on the ledger contract (the shape ADR-P3-016 already uses for reserve and commit), not another transaction.
- **Verification:** `tests/test_admin.py::TestRefundAtomicity` — two tests, both confirmed to **fail against the pre-fix code** before being accepted as passing. One drives a real `adjust_stock` on line 1 and raises on line 2, then asserts the order is still PAID and no variant was restocked; the other asserts a healthy order in the same selection still refunds when a sibling fails.
- **Consequences:** Under the shipping default (`local`) the refund path is now exact. Under `service` it is bounded and documented rather than silently wrong. `mark_as_cancelled` gets the same treatment, though its exposure was always lower — release is the safe direction, and the TTL sweep is its backstop.

## ADR-P3-028 — The stock commit inside the payment transaction gets its own budget

- **Status:** Accepted
- **Date:** 2026-08-24
- **Context:** ADR-P3-025 recorded the residual risk plainly: under `INVENTORY_PROVIDER=service`, `consume_order_holds` makes an HTTP call while the payment transaction holds a row lock on `Payment`, and called it "the next thing to address before anyone selects `service` in production."
- **What the budget actually was.** The commit used `_WRITE_POLICY`: 3 attempts × (1s connect + 5s read), plus backoff. **Measured against a deliberately stalled ledger: 7.12s–15.14s per call**, every second of it spent holding that lock. ADR-P3-018 already names this exact shape as the thing to avoid — "holding a database transaction open across an HTTP call would put network latency inside a row lock" — and it was right; the commit path was simply still doing it.
- **Decision:** A separate `_IN_TXN_WRITE_POLICY` (1 attempt, 1s connect + 2s read) selected by an explicit `inside_transaction=True` argument threaded through `commit_holds`. **Measured after: 2.00s, consistently — a 7.6× reduction in worst-case lock hold.**
- **Why cutting the retries is free rather than a trade.** `consume_order_holds` commits a `stock.commit` outbox row *in the same transaction, before it calls* (ADR-P3-018). A timeout therefore loses only the immediacy of the common case, never the commit itself: the drainer retries with the full budget outside any transaction, which is exactly where ADR-P3-018 says retries belong. Retrying inside the lock was buying a second copy of a guarantee the outbox already provides, and paying for it in lock-hold time.
- **`_cover_shortfall` deliberately keeps the full budget**, and the asymmetry is the point. Nothing enqueues those calls — that path *is* the last attempt, and when it fails the order is paid and unfulfillable (a human refund decision). A tight budget there would trade lock time for exactly the outcome the retries exist to prevent. The code says so at the call site, because "make it consistent" is the obvious wrong fix.
- **Alternative rejected:** moving the commit entirely out of the transaction and relying on the outbox alone. That is a larger change to the money path for a benefit the tight budget already delivers, and it would give up immediate stock movement in the common case — which is the property that keeps the storefront's availability honest between payment and the next drain.
- **Explicit argument rather than a thread-local.** A context variable would have avoided touching the provider protocol, but hidden global state is exactly what makes a policy question like this invisible at the call site. The signature now says which callers hold a transaction.
- **Verification:** `tests/test_commit_budget.py` — wall-clock assertions against a real socket that accepts the request and never answers (a refused connection fails in milliseconds and would prove nothing about a read timeout). Three tests: the in-transaction call gives up inside its budget; the retry path deliberately outlasts it, so a later change that gave every caller the tight budget would be caught; and a dead port still fails closed, so bounding the budget did not turn a failed commit into a silent success.
- **What this does not do.** It does not measure real load against a deployed staging environment — nothing has still ever run this provider outside tests. It removes the specific hazard ADR-P3-025 named; the staging measurement remains worth doing before a production cutover.

## ADR-P3-029 — Rate limiting and TOTP two-factor for the back-office consoles

- **Status:** Accepted
- **Date:** 2026-08-24
- **Context:** DRF's throttles are applied per view class, so the 10/min `auth-burst` budget guarding `/api/mobile/v1/` never touched `/admin/` or `/merchant/` — Django admin views that hold staff access to every order and customer record. Those two surfaces had no brute-force control and no second factor: a guessed or stolen password was sufficient, at whatever rate the network allowed.
- **Decision:** Two controls, both on `ConsoleAuthenticationForm` so they cover both consoles at once.
  1. **Failure-counting rate limits** in two independent buckets — per username (5 per 15 min) and per client address (20 per 15 min).
  2. **TOTP two-factor** via `django-otp`, required for any account with a confirmed device, and optionally for everyone via `CONSOLE_REQUIRE_OTP`.
- **Why two buckets.** They stop different attacks. Per-username catches one account guessed from many addresses and is unaffected by proxies, botnets, or IPv6 rotation — it is the load-bearing control. Per-address catches many accounts probed from one source, which no single username's counter can see. The username limit is the stricter of the two on purpose: staff share office NAT, so a tight per-IP limit locks out the colleagues of whoever mistyped a password, while a per-username limit only ever affects the account under attack.
- **Counting failures, not attempts**, with a successful login clearing both buckets. Ordinary typo-then-correct traffic therefore never walks toward a lockout, which is what keeps a brute-force control from becoming a self-inflicted outage.
- **`X-Forwarded-For` is ignored by default.** The header is client-supplied, so trusting it unconditionally would let an attacker mint a fresh bucket per request — a per-IP limit that reads as a control while enforcing nothing is worse than none. `CONSOLE_LOGIN_TRUSTED_PROXY_DEPTH` counts entries in from the right, because each trusted proxy appends the address it actually saw. Set it to 1 wherever Caddy terminates traffic.
- **Enrollment is a one-way door.** A user with a confirmed device *must* present a token; there is no path that accepts the password alone. Without that, 2FA would be advisory — anyone holding the password could simply decline to send a code.
- **`CONSOLE_REQUIRE_OTP` defaults to off, and that is a security decision rather than a weak one.** Defaulting it on means the first deployment refuses every account that exists, *including the superuser needed to enroll anyone*. The only recovery is to disable the control — so a default-on flag would predictably be turned off and left off. Enrol first, then flip it; `python manage.py check_console_otp [--strict]` lists exactly which accounts would be locked out, and is suitable as a deploy gate.
- **Lockout messages do not distinguish a real account from a nonexistent one**, and the lockout check runs *before* `authenticate()`. The first keeps the control from becoming an account-enumeration oracle; the second means a locked-out guess costs a cache read instead of a password hash, and leaves no timing difference to measure.
- **Bad TOTP tokens count toward the same lockout.** Otherwise an attacker holding a stolen password gets unlimited guesses at six digits, which is only a million.
- **Enforcement also lives in `ConsoleSite.has_permission`, not only in the login form.** A session opened *before* a device was enrolled would otherwise stay unverified for its full lifetime — precisely the window enrolling a device is meant to close.
- **Consequences and operator burden, stated honestly:**
  - `django-otp` and `qrcode` join the locked stack; `django_otp` and its two plugins bring their own migrations.
  - `templates/admin/login.html` is now overridden, because Django's admin template renders `username` and `password` by name rather than looping the form — a new field would otherwise never appear, and the form would demand a token the page gave no way to type. It will need re-checking on a Django upgrade.
  - **Rate-limit state lives in `CACHES["default"]`, which is unconfigured and therefore per-process LocMemCache.** Under multiple Gunicorn workers each process keeps its own counters, so the effective limit is roughly the configured value times the worker count. It still bounds the attack, but not at the stated number. A shared cache (the Redis already in Compose) is the fix and should land before the limits are relied on as exact.
- **Verification:** `tests/test_console_login_security.py`, 11 tests — lockout after N failures including against the *correct* password, identical messaging for real and nonexistent accounts, counter cleared by a success, the address bucket catching cross-account probing, `X-Forwarded-For` ignored at depth 0 and honoured at depth 1, password-alone refused once enrolled, password-plus-token accepted, bad tokens counting toward the lockout, blanket enforcement refusing an unenrolled account, an unenrolled account still working while the flag is off, and a pre-enrollment session losing console access.

## ADR-P3-030 — What is blocked on something other than engineering, and what would unblock it

- **Status:** Accepted
- **Date:** 2026-08-24
- **Context:** Two long-standing items keep reappearing on completion plans as though they were unwritten code. They are not: both are fully implemented and blocked on an external resource nobody in the repository can supply. Recording that distinction stops each new plan from re-listing them as engineering work and estimating them as such.
- **Blocked — real provider credentials (pre-launch).** The PayMongo and J&T Express adapters are written against documented contracts and exercised only against simulated providers. **Unblock condition:** sandbox credentials for each. **Then:** run a real payment intent, a real webhook signature verification, and a real waybill booking; fix contract mismatches; record the result as an ADR naming what sandbox limitations still prevented verifying against production. Until that happens the correct status is "written, never executed against the real endpoint" — not "done", and not "to be built".
- **Blocked — public staging evidence (M1).** Host, DNS, and a trusted certificate are manual operator actions. **Unblock condition:** a host and a domain. The Compose and Caddy configuration for it already exists.
- **Why this is worth an ADR at all.** An item that is blocked externally and an item that is unbuilt look identical in a status table, and both read as "not done". They need opposite responses: one needs a purchase or an account signup, the other needs engineering time. Conflating them has already produced at least one plan that budgeted engineering effort for neither.
- **Consequence:** anything in this section should be re-checked against its unblock condition, not against the code.

### Correction to the record — a completion plan dated 2026-08-24

A completion plan scanned this repository at commit `958ee53` and listed, as its top three P1 items: the reserve-before-order saga ("still not built"), `INVENTORY_PROVIDER` being pinned to `local`, and the G3/G4 gates never having run against `service`. **All three were substantially wrong**, and each was wrong by quoting a status line from an ADR that a later ADR had superseded (ADR-P3-017 and ADR-P3-021 quoted over ADR-P3-022 and ADR-P3-025; see the strike-throughs there).

The plan was not careless — it cited real file paths and real ADR numbers. It failed because **this file's own convention made it fail**: superseding decisions are recorded as *new* ADRs, leaving the old entry's status lines intact and still marked "Accepted". A reader following ADR numbers forward finds the correction; a reader searching for a topic finds whichever entry mentions it first.

**The practice this changes:** when an ADR supersedes a specific status claim in an earlier one, strike the claim through *in place* and point at the superseding ADR. The historical record is preserved — struck text is still readable — while the stale claim stops presenting itself as current. Two such corrections were applied retroactively above.

## ADR-P5-005 — Provisioned staff auth shell and explicit console themes

- **Status:** Accepted
- **Date:** 2026-08-29
- **Context:** The Merchant and Administrator login pages inherited Django's fixed 28-em card and 100-pixel top margin. At 320 pixels the separately rendered header collided with the form, while desktop branding and inputs were visually generic. Both authenticated consoles were dark-only. Django's stock admin theme controller also stores a third `auto` value under `localStorage.theme`, while the MetroDrip storefront understands only explicit `light` or `dark`; visiting one surface could therefore make the other disagree. Public staff registration remains outside the security model: Merchant and Administrator accounts are created by an authorized operator.
- **Decision:** Both consoles share one responsive industrial split-panel authentication shell with role-specific identity and provisioned-account guidance. The separate Django header is removed on login only; email, password, TOTP, CSRF, rate-limit, and console-role behavior remains on the existing `ConsoleAuthenticationForm`. A repository-owned two-state controller replaces Django's stock three-state controller for these sites. It follows the operating-system preference until a user selects Light or Dark, then persists only that explicit value and synchronizes every selector's `aria-pressed` state. The selector appears on both login pages and in the authenticated sidebar. Console colors now resolve through semantic dark and light tokens, including distinct readable accent/status text, control borders, overlays, table scroll fades, and a dual-contrast focus ring.
- **Alternatives considered:** Keeping Django's fixed login template preserved less code but did not meet responsive or identity requirements. Keeping `auto` as a third visible option would reintroduce an incompatible stored value and make the user-approved two-state control ambiguous. Public Merchant/Admin signup was rejected because it changes staff authorization and account approval, not presentation.
- **Consequences:** The login page is reflow-safe at 320/390/768/1440 pixels and all authored controls remain at least 44 CSS pixels. A stored theme is intentionally shared with the storefront in the same browser. The brand panel stays dark in both modes to preserve console identity; the form and all authenticated workspace surfaces adapt. `templates/admin/login.html` remains an upstream-template override that must be reviewed on a Django upgrade. The new light palette adds maintained color tokens and therefore supersedes ADR-P5-002's historical “dark-only/no new colors” description.
- **Verification / review trigger:** `tests/test_console_separation.py` covers both identities, provisioned-account copy, field autocomplete/TOTP associations, live-region errors, theme controls, authenticated placement, and removal of Django's conflicting theme script. `tests/test_console_theme_contrast.py` enforces the text and non-text token pairs in both palettes. `scripts/check-responsive.mjs` exercises both login routes and authenticated consoles at 320/390/768/1024/1440 and checks apply/persist/ARIA theme behavior in headless Chrome. Re-run the targeted tests, selector guard, responsive harness, contrast/Lighthouse checks, and manual keyboard/light/dark review whenever Django admin templates or console tokens change.

## ADR-P5-006 — GitHub Pages publishes a validated guide-only artifact

- **Status:** Accepted
- **Date:** 2026-08-30
- **Context:** The first Actions-based Pages workflow deployed successfully but passed the repository root to `upload-pages-artifact`. That made backend, mobile, test, and operational files part of the publication input even though the site needs only one HTML document and its visual aids. The same run exposed stale Node 20 action versions. Separately, mobile lint passed locally only because Expo reused `.eslintcache`; a clean runner revealed that npm had nested `eslint-import-resolver-typescript` where `eslint-plugin-import` could not load its legacy resolver interface.
- **Decision:** Keep GitHub Pages configured with **GitHub Actions** as its source. Build a new artifact from `index.html` by resolving and allowlisting only referenced PNG/SVG assets under `docs/images`, then deploy it through separately permissioned build and `github-pages` environment jobs. Use the current Node 24-based official Action majors. Make the TypeScript resolver a pinned direct mobile development dependency and make `npm run lint` cache-free.
- **Alternatives considered:** Publishing from a branch was rejected because it reintroduces a second generated source tree. Uploading the repository root was rejected because it unnecessarily broadens the public artifact. Disabling import resolution would hide real alias mistakes. Trusting Expo's cache was rejected because fresh CI runners never share that state.
- **Consequences:** A Pages deploy cannot accidentally expose ordinary repository files and fails on missing or unsafe local asset references. Deployment permission exists only in the job that uses it. Mobile lint is slightly slower but deterministic across developer and clean CI environments. Repository administrators must leave Pages Source set to GitHub Actions; no secret or publication branch is required.
- **Verification / review trigger:** Run `pytest tests/test_guide_structure.py tests/test_pages_build.py`, build into a fresh directory, inspect its file inventory, run `npm ci && npm run lint`, validate both workflow YAML files, and confirm the deployed Pages URL after changes to the guide, asset policy, ESLint dependency graph, or Actions versions.
