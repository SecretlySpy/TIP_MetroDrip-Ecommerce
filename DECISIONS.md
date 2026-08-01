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

