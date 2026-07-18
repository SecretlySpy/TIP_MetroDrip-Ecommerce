# AI Documentation Notes

## Document Metadata

- **Purpose:** Provide a machine-readable technical reference for the implemented MetroDrip codebase.
- **Inputs:** Repository source, migrations, settings, tests, `MetroDrip_AI_Handover.md`, and `DECISIONS.md`.
- **Outputs:** Current architecture, callable contracts, data model, control flow, dependency map, QA evidence, and implementation gaps.
- **Dependencies:** Post-change QA must pass before this document is regenerated.
- **Behavior:** Describes implemented behavior literally; planned behavior is labeled as not implemented.
- **Analysis Date:** 2026-07-18.
- **Implementation Stage:** Task A-1 scaffold and Task A-2 foundational schema, migrations, tests, and seed command complete.
- **QA Gate:** Passed with 55 tests passed and 1 intentional strict XFAIL.

## Repository Scope

- **Purpose:** Define the current deployable system boundary.
- **Inputs:** Django project, 10 first-party app packages, MySQL schema, Docker database service, and CI workflow.
- **Outputs:** One server-rendered Django monolith backed by one MySQL 8 database.
- **Dependencies:** Python 3.14, Django 5.2, MySQL 8, PyMySQL, environment configuration.
- **Behavior:** The only active HTTP route is Django Admin at `/admin/`. Public storefront and integration routes are not implemented.

### Technology Stack

| Layer | Implemented dependency | Current behavior |
|---|---|---|
| Language | Python 3.14 | Local virtual environment uses Python 3.14.4. |
| Framework | Django 5.2 | Installed version during QA was 5.2.16. |
| Database | MySQL 8 | Docker QA server uses MySQL 8.4.10, InnoDB, and `utf8mb4_0900_ai_ci`. |
| Driver | PyMySQL | Installed as the `MySQLdb` compatibility module before Django initializes. |
| Jobs | APScheduler | Dependency installed; no jobs or scheduler startup exists. |
| Frontend | Django Templates | Template directory exists; storefront templates, HTMX, and Alpine.js are absent. |
| Tests | pytest and pytest-django | Tests execute against real MySQL rather than SQLite. |
| Lint and format | Ruff | Lint and formatting checks pass. |
| CI | GitHub Actions | Runs Ruff and pytest against a MySQL 8.4 service on push and pull request. |

### Implemented Capability Matrix

| Capability | Status | Literal behavior |
|---|---|---|
| Project scaffold | Implemented | Split settings, 10 app packages, Docker MySQL, pytest, Ruff, and CI exist. |
| Customer identity | Schema-ready | Email is the login identifier; guest checkout has no Customer row. |
| Catalog | Data layer implemented | Categories, products, and Size × Color × Fit variants persist through Django ORM. |
| Effective pricing | Implemented | Variant override wins; otherwise the product base price is returned. |
| Inventory counters | Schema-ready | Availability is on-hand minus reserved; database prevents reserved exceeding on-hand. |
| Stock audit | Partially implemented | Movement rows validate direction and reject normal public ORM mutation/deletion paths. |
| Orders | Core data layer implemented | Order totals, unique order lines, snapshots, numbering, and guarded state transitions exist. |
| Payments | Schema-ready | One payment per order and one globally unique non-null provider reference are supported. |
| Shipping | Schema-ready | One shipment per order with J&T default and tracking fields is supported. |
| Wishlist | Schema-ready | One product bookmark per customer is enforced. |
| Reviews | Schema-ready | Rating and moderation storage exists; verified-purchase validation is absent. |
| Demo data | Implemented | Idempotent command creates 5 products and a complete 180-variant inventory matrix. |
| Storefront and checkout | Not implemented | No public routes, views, templates, cart, reservation, or checkout flow exists. |
| External APIs | Not implemented | No PayMongo, J&T, Semaphore, Google Maps, email-provider, CDN, or object-storage adapter exists. |

## System Architecture

- **Purpose:** Describe runtime composition, dependency direction, and domain boundaries.
- **Inputs:** Django settings, URL configuration, installed apps, models, and services.
- **Outputs:** Loaded Django application and relational domain graph.
- **Dependencies:** MySQL availability, environment values, and all applied migrations.
- **Behavior:** Django loads all domain apps into one process; business persistence uses the Django ORM and one database.

### Application Dependency Graph

```text
catalog.0001
├── accounts.0001 (also depends on auth.0012)
│   └── orders.0001 (via AUTH_USER_MODEL and catalog)
│       ├── inventory.0001
│       ├── payments.0001
│       ├── shipping.0001
│       └── reviews.0001
└── reviews.0001 also depends directly on catalog and accounts
```

- **Purpose:** Preserve foreign-key creation and reverse-migration order.
- **Inputs:** Migration dependency declarations.
- **Outputs:** Catalog first; dependent commerce tables after accounts and orders.
- **Dependencies:** Django migration executor.
- **Behavior:** Reversal removes leaf apps before orders, accounts, and catalog.

### Runtime Boot Flow

- **Purpose:** Initialize Django consistently across management, ASGI, and WSGI entrypoints.
- **Inputs:** Process environment, optional repository `.env`, and command-line arguments.
- **Outputs:** Configured Django application.
- **Dependencies:** PyMySQL, python-dotenv, Django settings loader, reachable MySQL.
- **Behavior:** PyMySQL installs as `MySQLdb`; base settings load `.env`; entrypoints default to development settings only when `DJANGO_SETTINGS_MODULE` is unset.

### Order Number Flow

- **Purpose:** Allocate collision-free public order identifiers.
- **Inputs:** Optional four-digit year.
- **Outputs:** `MD-YYYY-NNNNN` string.
- **Dependencies:** `OrderNumberSequence`, `transaction.atomic()`, and `select_for_update()`.
- **Behavior:** Uses the Asia/Manila local year by default, locks or creates its annual sequence, increments atomically, and raises after 99,999.

### Order State Flow

| Current status | Permitted next status |
|---|---|
| `pending` | `paid`, `cancelled` |
| `paid` | `packed`, `refunded` |
| `packed` | `shipped`, `refunded` |
| `shipped` | `delivered`, `refunded` |
| `delivered` | `refunded` |
| `cancelled` | none |
| `refunded` | none |

- **Purpose:** Enforce Hard Invariant 5 in application code.
- **Inputs:** Persisted order and requested target status.
- **Outputs:** One legal persisted transition or `IllegalTransition`.
- **Dependencies:** MySQL row locks and the `ALLOWED_TRANSITIONS` mapping.
- **Behavior:** Reloads and locks authoritative state before validation; ordinary save, queryset, bulk, explicit-PK, stale, and conflict-upsert bypasses are guarded.

### Inventory State Flow

