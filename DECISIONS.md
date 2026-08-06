# MetroDrip Architecture Decision Register

- **Scope:** Tasks A-1 through A-4, Epic B, and the Epic C/D/G storefront-commerce layer (through the 2026-07-19 QA/hardening pass)
- **Status:** Accepted
- **Authority:** Extends the locked decisions in `MetroDrip_AI_Handover.md` section 11.
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
- **Consequences:** Guest status is determined by `Order.customer_id is None`. A verified order-claim flow may later attach matching-email guest orders to a newly registered customer. Deleting a customer sets existing order ownership to `NULL` and does not delete the orders.

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
- **Decision:** `MOCK_PAYMENTS` (settings flag) short-circuits PayMongo: checkout records a pending mock Payment and the success page — reached only through the signed order token with `?mock=1` — calls the same idempotent `confirm_order_paid()` service the webhook uses. dev.py auto-enables it only when no `PAYMONGO_SECRET_KEY` is configured; prod.py refuses to boot if the environment sets `MOCK_PAYMENTS=1`.
- **Rationale:** The demo must complete end-to-end (pay → stock decrement → email) without provider credentials, while Hard Invariant 3 (webhook = payment truth) stays intact everywhere deployed.
- **Consequences:** All confirmation side effects (payment flip, reservation commit, sale movement, Paid transition, notifications) live in `confirm_order_paid()`; the webhook and the mock path are thin callers, so their behavior can never diverge.

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
- **Implemented and tested:** the `StockHold` receipt and the paid path that reads it; `reserve_lines` / `commit_holds` / `release_holds` on the in-process provider; batch reads end to end; the ledger's v1 HTTP surface including reserve, commit, release, adjust, sweep and low-stock; the idempotency protocol; auth on every route.
- **Implemented but NOT verified against a live ledger:** the service provider's reserve/commit/release round trips. Driving them needs a database that is **not** pytest-django's own test database — pointing the service there is exactly what made every previous service-provider test a false green (ADR-P3-012). Standing that harness up is the gate.
- **Since added (ADR-P3-018):** the transactional outbox on the paid-commit path, its drain job, and correlation-id binding for background work.
- **Not started:** the reserve-before-order checkout restructure; the reconciliation job that resolves `StockHoldState.UNKNOWN` holds; concurrency gates G3–G6 through the real web and mobile checkout endpoints; the provider-equivalence suite. Checkout remains order-then-reserve inside one atomic block, which is correct for the in-process ledger and is why nothing shippable is blocked on the restructure.
- **Therefore `INVENTORY_PROVIDER` stays pinned to `{local}` in `prod.py`.** ADR-P3-005's rule holds: never flip a default until parity is *proven*, and parity is not proven by code existing.

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