- **Purpose:** Represent physical stock, reservations, and audit evidence.
- **Inputs:** `qty_on_hand`, `qty_reserved`, movement delta, movement reason, optional order.
- **Outputs:** `available = qty_on_hand - qty_reserved` and append-only application-level ledger rows.
- **Dependencies:** MySQL checks, protected foreign keys, and ORM mutation guards.
- **Behavior:** Current schema prevents negative availability and invalid movement signs. Operational reserve/release/sale services are not implemented.

### Guest Identity Flow

- **Purpose:** Keep guest checkout independent from registered authentication identities.
- **Inputs:** Nullable `Order.customer` and checkout `shipping_address` snapshot.
- **Outputs:** Guest order when `customer_id is None`.
- **Dependencies:** Custom `accounts.Customer` user model and `SET_NULL` deletion policy.
- **Behavior:** Guest checkout creates no Customer row; future claim-by-email logic must read the order snapshot.

## Configuration Modules

### Module: `manage.py`

- **Purpose:** Execute Django management commands.
- **Inputs:** `sys.argv` and optional `DJANGO_SETTINGS_MODULE` environment value.
- **Outputs:** Django command output; function returns `None` implicitly.
- **Dependencies:** `os`, `sys`, and `django.core.management.execute_from_command_line`.
- **Behavior:** Defaults settings to `config.settings.dev` and raises a contextual import error when Django is unavailable.

#### Function: `main()`

- **Purpose:** Initialize settings and dispatch the requested management command.
- **Inputs:** No explicit parameters; reads process state.
- **Outputs:** `None`.
- **Dependencies:** Django management command registry.
- **Behavior:** Mutates the process environment only when the settings variable is absent, then executes `sys.argv`.

### Module: `config/settings/base.py`

- **Purpose:** Define settings shared by development, test, and production.
- **Inputs:** Environment variables and repository `.env`.
- **Outputs:** Django settings for apps, middleware, templates, MySQL, auth, timezone, and static files.
- **Dependencies:** `pymysql`, `python-dotenv`, `pathlib`, and MySQL 8.
- **Behavior:** Registers 10 MetroDrip apps; selects MySQL; requests `utf8mb4`; pins session InnoDB and strict transactional SQL mode; sets `AUTH_USER_MODEL = "accounts.Customer"`; uses Asia/Manila display timezone with UTC storage.

### Module: `config/settings/dev.py`

- **Purpose:** Provide safe local-development overrides.
- **Inputs:** Shared settings and optional secret environment value.
- **Outputs:** Debug-enabled settings with localhost hosts and console email.
- **Dependencies:** `config.settings.base`.
- **Behavior:** Uses a development-only fallback secret; never supplies production security behavior.

### Module: `config/settings/test.py`

- **Purpose:** Provide deterministic integration-test overrides.
- **Inputs:** Development settings and MySQL environment values.
- **Outputs:** MySQL test configuration with MD5 password hashing and in-memory email.
- **Dependencies:** Real MySQL row-lock behavior.
- **Behavior:** Does not replace MySQL with SQLite.

### Module: `config/settings/prod.py`

- **Purpose:** Provide production security and connection settings.
- **Inputs:** Required `DJANGO_SECRET_KEY` and comma-separated `DJANGO_ALLOWED_HOSTS`.
- **Outputs:** HTTPS redirect, secure cookies, proxy SSL handling, 30-day HSTS, and 60-second persistent database connections.
- **Dependencies:** Shared settings and a correctly configured reverse proxy.
- **Behavior:** Fails during import when the secret is absent; HSTS preload remains intentionally disabled during pre-launch bake-in.

### Module: `config/urls.py`

- **Purpose:** Define the root URL table.
- **Inputs:** Incoming request path.
- **Outputs:** Django Admin resolution for `/admin/`.
- **Dependencies:** `django.contrib.admin`.
- **Behavior:** No public app URL modules are included.

### Module: `config/asgi.py`

- **Purpose:** Expose an ASGI application object.
- **Inputs:** Optional preselected settings module.
- **Outputs:** Module variable `application`.
- **Dependencies:** `get_asgi_application()`.
- **Behavior:** Defaults to development settings and initializes Django during import.

### Module: `config/wsgi.py`

- **Purpose:** Expose a WSGI application object.
- **Inputs:** Optional preselected settings module.
- **Outputs:** Module variable `application`.
- **Dependencies:** `get_wsgi_application()`.
- **Behavior:** Defaults to development settings and initializes Django during import.

## App Registration Modules

| Module | Purpose | Inputs | Outputs | Dependencies | Behavior |
|---|---|---|---|---|---|
| `apps/accounts/apps.py` | Register accounts domain. | Django app loading. | `AccountsConfig`. | `AppConfig`. | Name is `apps.accounts`; uses `BigAutoField`. |
| `apps/catalog/apps.py` | Register catalog domain. | Django app loading. | `CatalogConfig`. | `AppConfig`. | Name is `apps.catalog`; uses `BigAutoField`. |
| `apps/inventory/apps.py` | Register inventory domain. | Django app loading. | `InventoryConfig`. | `AppConfig`. | Name is `apps.inventory`; uses `BigAutoField`. |
| `apps/orders/apps.py` | Register orders domain. | Django app loading. | `OrdersConfig`. | `AppConfig`. | Name is `apps.orders`; uses `BigAutoField`. |
| `apps/payments/apps.py` | Register payments domain. | Django app loading. | `PaymentsConfig`. | `AppConfig`. | Name is `apps.payments`; uses `BigAutoField`. |
| `apps/shipping/apps.py` | Register shipping domain. | Django app loading. | `ShippingConfig`. | `AppConfig`. | Name is `apps.shipping`; uses `BigAutoField`. |
| `apps/reviews/apps.py` | Register reviews domain. | Django app loading. | `ReviewsConfig`. | `AppConfig`. | Name is `apps.reviews`; uses `BigAutoField`. |
| `apps/notifications/apps.py` | Register notification shell. | Django app loading. | `NotificationsConfig`. | `AppConfig`. | Contains no notification behavior. |
| `apps/cms/apps.py` | Register CMS shell. | Django app loading. | `CmsConfig`. | `AppConfig`. | Contains no CMS behavior. |
| `apps/storefront/apps.py` | Register storefront shell. | Django app loading. | `StorefrontConfig`. | `AppConfig`. | Contains no storefront behavior. |

## Domain Module: `apps/accounts/models.py`

- **Purpose:** Define registered customers and wishlists.
- **Inputs:** Authentication credentials, profile data, saved-address JSON, and product bookmarks.
- **Outputs:** Customer and WishlistItem ORM rows.
- **Dependencies:** Django auth base classes, `catalog.Product`, and timezone utilities.
- **Behavior:** Uses email as username; guest orders are represented outside this module by a nullable order customer.

### Class: `CustomerManager(BaseUserManager)`

- **Purpose:** Create email-authenticated customer and superuser rows.
- **Inputs:** Email, optional password, and extra model fields.
- **Outputs:** Persisted `Customer`.
- **Dependencies:** Django password hashing and manager database alias.
- **Behavior:** Normalizes email and stores either a password hash or Django unusable-password marker.

#### Function: `CustomerManager._create(self, email, password, **extra_fields)`

- **Purpose:** Implement shared customer persistence.
- **Inputs:** Required truthy email; password may be `None`; arbitrary valid Customer fields.
- **Outputs:** Saved `Customer` instance.
- **Dependencies:** `normalize_email()`, `set_password()`, `set_unusable_password()`.
- **Behavior:** Raises `ValueError` for missing email and writes using `self._db`.

#### Function: `CustomerManager.create_user(self, email, password=None, **extra_fields)`

- **Purpose:** Create a non-staff, non-superuser account by default.
- **Inputs:** Email, optional password, optional field overrides.
- **Outputs:** Saved `Customer`.
- **Dependencies:** `CustomerManager._create()`.
- **Behavior:** Defaults privilege flags to false without overriding explicit caller values.

#### Function: `CustomerManager.create_superuser(self, email, password, **extra_fields)`

- **Purpose:** Create an administrative customer identity.
- **Inputs:** Email, non-empty password, optional field overrides.
- **Outputs:** Saved privileged `Customer`.
- **Dependencies:** `CustomerManager._create()`.
- **Behavior:** Requires both privilege flags to be true and raises `ValueError` otherwise.

### Class: `Customer(AbstractBaseUser, PermissionsMixin)`

- **Purpose:** Represent one registered shopper and Django authentication identity.
- **Inputs:** `email`, `name`, optional `phone`, address-list JSON, active/staff flags.
- **Outputs:** Auth-compatible customer row and reverse account relationships.
- **Dependencies:** Django auth group/permission tables.
- **Behavior:** `USERNAME_FIELD` is `email`; `REQUIRED_FIELDS` contains `name`; email is unique.
- **Fields:** `email`, `name`, `phone`, `addresses`, `is_active`, `is_staff`, `date_joined`, plus inherited password/login/permission fields.

#### Function: `Customer.__str__(self)`

- **Purpose:** Provide readable identity text.
- **Inputs:** Customer instance.
- **Outputs:** Email string.
- **Dependencies:** `email` field.
- **Behavior:** No side effects.

### Class: `WishlistItem(models.Model)`

- **Purpose:** Store a product-level customer bookmark.
- **Inputs:** Customer and Product foreign keys.
- **Outputs:** Wishlist row with creation timestamp.
- **Dependencies:** `Customer` and `catalog.Product`.
- **Behavior:** Cascades with either owner and enforces unique `(customer, product)` through `uniq_wishlist_entry`.

#### Function: `WishlistItem.__str__(self)`

- **Purpose:** Provide readable wishlist text.
- **Inputs:** Wishlist instance.
- **Outputs:** Customer and product joined with a heart symbol.
- **Dependencies:** Related model string methods.
- **Behavior:** May load related objects; performs no write.

## Domain Module: `apps/catalog/models.py`

- **Purpose:** Define product classification and three-axis SKU variants.
- **Inputs:** Category, product, price, image URL list, Size, Color, and Fit data.
- **Outputs:** Catalog ORM rows and effective centavo pricing.
- **Dependencies:** Django ORM.
- **Behavior:** One product belongs to one protected category; one axis combination and one SKU may exist only once.

### Class: `Category(models.Model)`

- **Purpose:** Classify products.
- **Inputs:** Unique `name` and unique `slug`.
- **Outputs:** Category row and reverse `products` relation.
- **Dependencies:** Products protect referenced categories from deletion.
- **Behavior:** Orders rows alphabetically by name.

#### Function: `Category.__str__(self)`

- **Purpose:** Return display text.
- **Inputs:** Category instance.
- **Outputs:** Category name.
- **Dependencies:** `name` field.
- **Behavior:** No side effects.

### Class: `Size(models.TextChoices)`

- **Purpose:** Define supported apparel sizes.
- **Inputs:** Model/form choice validation.
- **Outputs:** Values `XS`, `S`, `M`, `L`, `XL`, and `XXL`.
- **Dependencies:** Django TextChoices.
- **Behavior:** Labels values from Extra Small through 2X Large.

### Class: `Fit(models.TextChoices)`

- **Purpose:** Define supported apparel fits.
- **Inputs:** Model/form choice validation.
- **Outputs:** `slim`, `regular`, and `oversized`.
- **Dependencies:** Django TextChoices.
- **Behavior:** Provides canonical stored strings and display labels.

### Class: `Product(models.Model)`

- **Purpose:** Store sellable product-level content and default price.
- **Inputs:** Name, unique slug, description, category, integer-centavo base price, image URL JSON, active flag.
- **Outputs:** Product row with reverse variants, wishes, and reviews.
- **Dependencies:** `Category` and object-storage/CDN URL convention.
- **Behavior:** Protects its category; orders newest products first; product deletion cascades only to removable variants.
- **Fields:** `name`, `slug`, `description`, `category`, `base_price`, `images`, `is_active`, `created_at`.

#### Function: `Product.__str__(self)`

- **Purpose:** Return display text.
- **Inputs:** Product instance.
- **Outputs:** Product name.
- **Dependencies:** `name` field.
- **Behavior:** No side effects.

### Class: `ProductVariant(models.Model)`

- **Purpose:** Represent one Size × Color × Fit SKU.
- **Inputs:** Product, unique SKU, size, color, fit, optional centavo price override.
- **Outputs:** Variant row with reverse stock, movement, and order-line relations.
- **Dependencies:** `Product`, `Size`, and `Fit`.
- **Behavior:** Enforces `uniq_variant_axes` on `(product, size, color, fit)` and globally unique SKU.

#### Function: `ProductVariant.__str__(self)`

- **Purpose:** Return SKU display text.
- **Inputs:** Variant instance.
- **Outputs:** SKU string.
- **Dependencies:** `sku` field.
- **Behavior:** No side effects.

#### Property: `ProductVariant.price(self)`

- **Purpose:** Resolve effective unit price in centavos.
- **Inputs:** Variant and related product.
- **Outputs:** `price_override` when non-null; otherwise `product.base_price`.
- **Dependencies:** Related product may require a database fetch.
- **Behavior:** Performs no write and never uses floating-point arithmetic.

## Domain Module: `apps/inventory/models.py`

- **Purpose:** Define single-warehouse counters and immutable application-level stock audit rows.
- **Inputs:** Variant, physical quantity, reserved quantity, threshold, movement delta/reason, optional order.
- **Outputs:** StockRecord and StockMovement rows.
- **Dependencies:** Catalog variants, orders, MySQL checks, and Django ORM guards.
- **Behavior:** A-2 supports initial seed balances; operational mutation services begin in B-1.

### Class: `StockRecord(models.Model)`

- **Purpose:** Store current stock counters for exactly one variant.
- **Inputs:** Variant, nonnegative `qty_on_hand`, `qty_reserved`, and `low_stock_threshold`.
- **Outputs:** One-to-one stock row.
- **Dependencies:** `catalog.ProductVariant`.
- **Behavior:** Cascades with a removable variant and enforces `qty_reserved <= qty_on_hand` through `chk_reserved_lte_on_hand`.

#### Function: `StockRecord.__str__(self)`

- **Purpose:** Return readable counter text.
- **Inputs:** StockRecord instance.
- **Outputs:** Variant ID, on-hand value, and reserved value.
- **Dependencies:** Stored fields.
- **Behavior:** No side effects.

#### Property: `StockRecord.available(self)`

- **Purpose:** Calculate sellable inventory.
- **Inputs:** `qty_on_hand` and `qty_reserved`.
- **Outputs:** Integer difference.
- **Dependencies:** Database constraint prevents a persisted negative result.
- **Behavior:** No database write.

### Class: `MovementReason(models.TextChoices)`

- **Purpose:** Define stock audit reasons.
- **Inputs:** Movement creation and form validation.
- **Outputs:** `sale`, `restock`, `adjustment`, and `return`.
- **Dependencies:** Django TextChoices.
- **Behavior:** Database sign constraint assigns allowed delta direction by reason.

### Class: `AppendOnlyMovementQuerySet(models.QuerySet)`

- **Purpose:** Prevent public queryset APIs from rewriting or deleting stock history.
- **Inputs:** Queryset mutation calls.
- **Outputs:** Read/create results or `TypeError`.
- **Dependencies:** Django QuerySet.
- **Behavior:** Read operations and plain inserts remain available; mutation and conflict-update APIs are rejected.

#### Function: `AppendOnlyMovementQuerySet.update(self, **kwargs)`

- **Purpose:** Reject row updates.
- **Inputs:** Any proposed field values.
- **Outputs:** No row count; raises `TypeError`.
- **Dependencies:** None.
- **Behavior:** Performs no SQL update.

#### Function: `AppendOnlyMovementQuerySet.bulk_update(self, objs, fields, batch_size=None)`

- **Purpose:** Reject bulk row updates.
- **Inputs:** Objects, fields, optional batch size.
- **Outputs:** Raises `TypeError`.
- **Dependencies:** None.
- **Behavior:** Performs no SQL update.

#### Function: `AppendOnlyMovementQuerySet.delete(self)`

- **Purpose:** Reject queryset deletion.
- **Inputs:** Queryset selection.
- **Outputs:** Raises `TypeError`.
- **Dependencies:** None.
- **Behavior:** Performs no SQL delete.

#### Function: `AppendOnlyMovementQuerySet.bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False, update_fields=None, unique_fields=None)`

- **Purpose:** Permit append-only bulk inserts while rejecting MySQL conflict rewrites.
- **Inputs:** Django's complete public bulk-create argument set, including positional forms.
- **Outputs:** Created object list or `TypeError`.
- **Dependencies:** Django bulk insert implementation.
- **Behavior:** Rejects `update_conflicts=True`; delegates plain inserts and optional ignore-conflicts inserts.

### Class: `StockMovementManager`

- **Purpose:** Expose the append-only queryset as the default movement manager.
- **Inputs:** ORM manager operations.
- **Outputs:** Querysets and created rows.
- **Dependencies:** `AppendOnlyMovementQuerySet`.
- **Behavior:** Declares no additional methods.

### Class: `StockMovement(models.Model)`

- **Purpose:** Persist one immutable quantity-on-hand audit event.
- **Inputs:** Variant, signed delta, reason, optional referenced order.
- **Outputs:** Timestamped movement row.
- **Dependencies:** ProductVariant and optional Order use `PROTECT` deletion.
- **Behavior:** Orders newest first; `chk_movement_reason_delta` requires sale negative, restock/return positive, and adjustment nonzero.

#### Function: `StockMovement.__str__(self)`

- **Purpose:** Return readable audit text.
- **Inputs:** Movement instance.
- **Outputs:** Variant ID, signed delta, and reason.
- **Dependencies:** Stored fields.
- **Behavior:** No side effects.

#### Function: `StockMovement.save(self, *args, **kwargs)`

- **Purpose:** Permit inserts and reject instance updates.
- **Inputs:** Standard Django save arguments.
- **Outputs:** `None` on insert or `TypeError` when `pk` is already set.
- **Dependencies:** Django Model save.
- **Behavior:** Writes one new row only.

#### Function: `StockMovement.delete(self, *args, **kwargs)`

- **Purpose:** Reject instance deletion.
- **Inputs:** Standard Django delete arguments.
- **Outputs:** Raises `TypeError`.
- **Dependencies:** None.
- **Behavior:** Performs no deletion.

## Domain Module: `apps/orders/models.py`

- **Purpose:** Define order records, lines, annual numbering state, and the guarded lifecycle.
- **Inputs:** Customer or guest identity, shipping snapshot, integer-centavo totals, variant lines, and status targets.
- **Outputs:** Order, OrderItem, and OrderNumberSequence rows.
- **Dependencies:** Custom auth model, catalog variants, MySQL transactions, and row locks.
- **Behavior:** New orders begin Pending; totals reconcile in the database; legal status edges are enforced in code.

### Class: `OrderStatus(models.TextChoices)`

- **Purpose:** Define stored order lifecycle states.
- **Inputs:** Model fields and transition validation.
- **Outputs:** `pending`, `paid`, `packed`, `shipped`, `delivered`, `cancelled`, `refunded`.
- **Dependencies:** Django TextChoices.
- **Behavior:** Terminal states are Cancelled and Refunded.

### Constant: `ALLOWED_TRANSITIONS`

- **Purpose:** Define every legal directed state edge.
- **Inputs:** Current `OrderStatus`.
- **Outputs:** Set of allowed target statuses.
- **Dependencies:** `OrderStatus`.
- **Behavior:** Paid orders exit through Refunded; only Pending may become Cancelled.

### Constant: `MAX_ORDER_SEQUENCE = 99_999`

- **Purpose:** Preserve exactly five sequence digits.
- **Inputs:** Current annual counter.
- **Outputs:** Exhaustion boundary.
- **Dependencies:** Order-number service and database check.
- **Behavior:** Allocation beyond the boundary is rejected.

### Class: `IllegalTransition(Exception)`

- **Purpose:** Identify invalid order state operations.
- **Inputs:** Unknown, non-pending initial, direct, stale, bulk, conflict, or disallowed target operation.
- **Outputs:** Raised exception.
- **Dependencies:** Order model and queryset guards.
- **Behavior:** Prevents the invalid write from being committed.

### Class: `OrderQuerySet(models.QuerySet)`

- **Purpose:** Guard public bulk ORM paths around the order state machine.
- **Inputs:** Update, bulk-update, and bulk-create requests.
- **Outputs:** Delegated non-status result or `IllegalTransition`.
- **Dependencies:** Django QuerySet.
- **Behavior:** Covers keyword and positional conflict-upsert arguments.

#### Function: `OrderQuerySet.update(self, **kwargs)`

- **Purpose:** Block queryset status assignment.
- **Inputs:** Proposed update fields.
- **Outputs:** Affected row count for non-status updates; otherwise `IllegalTransition`.
- **Dependencies:** Django QuerySet update.
- **Behavior:** No status SQL executes when `status` is present.

#### Function: `OrderQuerySet.bulk_update(self, objs, fields, batch_size=None)`

- **Purpose:** Block status in bulk updates.
- **Inputs:** Objects, field names, optional batch size.
- **Outputs:** Affected row count or `IllegalTransition`.
- **Dependencies:** Django bulk update.
- **Behavior:** Delegates only when `status` is absent.

#### Function: `OrderQuerySet.bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False, update_fields=None, unique_fields=None)`

- **Purpose:** Enforce Pending initial state and prevent conflict-based status rewrites.
- **Inputs:** Django's complete public bulk-create arguments.
- **Outputs:** Created object list or `IllegalTransition`.
- **Dependencies:** `OrderStatus` and Django bulk insert.
- **Behavior:** Materializes input, rejects unknown/non-Pending status, rejects conflict updates containing status, then delegates allowed inserts.

### Class: `OrderManager`

- **Purpose:** Expose `OrderQuerySet` protections through `Order.objects`.
- **Inputs:** ORM manager calls.
- **Outputs:** Protected querysets and rows.
- **Dependencies:** `OrderQuerySet`.
- **Behavior:** Declares no additional methods.

### Class: `Order(models.Model)`

- **Purpose:** Persist one guest or account-owned commercial order.
- **Inputs:** Unique order number, optional customer, status, subtotal, shipping fee, total, and shipping-address JSON.
- **Outputs:** Order row and reverse items, movement, payment, shipment, and review relations.
- **Dependencies:** `AUTH_USER_MODEL` and MySQL check constraints.
- **Behavior:** `customer=NULL` denotes guest; customer deletion sets null; `chk_order_total_reconciles` enforces `total = subtotal + shipping_fee`; newest orders sort first.
- **Fields:** `order_no`, `customer`, `status`, `subtotal`, `shipping_fee`, `total`, `shipping_address`, `created_at`.

#### Function: `Order.__str__(self)`

- **Purpose:** Return public identifier text.
- **Inputs:** Order instance.
- **Outputs:** `order_no`.
- **Dependencies:** Stored field.
- **Behavior:** No side effects.

#### Function: `Order.save(self, *args, **kwargs)`

- **Purpose:** Persist non-state data while preventing ordinary direct status changes.
- **Inputs:** Standard save arguments and current instance state.
- **Outputs:** `None` or `IllegalTransition`.
- **Dependencies:** MySQL transaction, row lock, and stored order row.
- **Behavior:** Adding instances must be Pending even with explicit PKs. Explicit non-status field updates cannot write status. Full/status saves lock and compare the authoritative stored state before delegating.

#### Function: `Order.transition_to(self, new_status)`

- **Purpose:** Perform one legal, atomic state transition.
- **Inputs:** Persisted Order and target enum/value.
- **Outputs:** Same Order instance with synchronized status.
- **Dependencies:** `ALLOWED_TRANSITIONS`, `transaction.atomic()`, and `select_for_update()`.
- **Behavior:** Rejects unsaved/unknown/disallowed targets; locks the fresh row; writes only status through the parent save implementation.

### Class: `OrderItem(models.Model)`

- **Purpose:** Snapshot one purchased variant line.
- **Inputs:** Order, protected variant, quantity, integer-centavo unit price.
- **Outputs:** OrderItem row.
- **Dependencies:** Order and ProductVariant.
- **Behavior:** Cascades with order, protects variant, requires `qty >= 1`, and enforces one line per `(order, variant)`.

#### Function: `OrderItem.__str__(self)`

- **Purpose:** Return readable line text.
- **Inputs:** OrderItem instance.
- **Outputs:** Order ID, variant ID, and quantity.
- **Dependencies:** Stored foreign-key IDs.
- **Behavior:** No related fetch required.

### Class: `OrderNumberSequence(models.Model)`

- **Purpose:** Store one row-locked counter per business year.
- **Inputs:** Four-digit unique year and counter from 0 through 99,999.
- **Outputs:** Sequence row.
- **Dependencies:** Order number service.
- **Behavior:** Database constraints `chk_order_sequence_four_digit_year` and `chk_order_sequence_max_99999` enforce format boundaries.

#### Function: `OrderNumberSequence.__str__(self)`

- **Purpose:** Return readable sequence state.
- **Inputs:** Sequence instance.
- **Outputs:** Year and last value.
- **Dependencies:** Stored fields.
- **Behavior:** No side effects.

## Service Module: `apps/orders/services.py`

- **Purpose:** Host order business operations outside views.
- **Inputs:** Service arguments and ORM state.
- **Outputs:** Order-domain results or explicit service errors.
- **Dependencies:** Order models, timezone, and Django transactions.
- **Behavior:** Only annual number allocation is implemented at A-2.

### Class: `InvalidOrderYear(ValueError)`

- **Purpose:** Signal malformed order-number year input.
- **Inputs:** Boolean, non-integer, or integer outside 1000 through 9999.
- **Outputs:** Raised exception.
- **Dependencies:** `next_order_no()`.
- **Behavior:** No database mutation occurs.

### Class: `OrderNumberExhausted(RuntimeError)`

- **Purpose:** Signal exhausted annual identifier space.
- **Inputs:** Counter already at 99,999.
- **Outputs:** Raised exception.
- **Dependencies:** `next_order_no()`.
- **Behavior:** Counter remains unchanged.

### Function: `next_order_no(year=None)`

- **Purpose:** Allocate a unique `MD-YYYY-NNNNN` number.
- **Inputs:** Optional four-digit integer year; `None` selects current Asia/Manila year.
- **Outputs:** Formatted string.
- **Dependencies:** `OrderNumberSequence`, timezone, atomic transaction, and row locking.
- **Behavior:** Rejects Boolean despite `bool` being an `int` subclass; locks or creates the annual row; checks exhaustion; increments and persists atomically.

## Domain Module: `apps/payments/models.py`

- **Purpose:** Define one provider-facing payment record per order.
- **Inputs:** Order, optional PayMongo reference, method, status, integer-centavo amount, optional paid timestamp.
- **Outputs:** Payment row.
- **Dependencies:** Order model.
- **Behavior:** Payment cascades with order; non-null `provider_ref` is globally unique; webhook truth enforcement is not implemented.

### Class: `PaymentMethod(models.TextChoices)`

- **Purpose:** Define accepted provider methods.
- **Inputs:** Payment persistence/form validation.
- **Outputs:** `card`, `gcash`, and `maya`.
- **Dependencies:** Django TextChoices.
- **Behavior:** Provides stored values and display labels.

### Class: `PaymentStatus(models.TextChoices)`

- **Purpose:** Define payment record states.
- **Inputs:** Payment persistence/form validation.
- **Outputs:** `pending`, `paid`, `failed`, and `refunded`.
- **Dependencies:** Django TextChoices.
- **Behavior:** Direct mutation is currently unrestricted.

### Class: `Payment(models.Model)`

- **Purpose:** Persist payment reconciliation state.
- **Inputs:** One-to-one order, provider reference, method, status, amount, paid time.
- **Outputs:** Payment row and `order.payment` reverse accessor.
- **Dependencies:** Order.
- **Behavior:** Allows multiple null provider references; rejects duplicate non-null references; amount is nonnegative MySQL unsigned INT.

#### Function: `Payment.__str__(self)`

- **Purpose:** Return payment summary text.
- **Inputs:** Payment instance.
- **Outputs:** Order ID, method, and status.
- **Dependencies:** Stored fields.
- **Behavior:** No side effects.

## Domain Module: `apps/shipping/models.py`

- **Purpose:** Define one fulfillment record per order.
- **Inputs:** Order, courier, waybill, tracking URL, shipment status, booking time.
- **Outputs:** Shipment row.
- **Dependencies:** Order model.
- **Behavior:** Defaults courier to `jnt`; adapter, booking, webhook, and polling behavior are not implemented.

### Class: `ShipmentStatus(models.TextChoices)`

- **Purpose:** Define shipment states.
- **Inputs:** Shipment persistence/form validation.
- **Outputs:** `pending`, `booked`, `in_transit`, `out_for_delivery`, `delivered`, `failed`.
- **Dependencies:** Django TextChoices.
- **Behavior:** Direct mutation is currently unrestricted.

### Class: `Shipment(models.Model)`

- **Purpose:** Persist courier and tracking state.
- **Inputs:** One-to-one order and shipment fields.
- **Outputs:** Shipment row and `order.shipment` reverse accessor.
- **Dependencies:** Order.
- **Behavior:** Cascades with order; blank waybill and tracking values are allowed before booking.

#### Function: `Shipment.__str__(self)`

- **Purpose:** Return shipment summary text.
- **Inputs:** Shipment instance.
- **Outputs:** Order ID, courier, and waybill or `(no waybill)`.
- **Dependencies:** Stored fields.
- **Behavior:** No side effects.

## Domain Module: `apps/reviews/models.py`

- **Purpose:** Store moderated ratings with an order evidence reference.
- **Inputs:** Customer, product, order, 1-through-5 rating, body, moderation status.
- **Outputs:** Review row.
- **Dependencies:** Customer, Product, and protected Order.
- **Behavior:** Enforces rating range and one review per `(customer, product)`; verified-purchase business validation is not implemented.

### Class: `ReviewStatus(models.TextChoices)`

- **Purpose:** Define moderation states.
- **Inputs:** Review persistence/form validation.
- **Outputs:** `pending`, `approved`, and `rejected`.
- **Dependencies:** Django TextChoices.
- **Behavior:** Direct mutation is currently unrestricted.

### Class: `Review(models.Model)`

- **Purpose:** Persist review content, rating, moderation, and proof reference.
- **Inputs:** Customer, product, order, rating, body, status.
- **Outputs:** Timestamped review row.
- **Dependencies:** Accounts, catalog, and orders domains.
- **Behavior:** Orders newest first; validators and `chk_review_rating_1_to_5` enforce 1 through 5; `uniq_customer_review` prevents duplicate product reviews by one customer.

#### Function: `Review.__str__(self)`

- **Purpose:** Return review summary text.
- **Inputs:** Review instance.
- **Outputs:** Product ID, star rating, customer ID, and status.
- **Dependencies:** Stored fields.
- **Behavior:** No side effects.

## Command Module: `apps/catalog/management/commands/seed_demo.py`

- **Purpose:** Create deterministic local demo catalog and inventory.
- **Inputs:** `PRODUCT_SEEDS`, all Size values, all Fit values, and command invocation.
- **Outputs:** 5 categories, 5 products, 180 variants, 180 initial stock rows, and 180 initial restock movements on an empty database.
- **Dependencies:** Catalog models, inventory models, and one Django transaction.
- **Behavior:** Stable natural keys make reruns idempotent for row counts and inventory history; catalog metadata is refreshed.

### Constant: `PRODUCT_SEEDS`

- **Purpose:** Define five stable product/category/color/price records.
- **Inputs:** Seed command iteration.
- **Outputs:** Metro Essential Tee, Skyline Pullover Hoodie, Transit Utility Cargo Pants, Platform Twill Overshirt, and Night Route Windbreaker definitions.
- **Dependencies:** Integer-centavo pricing and deterministic slugs/codes.
- **Behavior:** Each product defines two product-specific colors.

### Constant: `FIT_SKU_CODES`

- **Purpose:** Map Fit values to stable SKU tokens.
- **Inputs:** `slim`, `regular`, or `oversized`.
- **Outputs:** `SLM`, `REG`, or `OVR`.
- **Dependencies:** Fit enum.
- **Behavior:** Keeps generated SKUs under the 64-character database limit.

### Class: `Command(BaseCommand)`

- **Purpose:** Register the `seed_demo` management command.
- **Inputs:** Django command discovery.
- **Outputs:** Command help and `handle()` execution.
- **Dependencies:** Django BaseCommand.
- **Behavior:** Declares no custom arguments.

#### Function: `Command.handle(self, *args, **options)`

- **Purpose:** Seed the complete variant matrix atomically.
- **Inputs:** Standard command arguments, currently unused.
- **Outputs:** `None` and a success line containing created counters.
- **Dependencies:** `update_or_create()`, `get_or_create()`, StockMovement creation, and `transaction.atomic()`.
- **Behavior:** Creates 6 sizes × 2 colors × 3 fits = 36 variants per product. Existing stock is never reset. Exactly one +10 restock movement is added only with a newly created stock row. Reruns reset seeded product `images=[]` and `is_active=True` by design.

## Migration Modules

### Module: `apps/catalog/migrations/0001_initial.py`

- **Purpose:** Bootstrap locked MySQL defaults and create Category, Product, and ProductVariant.
- **Inputs:** Active schema editor connection and empty/new database.
- **Outputs:** InnoDB/`utf8mb4_0900_ai_ci` defaults plus catalog tables and constraints.
- **Dependencies:** MySQL 8, permission to alter the active database, and Django migration recorder.
- **Behavior:** First planned project migration; reverse removes catalog schema but intentionally keeps the safer database defaults.

#### Function: `configure_mysql_defaults(apps, schema_editor)`

- **Purpose:** Enforce Hard Invariant 6 before domain tables are created.
- **Inputs:** Historical app registry and active schema editor.
- **Outputs:** Updated database defaults and normalized `django_migrations` table.
- **Dependencies:** MySQL vendor, `ALTER DATABASE` privilege, information_schema, and InnoDB.
- **Behavior:** Rejects non-MySQL backends; sets `utf8mb4_0900_ai_ci`; pins session InnoDB; converts the pre-created recorder table; verifies both defaults; raises `RuntimeError` on mismatch.

### Module: `apps/accounts/migrations/0001_initial.py`

- **Purpose:** Create the custom auth model and wishlist relation.
- **Inputs:** Catalog migration, Django auth migration 0012, and model state.
- **Outputs:** Customer, auth many-to-many join tables, and WishlistItem.
- **Dependencies:** `catalog.0001` and `auth.0012`.
- **Behavior:** Installs `CustomerManager` in migration state and unique wishlist constraint.

### Module: `apps/orders/migrations/0001_initial.py`

- **Purpose:** Create order, item, and annual sequence storage.
- **Inputs:** Catalog and swappable Customer migrations.
- **Outputs:** Orders tables plus total, quantity, uniqueness, year, and sequence constraints.
- **Dependencies:** `catalog.0001` and `AUTH_USER_MODEL`.
- **Behavior:** Establishes the schema used by payment, shipping, inventory, and review migrations.

### Module: `apps/inventory/migrations/0001_initial.py`

- **Purpose:** Create stock counters and audit movement tables.
- **Inputs:** Catalog variants and optional order references.
- **Outputs:** StockRecord and StockMovement tables with availability/sign constraints.
- **Dependencies:** `catalog.0001` and `orders.0001`.
- **Behavior:** Protects historical references and enforces one stock row per variant.

### Module: `apps/payments/migrations/0001_initial.py`

- **Purpose:** Create payment persistence.
- **Inputs:** Order migration.
- **Outputs:** One-to-one Payment table and unique nullable provider reference.
- **Dependencies:** `orders.0001`.
- **Behavior:** Amount uses MySQL unsigned INT centavos.

### Module: `apps/reviews/migrations/0001_initial.py`

- **Purpose:** Create review persistence and moderation fields.
- **Inputs:** Catalog, orders, and Customer migrations.
- **Outputs:** Review table with rating and customer/product uniqueness constraints.
- **Dependencies:** `catalog.0001`, `orders.0001`, and `AUTH_USER_MODEL`.
- **Behavior:** Protects evidence order and cascades customer/product content.

### Module: `apps/shipping/migrations/0001_initial.py`

- **Purpose:** Create shipment persistence.
- **Inputs:** Order migration.
- **Outputs:** One-to-one Shipment table.
- **Dependencies:** `orders.0001`.
- **Behavior:** Stores J&T-default courier and optional booking/tracking values.

## Data Relationship Map

- **Purpose:** Make ownership, cardinality, and deletion behavior explicit.
- **Inputs:** Model foreign-key and one-to-one declarations.
- **Outputs:** Relational dependency table.
- **Dependencies:** MySQL foreign keys.
- **Behavior:** Historical commerce references use `PROTECT` or `SET_NULL`; profile-owned/disposable records use cascade.

| Source | Target | Cardinality | Deletion behavior |
|---|---|---:|---|
| Product | Category | many-to-one | Category is protected. |
| ProductVariant | Product | many-to-one | Variant cascades with removable product. |
| StockRecord | ProductVariant | one-to-one | Counter cascades with removable variant. |
| StockMovement | ProductVariant | many-to-one | Variant is protected. |
| StockMovement | Order | optional many-to-one | Referenced order is protected. |
| Order | Customer | optional many-to-one | Customer deletion sets order customer null. |
| OrderItem | Order | many-to-one | Item cascades with order. |
| OrderItem | ProductVariant | many-to-one | Sold variant is protected. |
| Payment | Order | one-to-one | Payment cascades with order. |
| Shipment | Order | one-to-one | Shipment cascades with order. |
| WishlistItem | Customer | many-to-one | Wishlist row cascades. |
| WishlistItem | Product | many-to-one | Wishlist row cascades. |
| Review | Customer | many-to-one | Review cascades. |
| Review | Product | many-to-one | Review cascades. |
| Review | Order | many-to-one | Evidence order is protected. |

## Database Constraint Inventory

- **Purpose:** Enumerate persistence rules that survive ordinary ORM bypasses.
- **Inputs:** Model and migration constraint declarations.
- **Outputs:** Named MySQL checks, unique indexes, and foreign keys.
- **Dependencies:** MySQL 8 check-constraint enforcement.
- **Behavior:** Invalid writes raise database integrity errors.

| Domain | Constraint behavior |
|---|---|
| Catalog | Unique category name/slug, product slug, variant SKU, and variant axis tuple; nonnegative prices. |
| Accounts | Unique email and unique customer/product wishlist tuple. |
| Inventory | One stock row per variant; reserved not above on-hand; nonnegative counters; movement sign matches reason. |
| Orders | Unique order number; total reconciliation; quantity at least one; unique order/variant line; four-digit year; sequence at most 99,999. |
| Payments | One payment per order; globally unique non-null provider reference; nonnegative amount. |
| Reviews | Rating from 1 through 5; unique customer/product review tuple. |
| Shipping | One shipment per order. |

## Test Module: `tests/test_sanity.py`

- **Purpose:** Verify the A-1 scaffold contract.
- **Inputs:** Loaded Django test settings.
- **Outputs:** 3 passing assertions.
- **Dependencies:** pytest-django settings initialization.
- **Behavior:** Confirms settings import, MySQL/`utf8mb4`/InnoDB configuration, and all 10 installed apps.

## Test Module: `tests/test_models.py`

- **Purpose:** Verify A-2 schema, state guards, constraints, and seed idempotency on MySQL.
- **Inputs:** Real migrated MySQL test database and domain models.
- **Outputs:** 45 passing cases.
- **Dependencies:** pytest-django, MySQL information_schema, and `seed_demo`.
- **Behavior:** Covers table engine/collation, seven INT money fields, auth/guest semantics, order lifecycle and bypass resistance, total reconciliation, payment reference uniqueness, rating/quantity/movement checks, append-only ORM paths, and exact seed counts.

## Test Module: `tests/test_order_services.py`

- **Purpose:** Verify annual order-number correctness and locking.
- **Inputs:** Real MySQL transactions, two worker connections, year boundaries, and exhaustion state.
- **Outputs:** 7 passing cases.
- **Dependencies:** Thread pool, barrier, Django connection isolation, and `next_order_no()`.
- **Behavior:** Proves concurrent first allocations are unique/consecutive; rejects invalid years; preserves exhaustion boundary; verifies database constraints.

## Test Module: `tests/test_inventory.py`

- **Purpose:** Preserve the mandatory no-oversell red contract before B-1.
- **Inputs:** Two worker threads, two MySQL connections, one variant with one available unit.
- **Outputs:** One strict expected failure.
- **Dependencies:** Future `apps.inventory.services.reserve_stock` and `InsufficientStock`.
- **Behavior:** Marked `xfail(strict=True, raises=ImportError)`. B-1 must implement the API, remove the marker, and produce exactly one reservation and one insufficient-stock result.

## Quality Assurance

- **Purpose:** Record the successful post-implementation gate required before static analysis.
- **Inputs:** Settled source tree, Python virtual environment, Docker MySQL, migrations, and tests.
- **Outputs:** Verified pass/fail evidence.
- **Dependencies:** `.venv`, uv, Docker Compose, MySQL 8.4.10.
- **Behavior:** All blocking checks passed; one explicitly expected future-service contract remains XFAIL.

### QA Result Matrix

| Check | Command or method | Result |
|---|---|---|
| Ruff lint | `.venv/Scripts/ruff check .` | Passed; all checks passed. |
| Ruff format | `.venv/Scripts/ruff format --check .` | Passed; 48 files already formatted. |
| Django system check | `manage.py check --settings=config.settings.test` | Passed; 0 issues. |
| Migration drift | `manage.py makemigrations --check --dry-run` | Passed; no changes detected. |
| Applied migration state | `manage.py migrate --check --settings=config.settings.dev` | Passed; no pending migration. |
| Unit/integration tests | `.venv/Scripts/pytest -ra` | Passed; 55 passed, 1 strict XFAIL, 56 collected. |
| Dependency compatibility | `uv pip check --python .venv` | Passed; 16 packages compatible. |
| Compose validation | `docker compose config --quiet` | Passed. |
| Patch whitespace | `git diff --check` | Passed; only a Windows LF-to-CRLF advisory appeared. |
| Production settings | `manage.py check --deploy --settings=config.settings.prod` | Exit 0; only expected `security.W021` HSTS-preload warning. |
| Database metadata | information_schema queries | Passed; 0 non-InnoDB or non-`utf8mb4` tables. |
| Money column type | information_schema query | Passed; all 7 money columns are `int unsigned`. |

### Migration Execution Evidence

- **Purpose:** Validate migration correctness beyond a plan-only check.
- **Inputs:** Temporary database `metrodrip_migration_qa` initially created with Latin-1 defaults.
- **Outputs:** Successful forward, backward, and second forward migration.
- **Dependencies:** MySQL alter/create/drop privileges.
- **Behavior:** First migration converted the database to `utf8mb4_0900_ai_ci`; all tables were InnoDB; `migrate catalog zero` removed dependent project tables; reapplication succeeded; the temporary database was then dropped.

### Seed Execution Evidence

- **Purpose:** Validate exact data volume and rerun idempotency.
- **Inputs:** Clean migrated temporary QA database.
- **Outputs:** First run reported categories=5, products=5, variants=180, stock_records=180, stock_movements=180.
- **Dependencies:** `seed_demo` and A-2 migrations.
- **Behavior:** Second run reported zero created in every category; no stock or movement duplication occurred.

### Development Database State

- **Purpose:** Record local schema mutation performed during migration QA.
- **Inputs:** Confirmed-empty `metrodrip` Docker database.
- **Outputs:** Rebuilt schema using finalized initial migrations; no demo catalog loaded.
- **Dependencies:** Docker MySQL service.
- **Behavior:** The empty database was recreated after an earlier draft `0001` could not reverse newly amended constraints; finalized migrations then applied successfully.

## Hard Invariant Coverage

| Hard invariant | Current coverage | Remaining gap |
|---|---|---|
| No overselling | Database availability check and strict red concurrency contract. | No reserve/release/consume service or reservation TTL model; B-1 contract is not active-pass yet. |
| Integer centavos | All money fields are MySQL unsigned INT; tests reject BIGINT/float mapping. | A-3 formatting and arithmetic utilities are absent. |
| Webhook payment truth | Payment schema and unique provider reference only. | No signature verification, endpoint, replay log, or webhook-only Paid transition. |
| Append-only stock audit | Movement instance/queryset/bulk/conflict mutation guards and protected FKs. | StockRecord can still be directly mutated; raw SQL can bypass ORM guards; B-1 service is absent. |
| Enforced order state machine | Locked transition API and public ordinary ORM bypass guards. | Transition side effects and webhook-only Pending-to-Paid authority are absent; privileged raw SQL remains outside code guards. |
| InnoDB and utf8mb4 | First migration configures/verifies defaults; settings/server reinforce; metadata tests pass. | Production migration principal must retain required ALTER permission. |
| Card data never reaches server | No card-handling code exists. | Hosted PayMongo integration remains unimplemented. |

## Known Implementation Gaps

- **Purpose:** Prevent planned requirements from being mistaken for delivered behavior.
- **Inputs:** Handover build order compared with current source.
- **Outputs:** Explicit next-work boundary.
- **Dependencies:** Future epics.
- **Behavior:** Each listed capability is absent unless stated otherwise.

- A-3 money formatting/configuration utilities and tests are absent.
- A-4 staging deployment is absent.
- B-1 inventory mutation service, active concurrency pass, restock/adjustment service, and sale consumption are absent.
- B-2 reservation entity, 15-minute expiry, and release job are absent.
- Low-stock scheduler and email alerts are absent.
- Catalog admin registration, CRUD customization, and variant-matrix generator are absent.
- Storefront listing, filters, search, product detail, variant picker, and cart are absent.
- Checkout, zone fees, address autocomplete, payment initiation, and payment webhooks are absent.
- Payment amount is not yet reconciled against order total.
- Shipment adapter, booking, courier webhook, tracking surface, and manual admin waybill workflow are absent.
- Registration, login views, email verification, profile UI, password reset, saved-address UI, guest claiming, and order history are absent.
- Review verified-purchase validation, approved-only public query, and moderation admin are absent.
- Notifications, SMS, CMS, FAQ, contact form, invoice, packing slip, exports, 2FA, rate limits, and audit logs are absent.
- Caching, CDN/object storage configuration, production email provider, logging, monitoring, and staging configuration are absent.
- CI does not currently run Django system checks, migration drift/reversal, production checks, coverage thresholds, or security scanning.
- `Payment.status`, `Shipment.status`, and `Review.status` currently permit direct ORM mutation.
- The strict 2-buyer/1-unit test is a precursor; the M2 release gate still requires 20 parallel buyers for 10 units with exactly 10 successes.

## Next Strict Build Step

- **Purpose:** Identify the next task without expanding scope.
- **Inputs:** Handover dependency order and completed A-2 state.
- **Outputs:** Task sequence for continuation.
- **Dependencies:** User approval for future implementation.
- **Behavior:** Implement A-3 money utilities/configuration next, then A-4 staging deployment, then B-1 atomic inventory operations. B-1 must remove the strict XFAIL marker only after the existing race contract passes normally.

