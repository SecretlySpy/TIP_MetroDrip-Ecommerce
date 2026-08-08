# Module / File: Repository architecture, consolidated system specification, and delivery state

## Function: N/A — source-of-truth precedence hierarchy
- **Purpose**: Establish binding precedence across project documentation, eliminating conflicting claims.
- **Inputs**: Codebase, automated test suite execution results, `DECISIONS.md` (66 ADRs), `AI Documentation Notes.md`, `Tech Stack Setup Guide.md`, `README.md`, `index.html`.
- **Outputs**: Binding precedence hierarchy for AI agents and human developers.
- **Dependencies**: `AGENTS.md` engineering rules.
- **Behavior**: All documentation and system claims resolve in the following strict order:
  1. **Code + Verified Command Output**: Ground truth. Verifiable runtime behavior always wins.
  2. **`DECISIONS.md` (66 ADRs)**: Rationale for architectural decisions, trade-offs, and explicit reversals.
  3. **`AI Documentation Notes.md`**: Master system specification, consolidated handover state, entity model, FR/NFR traceability matrix, and module specifications.
  4. **`AGENTS.md` / `GEMINI.md`**: Autonomous engineering rules and operational protocols.
  5. **`Tech Stack Setup Guide.md` / `README.md` / `index.html`**: User-facing setup, quickstarts, and sitemaps.
- **Side Effects**: None.
- **Verification Status**: verified (audited against repo history).

## Function: N/A — consolidated product summary and hard invariants
- **Purpose**: Document product scope, locked tech stack, and non-negotiable commerce invariants.
- **Inputs**: B2C e-commerce requirements, PayMongo API specs, J&T API specs, PH Data Privacy Act (RA 10173).
- **Outputs**: System boundary and invariant rules.
- **Dependencies**: Python 3.14, Django 5.2, MySQL 8 (InnoDB, utf8mb4), DRF, HTMX 2.0, Alpine.js 3.14, React Native / Expo (TypeScript).
- **Behavior**:
  - **Product Summary**: MetroDrip is a B2C e-commerce + inventory system for a Metro Manila streetwear brand. Features server-rendered web storefront (HTMX/Alpine), dual admin consoles (`/admin/` and `/merchant/`), DRF public mobile API (`/api/mobile/v1/`), Expo mobile app, PayMongo payments, J&T shipping, and opt-in FastAPI strangler sidecars under `services/`.
  - **Hard Invariants (Non-Negotiable)**:
    1. *No overselling, ever*: `available = qty_on_hand − qty_reserved`. All stock mutations occur within `transaction.atomic()` with `select_for_update()`.
    2. *Money is integer centavos*: No floating-point numbers for money; `INT` columns used everywhere; display formatting only at view boundary.
    3. *Webhooks are payment truth*: Orders transition `Pending → Paid` ONLY via signature-verified PayMongo webhooks. Client redirects are never trusted. Webhook handlers are idempotent.
    4. *Append-only stock audit*: Every stock mutation creates a `StockMovement` row (delta, reason, ref_order_id); movements are never updated or deleted.
    5. *Order state machine enforced server-side*: `Pending → Paid → Packed → Shipped → Delivered` (plus `Cancelled` / `Refunded`). Illegal state transitions raise exceptions.
    6. *MySQL database standard*: InnoDB engine with `utf8mb4` charset enforced from the first migration.
    7. *PCI compliance*: Card details never touch MetroDrip servers; PayMongo hosted checkout/elements used exclusively.
    8. *Mobile app presentation boundary*: Mobile client performs zero price or stock calculations; server-validated pricing and availability are authoritative at checkout.
- **Side Effects**: Controls database transaction isolation, API payload processing, and payment confirmation.
- **Verification Status**: verified (560 pytest tests passing, including concurrency tests).

## Function: N/A — consolidated data model and taxonomy
- **Purpose**: Record authoritative entity schemas, two-level category tree, console roles, and curated collections.
- **Inputs**: Django ORM models (`apps/*/models.py`), database migrations, ADR-C-002, ADR-C-005, ADR-F-001.
- **Outputs**: Persisted database schema and model contracts.
- **Dependencies**: Django ORM, MySQL 8 InnoDB.
- **Behavior**:
  - **Entities**: Category, Product, ProductVariant, StockRecord, StockMovement, Order, OrderItem, Payment, Shipment, Customer, WishlistItem, Review, FlatPage, Banner, StockHold, OutboxMessage.
  - **Category Hierarchy**: Maximum 2 levels deep. Main categories (`parent = NULL`) have `Men` and `Women` child categories. Child slugs are parent-prefixed (`hoodies-men`). Depth (≤2) and sibling name uniqueness enforced in `Category.clean()`. Main category queries aggregate directly assigned products + all child products.
  - **Curated Collections**: Root categories ("New Arrivals", "Best-Sellers", "On-Sale", "Pre-Order") without gender subcategories; static discount pricing applied at creation.
  - **Dual Admin Consoles & Roles**: `Customer.role` enum (`customer`, `merchant`, `administrator`). `/admin/` (administrator console) manages customer accounts, roles, shipping fees, and audit trail; `/merchant/` (merchant console) manages catalog, variants, stock, orders, banners, flatpages, reviews, and support messages. Every model is registered on exactly one console site.
- **Side Effects**: Dictates DB schema, model validation, and route isolation.
- **Verification Status**: verified (`tests/test_catalog_hierarchy.py`, `tests/test_console_separation.py`).

## Function: N/A — full requirements & completion traceability matrix
- **Purpose**: Provide evidence-based traceability for every Web FR, Mobile FR, and NFR, mapping implementation files, automated test evidence, status (PASS/GAP), and gap notes.
- **Inputs**: Codebase inspection, pytest test suite execution (560 tests), ruff lint/format, mobile tsc/eslint checks.
- **Outputs**: Definitive matrix of system compliance.
- **Dependencies**: All Django apps, DRF mobile API, Expo mobile app, FastAPI sidecars.
- **Behavior**: Traceability matrix maps requirements as follows:

| ID | Requirement | Implementation Evidence | Test Evidence | Status | Gap / Verification Note |
|---|---|---|---|---|---|
| FR-1 | Catalog 3-axis variants (Size × Color × Fit) | `apps/catalog/models.py` (`ProductVariant`) | `tests/test_models.py` | PASS | SKU-level stock tracking verified |
| FR-2 | Storefront browse/filter/sort/search/detail | `apps/storefront/views.py` | `tests/test_storefront.py` | PASS | HTMX filtering & pagination verified |
| FR-3 | Cart (localStorage) + guest checkout | `templates/storefront/cart.html`, `apps/orders/checkout.py` | `tests/test_checkout_flow.py` | PASS | Client cart + guest order creation verified |
| FR-4 | PayMongo payments & webhook confirmation | `apps/payments/providers.py`, `apps/payments/views.py` | `tests/test_payments.py` | PASS | Signature verification & idempotency verified |
| FR-5 | Stock reservation hold (15-min) | `apps/orders/models.py` (`StockHold`), `jobs/scheduler.py` | `tests/test_stock_holds.py` | PASS | Auto-release on expiry verified |
| FR-6 | Order lifecycle state machine | `apps/orders/models.py` (`Order.status`) | `tests/test_order_services.py` | PASS | Illegal transition protection verified |
| FR-7 | J&T booking & admin waybill fallback | `apps/shipping/providers.py`, `apps/shipping/admin.py` | `tests/test_shipping.py` | PASS | Courier API + manual waybill fallback verified |
| FR-8 | Admin & Merchant dashboards | `config/consoles.py`, `config/admin.py` | `tests/test_admin.py` | PASS | Role-based dashboard separation verified |
| FR-9 | Low-stock SKU alerts | `apps/inventory/jobs.py`, `apps/notifications/services.py` | `tests/test_inventory.py` | PASS | Email alert dispatch verified |
| FR-10 | CSV sales & inventory exports | `apps/orders/admin.py`, `apps/inventory/admin.py` | `tests/test_admin.py` | PASS | UTF-8 CSV exports verified |
| FR-11 | Transactional confirmation & shipping email | `apps/notifications/services.py` | `tests/test_notifications.py` | PASS | Console/SMTP adapter verified |
| FR-12 | SMS alerts via Semaphore API | `apps/notifications/sms.py` | `tests/test_notifications.py` | PASS | Outbound SMS payload verified |
| FR-13 | Google Places autocomplete & zone derivation | `apps/shipping/zones.py` | `tests/test_shipping_zones.py` | PASS | NCR/Luzon/VisMin zone calculation verified |
| FR-14 | Customer registration, login, profile, reset | `apps/accounts/views.py`, `apps/accounts/models.py` | `tests/test_accounts.py` | PASS | Auth & address management verified |
| FR-15 | Order history & guest order claiming | `apps/orders/views.py`, `apps/mobile_api/views.py` | `tests/test_mobile_api.py` | PASS | Tokenized access & email claim verified |
| FR-16 | Wishlist management | `apps/catalog/models.py` (`WishlistItem`) | `tests/test_mobile_api.py` | PASS | Unique customer-product pairing verified |
| FR-17 | Verified-purchase reviews & moderation | `apps/reviews/models.py`, `apps/reviews/views.py` | `tests/test_reviews.py` | PASS | Moderation queue & rating math verified |
| FR-18 | Customer support contact form & FAQ | `apps/cms/views.py` | `tests/test_storefront_pages.py` | PASS | Message storage & email dispatch verified |
| FR-19 | Printable invoice & packing slip views | `apps/orders/views.py`, `apps/orders/admin.py` | `tests/test_orders.py` | PASS | Print-optimized HTML rendering verified |
| FR-20 | CMS flatpages & homepage promo banners | `apps/cms/models.py` | `tests/test_storefront_pages.py` | PASS | Active flag & banner display verified |
| FR-21 | Two-level category nav & header dropdown | `apps/catalog/services.py`, `templates/base.html` | `tests/test_catalog_hierarchy.py` | PASS | Active product counts & filter retention verified |
| FR-22 | Dual console separation (`/admin/` & `/merchant/`) | `config/consoles.py`, `apps/accounts/roles.py` | `tests/test_console_separation.py` | PASS | Routing isolation & 403 denial verified |
| Mobile FR-21 | Public JWT DRF API (`/api/mobile/v1/`) | `apps/mobile_api/urls.py` | `tests/test_mobile_api.py` | PASS | 24 endpoints verified |
| Mobile FR-22 | Auth parity & guest checkout | `mobile/src/store/AuthContext.tsx` | `tests/test_mobile_api.py` | PASS | JWT auth + refresh rotation verified |
| Mobile FR-23 | Opt-in biometric unlock | `mobile/src/store/AuthContext.tsx` | Code inspection | PASS | SecureStore key storage verified |
| Mobile FR-24 | Mobile catalog search/filter/sort | `mobile/src/screens/ShopScreen.tsx` | `mobile npm run typecheck` | PASS | Clean TypeScript compilation verified |
| Mobile FR-25 | Cart + server-validated checkout | `mobile/src/store/CartContext.tsx` | `tests/test_mobile_api.py` | PASS | Server prices authoritative at checkout |
| Mobile FR-26 | Mobile order history & tracking | `mobile/src/screens/OrderTrackingScreen.tsx` | `tests/test_mobile_api.py` | PASS | Live tracking status timeline verified |
| Mobile FR-27 | Push notifications on state changes | `mobile/src/hooks/usePushRegistration.ts` | `tests/test_push_lifecycle.py` | PASS | Device registration & push dispatch verified |
| Mobile FR-28 | In-app notification centre | `mobile/src/screens/NotificationsScreen.tsx` | `tests/test_mobile_api.py` | PASS | Read/unread state toggles verified |
| Mobile FR-29 | Mobile wishlist + OOS notifications | `mobile/src/screens/WishlistScreen.tsx` | Code inspection | PASS | Toggle & stock alert hook verified |
| Mobile FR-30 | Mobile offline degradation | `mobile/src/api/client.ts` | Code inspection | PASS | Cached catalog & offline banner verified |
| Mobile FR-31 | Dark mode (OS + manual override) | `mobile/src/theme/index.ts` | Code inspection | PASS | Tokenized light/dark themes verified |
| NFR-1 | Performance (LCP < 2.5s, catalog caching) | `apps/storefront/views.py` (`cache_page`) | System benchmark | PASS | Page caching applied to shop views |
| NFR-2 | Security (TOTP 2FA, rate limiting, HTTPS) | `config/settings/prod.py`, `apps/core/http.py` | `tests/test_staging_settings.py` | PASS | Strict host, origin, and secret rules verified |
| NFR-3 | Zero oversell invariant | `apps/inventory/services.py`, ORM atomic locks | `tests/test_checkout_concurrency.py` | PASS | 20 parallel buyers test passed |
| NFR-4 | PH Data Privacy Act compliance | Privacy Policy flatpage, `apps/accounts/models.py` | Code inspection | PASS | Minimal PII storage & explicit retention |
| NFR-5 | Infrastructure cost constraint (≤ $25/mo) | `deploy/docker-compose.prod.yml`, Caddy | Deployment spec | PASS | Single-host Docker stack specification |
| NFR-6 | Automated QA testability | `pyproject.toml`, pytest suite, ruff, CI | `python -m pytest` | PASS | 560 passing tests, 0 ruff lint errors |
| NFR-7 | Category navigation usability | `templates/components/navbar.html` | `tests/test_catalog_hierarchy.py` | PASS | Category tree rendering verified |
| NFR-8 | Category hierarchy depth restriction (≤2) | `apps/catalog/models.py` (`Category.clean`) | `tests/test_catalog_hierarchy.py` | PASS | Exception raised on depth > 2 |
| NFR-9 | Console routing isolation | `config/consoles.py` | `tests/test_console_separation.py` | PASS | Disjoint AdminSite registries verified |
| NFR-10 | Console permission & audit logging | `apps/core/admin.py` (`AdminAuditLog`) | `tests/test_console_separation.py` | PASS | Append-only admin audit log verified |

- **Known Minor Gap**:
  - *Mobile Tab Bar Labeling*: In `mobile/src/navigation/`, the navigation tab labeled "Orders" renders `NotificationsScreen`, resulting in an accessible label mismatch against screen title. Recorded as non-blocking minor UX gap for next mobile patch cycle.

- **Side Effects**: None.
- **Verification Status**: verified (560 pytest tests passing, `ruff check .` 0 errors, `mobile tsc` 0 errors, `mobile eslint` 0 errors).

## Function: N/A — delivery verification status & QA baseline
- **Purpose**: Record verified test, lint, and build execution results.
- **Inputs**: Automated test suite, static analysis tools, mobile TypeScript compiler.
- **Outputs**: `QA_PASSED`.
- **Dependencies**: Python 3.14.6, Pytest 8.4.2, Ruff 0.15.22, Django 5.2.16, Node 20+, Expo SDK 51.
- **Behavior**:
  - `python -m pytest`: **560 passed** (0 failed, 164 warnings).
  - `ruff check .`: **All checks passed** (0 errors).
  - `ruff format --check .`: **192 files formatted**.
  - `cd mobile && npm run typecheck`: **Clean** (`tsc --noEmit`, 0 errors).
  - `cd mobile && npm run lint`: **Clean** (`eslint`, 0 errors).
  - Responsive audit: 15 routes × 4 widths = **60/60 pass**.
- **Side Effects**: None.
- **Verification Status**: verified (executed on current codebase).

# Module / File: manage.py

## Function: main()
- **Purpose**: Initialize Django settings and dispatch a management command.
- **Inputs**:
  - `sys.argv` (`list[str]`): Command-line arguments supplied to Django.
  - `DJANGO_SETTINGS_MODULE` (`str | None`): Optional preselected settings module.
- **Outputs**: `None`; command output is written by Django.
- **Dependencies**: `os`, `sys`, and `django.core.management.execute_from_command_line`.
- **Behavior**: Defaults the settings module to `config.settings.dev`, raises a contextual ImportError when Django cannot import, and passes the original argument vector to Django.
- **Side Effects**: May set one process environment value and execute any selected Django command.

# Module / File: config/settings/base.py, dev.py, and test.py

## Function: N/A — shared settings contract
- **Purpose**: Define shared, development, and test runtime configuration.
- **Inputs**:
  - `.env` (`filesystem file, optional`): Local environment values.
  - `process environment` (`mapping[str, str]`): Database, provider, notification, and secret settings.
- **Outputs**: Django settings for 10 apps, middleware, templates, MySQL, authentication, currency, inventory jobs, providers, and static files.
- **Dependencies**: `python-dotenv`, PyMySQL, Django, MySQL 8, and WhiteNoise.
- **Behavior**: Base settings install PyMySQL as MySQLdb, select `django.db.backends.mysql`, request `utf8mb4`, set InnoDB/strict SQL mode for every connection, define PHP integer-centavo settings, register `accounts.Customer`, and keep preview/mock features disabled. Development enables debug, localhost, console email, and mock payments only when no PayMongo key exists. Tests retain real MySQL, switch to fast password hashing/in-memory email, and use DummyCache to prevent cached-page leakage.
- **Side Effects**: Loads `.env`, installs the PyMySQL compatibility hook, and configures global Django behavior during import.

# Module / File: config/settings/prod.py

## Function: _required_environment(name)
- **Purpose**: Read one mandatory non-empty deployment value.
- **Inputs**:
  - `name` (`str`): Environment-variable name.
- **Outputs**: `str` containing the stripped value.
- **Dependencies**: `os.environ` and `ImproperlyConfigured`.
- **Behavior**: Rejects missing, empty, and whitespace-only values before Django boots.
- **Side Effects**: Reads process environment; performs no write.

## Function: _required_csv_environment(name)
- **Purpose**: Parse one mandatory comma-separated environment list.
- **Inputs**:
  - `name` (`str`): Environment-variable name.
- **Outputs**: `list[str]` of stripped non-empty values.
- **Dependencies**: `_required_environment`.
- **Behavior**: Splits the required value, removes empty members, and rejects a list with no populated member.
- **Side Effects**: None.

## Function: _normalize_deployment_hostname(hostname)
- **Purpose**: Canonicalize a trusted deployment hostname and reject broadened trust syntax.
- **Inputs**:
  - `hostname` (`str`): Literal hostname candidate.
- **Outputs**: `str` containing lowercase DNS syntax, `localhost`, or `127.0.0.1`.
- **Dependencies**: `ipaddress`, `_HOST_LABEL_PATTERN`, and Python string validation.
- **Behavior**: Rejects public IP literals, wildcard/URL/internal single-label syntax, oversized names, invalid labels, and numeric-only top-level labels.
- **Side Effects**: None.

## Function: _required_hostnames_environment(name)
- **Purpose**: Parse Django’s required allowed-host list.
- **Inputs**:
  - `name` (`str`): Environment-variable name containing CSV hostnames.
- **Outputs**: `list[str]` of normalized literal hostnames.
- **Dependencies**: `_required_csv_environment`, `_normalize_deployment_hostname`, and `ImproperlyConfigured`.
- **Behavior**: Normalizes every member and converts validation failures to a setting-specific boot error.
- **Side Effects**: None.

## Function: _required_hostname_environment(name)
- **Purpose**: Read and validate one required literal deployment hostname.
- **Inputs**:
  - `name` (`str`): Environment-variable name.
- **Outputs**: `str` normalized hostname.
- **Dependencies**: `_required_environment`, `_normalize_deployment_hostname`, and `ImproperlyConfigured`.
- **Behavior**: Rejects invalid hostname syntax with a deployment-setting error.
- **Side Effects**: None.

## Function: _required_https_origins_environment(name)
- **Purpose**: Validate Django’s CSRF trusted-origin list.
- **Inputs**:
  - `name` (`str`): Environment-variable name containing CSV origins.
- **Outputs**: `list[str]` of exact HTTPS origins.
- **Dependencies**: `_required_csv_environment`, `_normalize_deployment_hostname`, and `urllib.parse.urlsplit`.
- **Behavior**: Rejects non-HTTPS schemes, credentials, invalid hostnames/ports, non-origin paths, queries, fragments, and netloc normalization mismatches.
- **Side Effects**: None.

## Function: _required_port_environment(name)
- **Purpose**: Validate one TCP port without changing Django’s expected string type.
- **Inputs**:
  - `name` (`str`): Environment-variable name.
- **Outputs**: `str` containing an ASCII decimal integer from 1 through 65535.
- **Dependencies**: `_required_environment`.
- **Behavior**: Rejects signs, Unicode digits, decimals, zero, and overflow.
- **Side Effects**: None.

## Function: _required_secret_environment(name)
- **Purpose**: Reject weak or example Django signing keys.
- **Inputs**:
  - `name` (`str`): Environment-variable name.
- **Outputs**: `str` containing a secret of at least 50 characters and five distinct characters.
- **Dependencies**: `_required_environment`.
- **Behavior**: Rejects short, low-diversity, `django-insecure-`, and `replace-with-` values without logging the secret.
- **Side Effects**: None.

## Function: _required_password_environment(name)
- **Purpose**: Reject weak or example application-database passwords.
- **Inputs**:
  - `name` (`str`): Environment-variable name.
- **Outputs**: `str` containing a password of at least 16 characters and five distinct characters.
- **Dependencies**: `_required_environment`.
- **Behavior**: Rejects short, low-diversity, and `replace-with-` values without logging the password.
- **Side Effects**: None.

# Module / File: config/settings/staging.py

## Function: _environment_flag(name, *, default=False)
- **Purpose**: Parse an explicit deployment Boolean without truthy-string ambiguity.
- **Inputs**:
  - `name` (`str`): Environment-variable name.
  - `default` (`bool`): Value used when the variable is absent.
- **Outputs**: `bool`.
- **Dependencies**: `os.environ` and `ImproperlyConfigured`.
- **Behavior**: Accepts only exact strings `0` and `1`; missing values use the supplied default.
- **Side Effects**: Reads process environment.

# Module / File: apps/catalog/seed_catalog.py

## Function: N/A - deterministic seed vocabulary
- **Purpose**: Hold the pure definitions shared by the catalog seeding commands so generated data is byte-identical across machines.
- **Inputs**:
  - `parent_slug` (`str`), `audience_suffix` (`str`), `sequence` (`int`), `index` (`int`): coordinates of one placeholder slot.
- **Outputs**: `AUDIENCES` tuple, colour/size/fit cycles, price-ladder constants, the naming helpers `category_code`, `mock_product_slug`, `mock_product_name`, `mock_sku`, `mock_price`, `mock_variant_axes`, and `allocate_round_robin`.
- **Dependencies**: `apps.catalog.models.Size`, `apps.catalog.models.Fit`.
- **Behavior**: Every function is a pure function of its arguments - no randomness, no clock, no database - which is what makes `seed_mock_catalog` safe to rerun. `allocate_round_robin(count, buckets)` returns per-bucket counts with the remainder given to the leading buckets, so 100 items over 18 buckets yields ten 6s followed by eight 5s.
- **Side Effects**: None.

# Module / File: apps/catalog/management/commands/seed_mock_catalog.py

## Function: Command.handle(self, *args, **options)
- **Purpose**: Bring the catalog's placeholder population up to `--count`, spread evenly across every audience subcategory.
- **Inputs**:
  - `--count` (`int`, default 100): how many `is_mock` products should exist. Counts placeholders only, not hand-authored products, so a database with 12 real products ends at 112.
  - `--dry-run` (`bool`): plan and report without writing.
- **Outputs**: `None`. Writes created/existing tallies for categories, products, variants, stock records, and movements to stdout.
- **Dependencies**: `Category`, `Product`, `ProductVariant`, `StockRecord`, `StockMovement`, `apps.catalog.seed_catalog`.
- **Behavior**: Aborts with an error when no main categories exist. Ensures every root has its audience children, builds a deterministic slot plan, then creates only the slots whose slug is absent. Warns - without deleting - when placeholders already exceed the target.
- **Side Effects**: Creates categories, products, variants, stock records, and stock movements. Never updates or deletes an existing row.

## Function: Command._ensure_audience_categories(self, dry_run)
- **Purpose**: Guarantee that each main category has its `Men` and `Women` children.
- **Inputs**:
  - `dry_run` (`bool`): when true, count what is missing without creating it.
- **Outputs**: `tuple[list, int]` - leaf slots ordered by root slug, and the number of children created.
- **Dependencies**: `Category`, `AUDIENCES`.
- **Behavior**: Re-establishes the invariant rather than trusting migration 0003, which back-fills only the categories present when it ran; a database migrated before being seeded has none, and roots added later would otherwise have no children. A dry run still emits the slot so the distribution can be planned and reported.
- **Side Effects**: Creates `Category` rows unless `dry_run`.

## Function: Command._build_plan(self, count, leaves)
- **Purpose**: Assign every placeholder slot to a leaf category deterministically.
- **Inputs**:
  - `count` (`int`): total placeholders wanted.
  - `leaves` (`list`): leaf slots from `_ensure_audience_categories`.
- **Outputs**: `list[dict]` with `root`, `audience`, `category`, `sequence`, and a monotonic `index`.
- **Dependencies**: `allocate_round_robin`.
- **Behavior**: Quotas come from round-robin allocation; sequence numbers restart at 1 per leaf so existing slugs stay stable when the target changes.
- **Side Effects**: None.

## Function: Command._create_product_graph(self, slug, slot, stats)
- **Purpose**: Create one placeholder together with the inventory rows that make it buyable.
- **Inputs**:
  - `slug` (`str`): natural key.
  - `slot` (`dict`): plan entry.
  - `stats` (`dict`): counters, mutated in place.
- **Outputs**: `None`.
- **Dependencies**: `Product`, `ProductVariant`, `StockRecord`, `StockMovement`, `MovementReason`.
- **Behavior**: Wrapped in `transaction.atomic`. A product without its variant, stock row, and opening ledger entry would be an unbuyable listing and a hole in the audit trail, so the graph commits all-or-nothing.
- **Side Effects**: Inserts one product, one variant, one stock record, and one restock movement.

## Function: Command._heal_product_graph(self, product, slot, stats)
- **Purpose**: Restore inventory rows that an existing placeholder is missing, without disturbing rows that survive.
- **Inputs**:
  - `product` (`Product`): an existing placeholder.
  - `slot` (`dict`): plan entry.
  - `stats` (`dict`): counters, mutated in place.
- **Outputs**: `None`.
- **Dependencies**: `ProductVariant`, `StockRecord`, `StockMovement`, `MovementReason`.
- **Behavior**: Strictly additive - an existing `StockRecord` is never read back or rewritten, so operational quantities, reservations, and thresholds survive untouched. An opening movement is posted only when the ledger is empty, because `StockMovement` is append-only: a duplicated opening balance could never be corrected and would leave the ledger permanently disagreeing with `qty_on_hand`. A healthy database never reaches this path; it exists for catalog tables that outlived their inventory tables.
- **Side Effects**: May insert a variant, a stock record, and a movement.

# Module / File: apps/catalog/context_processors.py

## Function: category_navigation(request)
- **Purpose**: Publish the category tree to every rendered template as `category_nav`.
- **Inputs**:
  - `request` (`HttpRequest`): unused; required by the context-processor contract.
- **Outputs**: `dict` with `category_nav` wrapped in `SimpleLazyObject`.
- **Dependencies**: `apps.catalog.services.get_category_tree`.
- **Behavior**: Laziness is load-bearing - without it every admin page, HTMX fragment, and error page would pay two catalog queries for navigation it never renders.
- **Side Effects**: None until a template dereferences the value.

# Module / File: config/admin.py

## Function: N/A — admin app configuration
- **Purpose**: Install `AdministratorSite` as the project's default admin site without editing any app's `admin.py`.
- **Inputs**:
  - `INSTALLED_APPS` (`list[str]`): Must list `config.admin.MetroDripAdminConfig` in place of `django.contrib.admin`.
- **Outputs**: `django.contrib.admin.site` resolves to `config.consoles.AdministratorSite`.
- **Dependencies**: `django.contrib.admin.apps.AdminConfig`.
- **Behavior**: `default_site` is a **dotted path string**, not an import. Django loads this module during `apps.populate()`, before models exist, so importing `config.consoles` here — which imports `apps.accounts.roles` — would raise `AppRegistryNotReady`. Django resolves the string in `AdminConfig.ready()`, after models are loaded. Because the administrator console *is* the default site, every existing `admin.site.register(...)` call and `admin.site.urls` binds to it unchanged, and the `admin:` URL namespace is preserved for Django's own templates.
- **Side Effects**: None at import time; autodiscovery runs during app registry population as before.
- **DSA Used**: None.
- **Data Analysis Notes**: None.
- **Responsive & Accessibility Notes**: None.
- **Security Notes**: Selecting the default site is what makes the administrator console the one reachable at `/admin/`; the access rules themselves live in `config/consoles.py`.

# Module / File: config/consoles.py

## Function: ConsoleSite.has_permission(self, request)
- **Purpose**: Decide whether a request may enter this console at all (ADR-F-001).
- **Inputs**:
  - `request` (`HttpRequest`): Any request routed through `AdminSite.admin_view`.
- **Outputs**: `bool` — True only for an active staff account whose role matches this console, or any superuser.
- **Dependencies**: `apps.accounts.roles.StaffRole`.
- **Behavior**: Returns False unless `user.is_active and user.is_staff`, then admits superusers unconditionally and otherwise requires `user.role == self.console_role`. Anonymous users fail on `is_active`, so the role lookup is never reached for them; `getattr` guards it regardless because `AnonymousUser` has no `role`.
- **Side Effects**: None.
- **DSA Used**: Constant-time attribute comparison; no queries.
- **Data Analysis Notes**: None.
- **Responsive & Accessibility Notes**: None.
- **Security Notes**: This is the server-side gate for every view on the console (NFR-10). It runs before any view body, so hidden or disabled interface controls are never the only protection. It is checked on *every* request, so revoking `is_active`, `is_staff`, or the role takes effect on the next request rather than at the next login.

## Function: ConsoleSite.login(self, request, extra_context=None)
- **Purpose**: Render this console's login page, or explain a wrong-console landing.
- **Inputs**:
  - `request` (`HttpRequest`): The incoming login GET or POST.
  - `extra_context` (`dict | None`): Additional template context supplied by a caller.
- **Outputs**: `HttpResponse` — the login form (200), a redirect once authenticated, or the wrong-console page (403).
- **Dependencies**: `django.contrib.admin.AdminSite.login`, `ConsoleSite.render_wrong_console`.
- **Behavior**: If the requester is already authenticated but fails `has_permission`, delegates to `render_wrong_console` instead of showing a form — they arrived here because `admin_view` bounced them, and their credentials were not wrong. Otherwise merges `site_header=self.login_heading` into `extra_context`. `AdminSite.login` applies `extra_context` after `each_context`, so the heading override wins for this view only; overriding `each_context` would also retitle logout and password-reset.
- **Side Effects**: None directly; `AdminSite.login` may create a session on success.
- **DSA Used**: None.
- **Data Analysis Notes**: None.
- **Responsive & Accessibility Notes**: Inherits Django's responsive `admin/login.html`.
- **Security Notes**: The heading is cosmetic. The actual per-console credential check is in `ConsoleAuthenticationForm.confirm_login_allowed`.

## Function: ConsoleSite.render_wrong_console(self, request)
- **Purpose**: Return a 403 page naming the console the signed-in user actually owns.
- **Inputs**:
  - `request` (`HttpRequest`): The refused request.
- **Outputs**: `HttpResponse` with status 403 rendering `admin/console_denied.html`.
- **Dependencies**: `Customer.console`, `CONSOLE_NAMESPACE`, `django.urls.reverse`.
- **Behavior**: Reads `request.user.console`; if it names a *different* console, reverses that console's index for a "Go to my console" link. Also passes this console's login URL so the page can offer a CSRF-protected account swap through the storefront logout — this console's own logout is unreachable from here, because `admin_view` bounces a permission-less request off it back to the index.
- **Side Effects**: None.
- **DSA Used**: Dictionary lookup on `CONSOLE_NAMESPACE`.
- **Data Analysis Notes**: None.
- **Responsive & Accessibility Notes**: The template is standalone with inlined CSS, honours `prefers-color-scheme`, keeps a visible `:focus-visible` outline on every action, and uses a single-column layout that is readable at 320 px. It deliberately does not extend `admin/base_site.html`, which builds a nav sidebar from `available_apps` the requester has no permission to enumerate.
- **Security Notes**: Discloses only which console the requester's *own* account belongs to — never what exists on the console being refused. Status is 403, not 200, so automated clients and logs record a refusal.

## Function: ConsoleAuthenticationForm.confirm_login_allowed(self, user)
- **Purpose**: Reject correct credentials belonging to the other console (ADR-F-001).
- **Inputs**:
  - `user` (`Customer`): The account that just authenticated.
- **Outputs**: `None` on success; raises `ValidationError` with code `wrong_console` otherwise.
- **Dependencies**: `django.contrib.admin.forms.AdminAuthenticationForm`.
- **Behavior**: Calls `super()` first (which checks `is_active` then `is_staff`), then admits superusers and accounts whose `role` equals `self.console_role`.
- **Side Effects**: None.
- **DSA Used**: None.
- **Data Analysis Notes**: None.
- **Responsive & Accessibility Notes**: The error renders in Django's standard admin form error region, which is announced by screen readers.
- **Security Notes**: Without this the separation would be a **redirect loop**, not a boundary: `AdminAuthenticationForm` checks only `is_staff`, which a merchant has, so `/admin/login/` would accept merchant credentials, redirect to the index, be refused by `has_permission`, and bounce back to the form indefinitely. The message names the console, never whether the account exists.

## Function: N/A — console registry ownership contract
- **Purpose**: Record which console owns which model, and why the split is structural.
- **Inputs**:
  - `admin.site._registry` (`dict[Model, ModelAdmin]`): Administrator console registry.
  - `merchant_site._registry` (`dict[Model, ModelAdmin]`): Merchant console registry.
- **Outputs**: Two disjoint sets of models; the intersection is asserted empty by `tests/test_console_separation.py`.
- **Dependencies**: Every app's `admin.py`.
- **Behavior**: Administrator console (`/admin/`, namespace `admin`) holds `accounts.Customer`, `accounts.WishlistItem`, `auth.Group`, `admin.LogEntry`, `shipping.ShippingZone`, and `sites.Site` — 6 models. Merchant console (`/merchant/`, namespace `merchant`) holds `catalog.Category`, `catalog.Product`, `inventory.StockRecord`, `inventory.StockMovement`, `inventory.Reservation`, `orders.Order`, `payments.Payment`, `shipping.Shipment`, `reviews.Review`, `cms.HomepageBanner`, `cms.ContactMessage`, and `flatpages.FlatPage` — 12 models. `apps.cms` unregisters `FlatPage` from the default site and re-registers it on the merchant console, relying on `django.contrib.flatpages` sorting before `apps.cms` in INSTALLED_APPS.
- **Side Effects**: None.
- **DSA Used**: Two hash maps keyed by model class; ownership lookup and the disjointness check are both O(1) per model.
- **Data Analysis Notes**: Shipping is the only domain that spans both consoles — `ShippingZone` (what customers are charged) is governance, `Shipment` (this parcel's waybill) is fulfilment.
- **Responsive & Accessibility Notes**: Each console renders Django's standard responsive admin theme.
- **Security Notes**: Because Django builds the admin index from the registry rather than from permissions, disjoint registries mean an administrator model's URL **does not exist** under `/merchant/` — guessing it returns 404, not 403. A single site with per-model permissions would still render empty headings for the other role's models.

# Module / File: apps/accounts/roles.py

## Function: N/A — back-office role vocabulary
- **Purpose**: Define the console roles in a module that imports no models.
- **Inputs**: None.
- **Outputs**: `StaffRole` (`TextChoices`: `customer`, `merchant`, `administrator`) and `CONSOLE_ROLES` (`frozenset`).
- **Dependencies**: `django.db.models.TextChoices`.
- **Behavior**: Exists as a separate module because `config.consoles` needs these values while the admin app is still starting; importing `apps.accounts.models` at that point would raise `AppRegistryNotReady`. A `TextChoices` subclass registers nothing with the app registry, so this module is safe to import at any point. `apps.accounts.models` re-exports both names.
- **Side Effects**: None.
- **DSA Used**: `frozenset` membership test for `CONSOLE_ROLES`, O(1).
- **Data Analysis Notes**: Roles are mutually exclusive; there is no multi-role account. A superuser is modelled as a flag on top of a role, not as a fourth role.
- **Responsive & Accessibility Notes**: None.
- **Security Notes**: `is_staff` answers "may this account reach a console at all"; `role` answers "which one". Both are required, so clearing `is_staff` revokes access without having to rewrite the role.

# Module / File: config/views.py

## Function: liveness(request)
- **Purpose**: Report that the Django process can route an HTTP request.
- **Inputs**:
  - `request` (`HttpRequest`): GET request.
- **Outputs**: `JsonResponse` with HTTP 200 and `{"status": "ok"}`.
- **Dependencies**: Django `JsonResponse` and `require_GET`.
- **Behavior**: Performs no database access so an external database outage does not trigger a process-restart loop.
- **Side Effects**: None.

## Function: readiness(request)
- **Purpose**: Report whether Django can execute a minimal database query.
- **Inputs**:
  - `request` (`HttpRequest`): GET request.
- **Outputs**: `JsonResponse` with HTTP 200 `ok` or HTTP 503 `unavailable`.
- **Dependencies**: Django database connection, `DatabaseError`, and application logger.
- **Behavior**: Executes `SELECT 1`; database errors are logged while the HTTP body hides credentials and driver details.
- **Side Effects**: Opens/uses a database connection and may write a warning log.

# Module / File: apps/accounts/models.py

## Function: CustomerManager._create(self, email, password, **extra_fields)
- **Purpose**: Implement the shared persistence path for customers and administrators.
- **Inputs**:
  - `self` (`CustomerManager`): Bound model manager.
  - `email` (`str`): Required login identity.
  - `password` (`str | None`): Plain password or `None` for Django’s unusable marker.
  - `extra_fields` (`dict[str, object]`): Additional Customer fields.
- **Outputs**: Persisted `Customer`.
- **Dependencies**: Django email normalization, password hashing, unusable-password support, and manager database alias.
- **Behavior**: Rejects an empty email, normalizes it, hashes or disables the password, and saves through the selected database.
- **Side Effects**: Inserts one customer row.

## Function: CustomerManager.create_user(self, email, password=None, **extra_fields)
- **Purpose**: Create a normal non-staff customer by default.
- **Inputs**:
  - `self` (`CustomerManager`): Bound manager.
  - `email` (`str`): Customer email.
  - `password` (`str | None`): Optional password.
  - `extra_fields` (`dict[str, object]`): Optional profile/flag overrides.
- **Outputs**: Persisted `Customer`.
- **Dependencies**: `CustomerManager._create`.
- **Behavior**: Defaults `is_staff` and `is_superuser` to false, then delegates creation.
- **Side Effects**: Inserts one customer row.

## Function: CustomerManager.create_superuser(self, email, password, **extra_fields)
- **Purpose**: Create a privileged Django administrator.
- **Inputs**:
  - `self` (`CustomerManager`): Bound manager.
  - `email` (`str`): Administrator email.
  - `password` (`str`): Required non-empty password.
  - `extra_fields` (`dict[str, object]`): Optional model values.
- **Outputs**: Persisted privileged `Customer`.
- **Dependencies**: `CustomerManager._create`, `StaffRole`.
- **Behavior**: Defaults both privilege flags true, defaults `role` to `ADMINISTRATOR`, and rejects missing passwords or false privilege overrides.
- **Side Effects**: Inserts one customer row.
- **Security Notes**: The role default is descriptive, not restrictive — a superuser reaches both consoles regardless. It exists so the project's most privileged login is not labelled "Customer" in the account list. Scoped, non-superuser console accounts are created with `create_console_account` instead.

## Function: CustomerManager.merchants(self) / CustomerManager.administrators(self)
- **Purpose**: Query the accounts that can currently reach each console.
- **Inputs**:
  - `self` (`CustomerManager`): Bound manager.
- **Outputs**: `QuerySet[Customer]`.
- **Dependencies**: `django.db.models.Q`, `StaffRole`.
- **Behavior**: Filters `is_active=True, is_staff=True` then ORs `is_superuser=True` with the matching `role`. Mirrors the `Customer.console` property in SQL so a set of accounts can be selected without loading every row.
- **Side Effects**: None.
- **DSA Used**: Indexed equality on `role` (`db_index=True`) plus two boolean columns; the OR branch is a small scan on the already-narrowed staff set.
- **Data Analysis Notes**: Staff are a tiny fraction of `accounts_customer`, so the two boolean predicates do the real selectivity work and the `role` index mainly keeps the plan stable as staff counts grow.

## Function: Customer.clean(self)
- **Purpose**: Reject a console role that staff status would silently neutralise.
- **Inputs**:
  - `self` (`Customer`): The instance being validated.
- **Outputs**: `None`; raises `ValidationError` keyed on `is_staff`.
- **Dependencies**: `CONSOLE_ROLES`.
- **Behavior**: Raises when `role` is a console role and `is_staff` is False. Like `Category.clean`, this runs through ModelForms — so the administrator console cannot save the contradiction — but not through bulk seeds, which are trusted.
- **Side Effects**: None.
- **DSA Used**: `frozenset` membership, O(1).
- **Data Analysis Notes**: None.
- **Responsive & Accessibility Notes**: Surfaces as a field-level error on `is_staff` in the admin form, which Django associates with the input for screen readers.
- **Security Notes**: This is a usability guard, not the boundary. `ConsoleSite.has_permission` is the enforcement point; `clean` only stops an operator creating an account that *looks* privileged and is not.

## Function: Customer.console (property)
- **Purpose**: Report the one console this account may enter right now, or None.
- **Inputs**:
  - `self` (`Customer`): The account.
- **Outputs**: `StaffRole.ADMINISTRATOR`, `StaffRole.MERCHANT`, or `None`.
- **Dependencies**: `CONSOLE_ROLES`, `StaffRole`.
- **Behavior**: Returns None unless active and staff; superusers answer `ADMINISTRATOR` because that console owns account and role management, and `has_permission` waves them into the merchant console separately rather than forcing a second login. Otherwise returns `role` when it is a console role.
- **Side Effects**: None.
- **DSA Used**: `frozenset` membership, O(1); no queries.
- **Data Analysis Notes**: `role` alone is misleading — an inactive or non-staff account with the Administrator role opens nothing. This property is the effective answer and is what both the navbar and the denial page read.
- **Responsive & Accessibility Notes**: Drives the staff console shortcut in `templates/base.html`, which is rendered only for accounts that have a console.
- **Security Notes**: Convenience only. Every console request is re-checked server-side, so removing the navbar link would change nothing about who can get in.

## Function: Customer.is_merchant / Customer.is_administrator (properties)
- **Purpose**: Boolean predicates for "may enter the merchant / administrator console".
- **Inputs**:
  - `self` (`Customer`): The account.
- **Outputs**: `bool`.
- **Dependencies**: `StaffRole`.
- **Behavior**: Active AND staff AND (superuser OR the matching role). Both return True for a superuser, which is correct: superusers are admitted to both consoles.
- **Side Effects**: None.
- **Security Notes**: These mirror `ConsoleSite.has_permission` for use in templates and services. They are not a substitute for it — the site's own check is the one that runs before a view executes.

## Function: Customer.__str__(self)
- **Purpose**: Return the customer’s display identity.
- **Inputs**:
  - `self` (`Customer`): Customer instance.
- **Outputs**: `str` email address.
- **Dependencies**: `Customer.email`.
- **Behavior**: Returns the stored email.
- **Side Effects**: None.

## Function: WishlistItem.__str__(self)
- **Purpose**: Return readable wishlist relationship text.
- **Inputs**:
  - `self` (`WishlistItem`): Wishlist row.
- **Outputs**: `str` containing customer and product display values.
- **Dependencies**: Related Customer and Product string conversion.
- **Behavior**: Joins the two related displays with a heart symbol.
- **Side Effects**: May lazily read related rows; performs no write.

# Module / File: apps/accounts/views.py

## Function: _safe_next_url(request)
- **Purpose**: Prevent open redirects after authentication.
- **Inputs**:
  - `request` (`HttpRequest`): Request containing optional POST/GET `next`.
- **Outputs**: `str | None` validated same-host target.
- **Dependencies**: `url_has_allowed_host_and_scheme`.
- **Behavior**: Uses POST before GET, restricts the target to the request host, and requires HTTPS when the current request is secure.
- **Side Effects**: None.

## Function: register_view(request)
- **Purpose**: Register and authenticate a customer.
- **Inputs**:
  - `request` (`HttpRequest`): GET or registration form POST.
- **Outputs**: Registration HTML, validation HTML, or redirect to profile.
- **Dependencies**: Customer manager, Django login, Order, messages, and templates.
- **Behavior**: Redirects authenticated users, normalizes submitted email, requires email/password/name, rejects duplicate email, creates/logs in the customer, and attaches guest orders whose JSON email exactly matches.
- **Side Effects**: Inserts a Customer, creates a session, may attach multiple Orders, and may enqueue a success message.

## Function: login_view(request)
- **Purpose**: Authenticate an email/password customer safely.
- **Inputs**:
  - `request` (`HttpRequest`): GET or login form POST.
- **Outputs**: Login HTML or a safe redirect.
- **Dependencies**: Django `authenticate`, `login`, `_safe_next_url`, and template rendering.
- **Behavior**: Normalizes email, authenticates credentials, uses a validated `next` target when present, and returns a generic invalid-credential error otherwise.
- **Side Effects**: May create/update an authenticated session.

## Function: logout_view(request)
- **Purpose**: End the current authenticated session, returning to a validated `next` when supplied.
- **Inputs**:
  - `request` (`HttpRequest`): POST request; may carry `next`.
- **Outputs**: Redirect to `next` when safe, otherwise storefront home.
- **Dependencies**: Django `logout`, `_safe_next_url`.
- **Behavior**: Clears the current session identity, then redirects to `_safe_next_url(request)` or `storefront:home`. The `next` hop exists for the console-denied page: a staff member on the wrong console needs to swap accounts and return to *that* console's login rather than being dropped on the storefront.
- **Side Effects**: Mutates/deletes session authentication data.
- **DSA Used**: None.
- **Data Analysis Notes**: None.
- **Responsive & Accessibility Notes**: Reached only from POST forms (`accounts/profile.html`, `admin/console_denied.html`), each a real submit button.
- **Security Notes**: `next` is validated by `_safe_next_url`, which rejects any off-host target, so this cannot become an open redirect. Logout stays POST-only in practice, so a crafted `<img>` on a third-party page cannot force it.

## Function: profile_view(request)
- **Purpose**: Render a customer dashboard and update basic profile fields.
- **Inputs**:
  - `request` (`HttpRequest`): Authenticated GET or POST.
- **Outputs**: Profile HTML or post-update redirect.
- **Dependencies**: Customer, Order, WishlistItem, messages, and `login_required`.
- **Behavior**: POST trims name/phone, rejects an empty name, persists approved fields, and redirects. GET loads five recent orders plus product/category-aware wishlist rows.
- **Side Effects**: POST may update Customer and messages; GET performs reads only.

## Function: order_history(request)
- **Purpose**: Display every order belonging to the authenticated customer.
- **Inputs**:
  - `request` (`HttpRequest`): Authenticated request.
- **Outputs**: Order-history HTML.
- **Dependencies**: Order ORM, template rendering, and `login_required`.
- **Behavior**: Queries customer-owned orders newest first.
- **Side Effects**: Database reads only.

## Function: claim_guest_order(request)
- **Purpose**: Attach an unclaimed guest order when its snapshot email matches the logged-in account.
- **Inputs**:
  - `request` (`HttpRequest`): Authenticated POST containing `order_no`.
- **Outputs**: Redirect to order history with a non-enumerating message.
- **Dependencies**: Order ORM, Customer session, Django messages, and `require_POST`.
- **Behavior**: Looks up only unclaimed orders, compares lowercase emails, attaches exact matches, and uses the same failure message for nonexistent and mismatched orders.
- **Side Effects**: May update one Order customer foreign key and write a message.

## Function: toggle_wishlist(request)
- **Purpose**: Toggle a product bookmark for the authenticated customer.
- **Inputs**:
  - `request` (`HttpRequest`): POST JSON containing `product_id`.
- **Outputs**: `JsonResponse` with `{success, added}` or HTTP 400 error.
- **Dependencies**: JSON parser, Product, WishlistItem, `login_required`, and `require_POST`.
- **Behavior**: Treats malformed JSON and unknown IDs identically, creates a missing bookmark, or deletes an existing one.
- **Side Effects**: Inserts or deletes one WishlistItem.

# Module / File: apps/catalog/models.py

## Function: Category.clean(self)
- **Purpose**: Reject self-parenting, third-level nesting, and duplicate sibling names before a category is saved through a form.
- **Inputs**:
  - `self` (`Category`): The instance being validated, with `parent_id` and `name` already assigned.
- **Outputs**: `None` on success; raises `ValidationError` keyed by field otherwise.
- **Dependencies**: `Category` table (sibling lookup), `django.core.exceptions.ValidationError`.
- **Behavior**: When a parent is set, rejects the instance as its own parent, rejects a parent that itself has a parent (depth cap of `Category.MAX_DEPTH` = 2), and rejects demoting a category that already has children. Then rejects any existing sibling sharing the same name under the same parent, excluding itself on update. Errors accumulate and raise together. Django calls this from ModelForm validation, so the admin is covered; bare `Model.save()` does not invoke it.
- **Side Effects**: None. Read-only; performs at most one sibling query.

## Function: Category.is_root(self)
- **Purpose**: Report whether the category sits at the top of the taxonomy.
- **Inputs**: none beyond `self`.
- **Outputs**: `bool` - `True` when `parent_id` is `None`.
- **Dependencies**: none.
- **Behavior**: Reads `parent_id` without dereferencing the relation, so it never triggers a query.
- **Side Effects**: None.

## Function: Category.hierarchy_label(self)
- **Purpose**: Render the category's position for admin lists and debugging.
- **Inputs**: none beyond `self`.
- **Outputs**: `str` - the name for a root, `"Parent -> Child"` otherwise.
- **Dependencies**: `Category.parent`.
- **Behavior**: Dereferences `parent` for non-roots, so callers listing many rows should `select_related("parent")`. `CategoryAdmin.get_queryset` does exactly that.
- **Side Effects**: None.

## Function: Category.__str__(self)
- **Purpose**: Return category display text.
- **Inputs**:
  - `self` (`Category`): Category row.
- **Outputs**: `str` category name.
- **Dependencies**: `Category.name`.
- **Behavior**: Returns the stored name.
- **Side Effects**: None.

## Function: Product.__str__(self)
- **Purpose**: Return product display text.
- **Inputs**:
  - `self` (`Product`): Product row.
- **Outputs**: `str` product name.
- **Dependencies**: `Product.name`.
- **Behavior**: Returns the stored name.
- **Side Effects**: None.

## Function: ProductVariant.__str__(self)
- **Purpose**: Return variant display text.
- **Inputs**:
  - `self` (`ProductVariant`): Variant row.
- **Outputs**: `str` SKU.
- **Dependencies**: `ProductVariant.sku`.
- **Behavior**: Returns the globally unique SKU.
- **Side Effects**: None.

## Function: ProductVariant.price(self)
- **Purpose**: Resolve the authoritative unit price in integer centavos.
- **Inputs**:
  - `self` (`ProductVariant`): Variant with related Product.
- **Outputs**: `int` variant override or product base price.
- **Dependencies**: `price_override` and `product.base_price`.
- **Behavior**: Uses the override only when non-null; zero is not mistaken for null.
- **Side Effects**: May lazily read the Product; performs no write.

# Module / File: apps/catalog/services.py

## Function: get_catalog_queryset(*, filters=None, sort=None, search=None)
- **Purpose**: Build the active-product listing query with annotations, filters, search, and sorting.
- **Inputs**:
  - `filters` (`dict[str, str] | None`): Category, size, color, fit, and min/max price values.
  - `sort` (`str | None`): Supported catalog sort key.
  - `search` (`str | None`): Free-text product/description/SKU search.
- **Outputs**: `QuerySet[Product]` with price, variant, review, and popularity annotations.
- **Dependencies**: Product, ReviewStatus, Django `Q`, `Avg`, `Count`, `Min`, and `Max`.
- **Behavior**: Restricts to active products, filters variant axes conjunctively, ignores malformed optional integer price filters, searches multiple fields, deduplicates joins, and defaults unknown sorts to newest.
- **Side Effects**: None until queryset evaluation; evaluation performs database reads.

## Function: get_category_tree()
- **Purpose**: Return main categories with their children and active-product counts, for the global menu and the shop filter tree.
- **Inputs**: none.
- **Outputs**: `list[Category]` - roots ordered by name, each carrying `child_categories` (children ordered by name, annotated with `product_count`), its own `product_count` for directly assigned products, and `total_product_count` for the whole branch.
- **Dependencies**: `Category`, `Product`.
- **Behavior**: Exactly two queries regardless of taxonomy size - one for roots, one for the prefetched children - so templates can render counts without touching the database. `total_product_count` is summed in Python from already-prefetched rows; a database-side rollup would need a third query or a correlated subquery per root.
- **Side Effects**: None.

## Function: get_all_categories()
- **Purpose**: Return categories with active-product counts.
- **Inputs**:
  - `None` (`None`): No explicit parameters.
- **Outputs**: `QuerySet[Category]`.
- **Dependencies**: Category ORM, Count, and Q.
- **Behavior**: Annotates each category and orders names alphabetically.
- **Side Effects**: Database reads on evaluation.

## Function: get_available_colors()
- **Purpose**: Return the distinct color filter options used by active products.
- **Inputs**:
  - `None` (`None`): No explicit parameters.
- **Outputs**: `list[str]` sorted color values.
- **Dependencies**: ProductVariant ORM.
- **Behavior**: Filters through active parent products, selects distinct colors, orders them, and materializes the query.
- **Side Effects**: Performs one database read.

## Function: get_product_detail(slug)
- **Purpose**: Load an active product with category, stock-aware variants, and approved reviews.
- **Inputs**:
  - `slug` (`str`): Unique product slug.
- **Outputs**: `Product | None`.
- **Dependencies**: Product, ReviewStatus, StockRecord relations, review/customer relations, annotations, and Prefetch.
- **Behavior**: Annotates approved-review statistics, orders variants, attaches approved reviews to `approved_reviews`, and returns None for inactive/missing products.
- **Side Effects**: Performs database reads only.

# Module / File: apps/catalog/admin.py

## Function: ProductAdmin.generate_variant_matrix(self, request, queryset)
- **Purpose**: Create missing Size × Color × Fit variants for selected products.
- **Inputs**:
  - `self` (`ProductAdmin`): Bound admin instance.
  - `request` (`HttpRequest`): Staff admin request.
  - `queryset` (`QuerySet[Product]`): Selected products.
- **Outputs**: `None`; emits an admin message with the created count.
- **Dependencies**: ProductVariant, Size, Fit, transaction savepoints, and IntegrityError.
- **Behavior**: Uses existing product colors or `Default`, generates every supported size/fit combination, derives a deterministic-looking SKU prefix, skips existing axes, and currently suppresses cross-product SKU collisions.
- **Side Effects**: Inserts ProductVariant rows and writes an admin message; it does not create StockRecord or StockMovement rows.

# Module / File: apps/catalog/management/commands/seed_demo.py

## Function: Command.handle(self, *args, **options)
- **Purpose**: Seed a deterministic, idempotent five-product demo catalog and operating data.
- **Inputs**:
  - `self` (`Command`): Django command instance.
  - `args` (`tuple[object, ...]`): Unused positional command arguments.
  - `options` (`dict[str, object]`): Django command options.
- **Outputs**: `None`; writes a compact created-count summary.
- **Dependencies**: Category, Product, ProductVariant, StockRecord, StockMovement, ShippingZone, FlatPage, Site, HomepageBanner, settings, and transaction.
- **Behavior**: Upserts five stable products/categories, creates 180 deterministic variants, creates stock only when absent, writes one matching +10 restock movement per new stock row, creates three zones/flatpages/banner, preserves live stock on rerun, and wraps all writes in one transaction.
- **Side Effects**: Inserts/updates catalog and CMS data, inserts create-only inventory/ledger data, attaches flatpages to the configured Site, and writes command output.

# Module / File: apps/catalog/migrations/0001_initial.py

## Function: configure_mysql_defaults(apps, schema_editor)
- **Purpose**: Enforce MySQL/InnoDB/Unicode defaults before fresh domain tables are created.
- **Inputs**:
  - `apps` (`StateApps`): Historical app registry; not read.
  - `schema_editor` (`BaseDatabaseSchemaEditor`): Active migration connection.
- **Outputs**: `None`; raises RuntimeError when the invariant cannot be established.
- **Dependencies**: MySQL 8 metadata, quoted identifiers, `django_migrations`, and DDL privileges.
- **Behavior**: Rejects non-MySQL backends, alters database defaults to `utf8mb4_0900_ai_ci`, pins session InnoDB, normalizes the migration-recorder table, and verifies database/session values.
- **Side Effects**: Executes MySQL DDL and session statements.

# Module / File: apps/catalog/migrations/0002_enforce_mysql_defaults.py

## Function: enforce_mysql_defaults(apps, schema_editor)
- **Purpose**: Repair existing installations affected while the initial invariant operation was historically disabled.
- **Inputs**:
  - `apps` (`StateApps`): Historical app registry; not read.
  - `schema_editor` (`BaseDatabaseSchemaEditor`): Active migration connection.
- **Outputs**: `None`; raises RuntimeError with remaining table violations.
- **Dependencies**: MySQL 8 information_schema, identifier quoting, and DDL privileges.
- **Behavior**: Rejects non-MySQL backends, repairs database defaults, pins the session engine, finds only noncompliant base tables, converts each to InnoDB/`utf8mb4_0900_ai_ci`, and verifies defaults, engine, and every table afterward. The migration is non-atomic because MySQL commits DDL implicitly and uses a no-op reverse.
- **Side Effects**: May rebuild noncompliant MySQL tables and changes database/session defaults.

# Module / File: apps/cms/models.py

## Function: HomepageBanner.__str__(self)
- **Purpose**: Return the CMS banner title for admin/display use.
- **Inputs**:
  - `self` (`HomepageBanner`): Banner row.
- **Outputs**: `str` title.
- **Dependencies**: `HomepageBanner.title`.
- **Behavior**: Returns the stored title.
- **Side Effects**: None.

## Function: ContactMessage.__str__(self)
- **Purpose**: Return readable contact-message attribution.
- **Inputs**:
  - `self` (`ContactMessage`): Stored inquiry.
- **Outputs**: `str` containing sender name and email.
- **Dependencies**: ContactMessage fields.
- **Behavior**: Formats the sender identity.
- **Side Effects**: None.

# Module / File: apps/inventory/models.py

## Function: StockRecord.available(self)
- **Purpose**: Calculate sellable stock from physical and reserved counters.
- **Inputs**:
  - `self` (`StockRecord`): Stock row.
- **Outputs**: `int` equal to `qty_on_hand - qty_reserved`.
- **Dependencies**: Database check `chk_reserved_lte_on_hand`.
- **Behavior**: Subtracts reserved units without writing state.
- **Side Effects**: None.

## Function: AppendOnlyMovementQuerySet.update(self, **kwargs)
- **Purpose**: Block bulk updates to inventory audit history.
- **Inputs**:
  - `self` (`AppendOnlyMovementQuerySet`): Movement queryset.
  - `kwargs` (`dict[str, object]`): Requested fields.
- **Outputs**: Never returns normally; raises TypeError.
- **Dependencies**: None.
- **Behavior**: Rejects every QuerySet update.
- **Side Effects**: None.

## Function: AppendOnlyMovementQuerySet.bulk_update(self, objs, fields, batch_size=None)
- **Purpose**: Block bulk object rewrites of inventory audit history.
- **Inputs**:
  - `self` (`AppendOnlyMovementQuerySet`): Movement queryset.
  - `objs` (`Iterable[StockMovement]`): Requested rows.
  - `fields` (`Iterable[str]`): Requested fields.
  - `batch_size` (`int | None`): Requested batch size.
- **Outputs**: Never returns normally; raises TypeError.
- **Dependencies**: None.
- **Behavior**: Rejects every bulk update.
- **Side Effects**: None.

## Function: AppendOnlyMovementQuerySet.delete(self)
- **Purpose**: Block queryset deletion of inventory audit history.
- **Inputs**:
  - `self` (`AppendOnlyMovementQuerySet`): Movement queryset.
- **Outputs**: Never returns normally; raises TypeError.
- **Dependencies**: None.
- **Behavior**: Rejects deletion.
- **Side Effects**: None.

## Function: AppendOnlyMovementQuerySet.bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False, update_fields=None, unique_fields=None)
- **Purpose**: Permit append-only bulk inserts while rejecting conflict-update rewrites.
- **Inputs**:
  - `self` (`AppendOnlyMovementQuerySet`): Movement queryset.
  - `objs` (`Iterable[StockMovement]`): New ledger rows.
  - `batch_size` (`int | None`): Optional batch size.
  - `ignore_conflicts` (`bool`): Django insert option.
  - `update_conflicts` (`bool`): Forbidden rewrite option.
  - `update_fields` (`Iterable[str] | None`): Conflict-update fields.
  - `unique_fields` (`Iterable[str] | None`): Conflict target fields.
- **Outputs**: `list[StockMovement]` for plain inserts.
- **Dependencies**: Django QuerySet bulk creation.
- **Behavior**: Raises TypeError when `update_conflicts` is true; otherwise delegates the append.
- **Side Effects**: May insert multiple immutable ledger rows.

## Function: StockMovement.save(self, *args, **kwargs)
- **Purpose**: Allow ledger insertion while preventing instance updates.
- **Inputs**:
  - `self` (`StockMovement`): Movement instance.
  - `args` (`tuple[object, ...]`): Django save arguments.
  - `kwargs` (`dict[str, object]`): Django save options.
- **Outputs**: `None`.
- **Dependencies**: Django Model.save.
- **Behavior**: Raises TypeError when a primary key already exists; delegates only new-row insertion.
- **Side Effects**: Inserts one StockMovement when new.

## Function: StockMovement.delete(self, *args, **kwargs)
- **Purpose**: Prevent instance deletion of inventory audit history.
- **Inputs**:
  - `self` (`StockMovement`): Persisted movement.
  - `args` (`tuple[object, ...]`): Ignored delete arguments.
  - `kwargs` (`dict[str, object]`): Ignored delete options.
- **Outputs**: Never returns normally; raises TypeError.
- **Dependencies**: None.
- **Behavior**: Rejects deletion unconditionally.
- **Side Effects**: None.

# Module / File: apps/inventory/services.py

## Function: _require_positive_int(value, name)
- **Purpose**: Enforce strict positive-integer inventory inputs.
- **Inputs**:
  - `value` (`object`): Candidate value.
  - `name` (`str`): Field name used in the error.
- **Outputs**: `int` validated value.
- **Dependencies**: Python type system.
- **Behavior**: Rejects Booleans, non-integers, zero, and negative values.
- **Side Effects**: None.

## Function: reserve_stock(*, variant_id, qty, session_key="", order=None)
- **Purpose**: Place one TTL-bound stock hold without overselling.
- **Inputs**:
  - `variant_id` (`int`): ProductVariant primary key.
  - `qty` (`int`): Positive requested units.
  - `session_key` (`str`): Guest/session correlation value.
  - `order` (`Order | None`): Checkout order owning the hold.
- **Outputs**: Active `Reservation`.
- **Dependencies**: StockRecord, Reservation, settings TTL, transaction.atomic, and select_for_update.
- **Behavior**: Validates quantity, locks the stock row, checks computed availability, increments reserved units, and creates the matching active reservation before releasing the lock.
- **Side Effects**: Updates StockRecord and inserts Reservation in one transaction.

## Function: _end_active_reservation(reservation, terminal_status)
- **Purpose**: Release one already-locked active reservation into a terminal state.
- **Inputs**:
  - `reservation` (`Reservation`): Active locked reservation.
  - `terminal_status` (`ReservationStatus`): Released or expired status.
- **Outputs**: Updated `Reservation`.
- **Dependencies**: StockRecord row lock and timezone.
- **Behavior**: Locks stock, checks counter coverage, decrements reserved units, stamps terminal status/time, and returns the row.
- **Side Effects**: Updates StockRecord and Reservation.

## Function: release_reservation(reservation_id)
- **Purpose**: Return an abandoned or cancelled hold to availability idempotently.
- **Inputs**:
  - `reservation_id` (`int`): Reservation primary key.
- **Outputs**: Terminal `Reservation`.
- **Dependencies**: Reservation lock, `_end_active_reservation`, and transaction.atomic.
- **Behavior**: Returns released/expired rows unchanged, rejects committed sales, and releases an active row.
- **Side Effects**: May update StockRecord and Reservation in one transaction.

## Function: commit_reservation(*, reservation_id, order)
- **Purpose**: Convert an active hold into a paid physical sale and audit movement.
- **Inputs**:
  - `reservation_id` (`int`): Active reservation primary key.
  - `order` (`Order`): Paid order reference.
- **Outputs**: Committed `Reservation`.
- **Dependencies**: Reservation/StockRecord locks, StockMovement, transaction.atomic, and timezone.
- **Behavior**: Rejects non-active or uncovered holds, decrements on-hand and reserved counters, appends one negative sale movement, links the order, and terminally commits the hold.
- **Side Effects**: Updates StockRecord/Reservation and inserts StockMovement atomically.

## Function: adjust_stock(*, variant_id, delta, reason, ref_order=None)
- **Purpose**: Apply audited restock, return, or manual-adjustment changes.
- **Inputs**:
  - `variant_id` (`int`): Variant primary key.
  - `delta` (`int`): Nonzero physical quantity change.
  - `reason` (`MovementReason | str`): Non-sale movement reason.
  - `ref_order` (`Order | None`): Optional related order.
- **Outputs**: Updated `StockRecord`.
- **Dependencies**: StockRecord lock, StockMovement, MovementReason, and transaction.atomic.
- **Behavior**: Validates sign/reason, forbids sales, prevents on-hand dropping below reserved, updates the counter, and appends the matching ledger entry.
- **Side Effects**: Updates StockRecord and inserts StockMovement atomically.

## Function: release_expired_reservations(now=None)
- **Purpose**: Expire every overdue active hold without letting one bad row block the sweep.
- **Inputs**:
  - `now` (`datetime | None`): Evaluation time; defaults to timezone.now.
- **Outputs**: `int` expired count.
- **Dependencies**: Reservation ORM, `_end_active_reservation`, per-row transactions, locks, and logger.
- **Behavior**: Collects candidate IDs, rechecks each under lock, skips racing terminal/future rows, expires valid candidates, and logs then continues after per-row exceptions.
- **Side Effects**: May update many StockRecord/Reservation rows and write exception logs.

## Function: scan_low_stock()
- **Purpose**: Find variants whose available units are at or below their configured threshold.
- **Inputs**:
  - `None` (`None`): No explicit parameters.
- **Outputs**: `QuerySet[StockRecord]` annotated with `available_units`.
- **Dependencies**: Django F expressions and related variant/product models.
- **Behavior**: Computes availability in SQL, filters against each row’s threshold, selects related display data, and orders by SKU.
- **Side Effects**: Database reads on evaluation.

# Module / File: jobs/scheduler.py and apps/inventory/management/commands/run_scheduler.py

## Function: sweep_expired_reservations()
- **Purpose**: Execute the periodic reservation-expiry job safely in a long-lived process.
- **Inputs**:
  - `None` (`None`): Scheduler invocation.
- **Outputs**: `None`.
- **Dependencies**: `release_expired_reservations`, `close_old_connections`, and logger.
- **Behavior**: Closes stale connections before/after work and logs a positive expiry count.
- **Side Effects**: May expire reservations, update inventory counters, recycle DB connections, and write logs.

## Function: run_low_stock_scan()
- **Purpose**: Execute the periodic low-stock scan and alert adapter.
- **Inputs**:
  - `None` (`None`): Scheduler invocation.
- **Outputs**: `None`.
- **Dependencies**: `scan_low_stock`, `send_low_stock_alert`, `close_old_connections`, and logger.
- **Behavior**: Recycles connections around the scan and logs when alerts cover one or more SKUs.
- **Side Effects**: Performs database reads, may send email, recycles DB connections, and writes logs.

## Function: build_scheduler(scheduler_class=BackgroundScheduler)
- **Purpose**: Build the two-job scheduler without starting it.
- **Inputs**:
  - `scheduler_class` (`type[BaseScheduler]`): Injectable scheduler implementation.
- **Outputs**: Configured scheduler instance.
- **Dependencies**: APScheduler, zoneinfo, Django settings, and the two job functions.
- **Behavior**: Uses the application timezone, schedules the expiry sweep in seconds and low-stock scan in minutes, and prevents overlapping/catch-up bursts with coalescing and one instance.
- **Side Effects**: Creates in-memory scheduler/job objects only.

## Function: Command.handle(self, *args, **options)
- **Purpose**: Run one foreground blocking scheduler process.
- **Inputs**:
  - `self` (`Command`): Django management command.
  - `args` (`tuple[object, ...]`): Unused positional arguments.
  - `options` (`dict[str, object]`): Command options.
- **Outputs**: `None` after interruption.
- **Dependencies**: `build_scheduler` and BlockingScheduler.
- **Behavior**: Builds the blocking scheduler, announces startup, starts it, and handles Ctrl+C with a stop message.
- **Side Effects**: Starts long-lived scheduled jobs and writes command output.

# Module / File: apps/orders/models.py

## Function: OrderQuerySet.update(self, **kwargs)
- **Purpose**: Block queryset-level status bypasses while preserving ordinary field updates.
- **Inputs**:
  - `self` (`OrderQuerySet`): Order queryset.
  - `kwargs` (`dict[str, object]`): Requested updates.
- **Outputs**: `int` affected-row count for non-status updates.
- **Dependencies**: `IllegalTransition` and Django QuerySet.update.
- **Behavior**: Rejects any `status` key and delegates other fields.
- **Side Effects**: May bulk-update non-status fields.

## Function: OrderQuerySet.bulk_update(self, objs, fields, batch_size=None)
- **Purpose**: Block bulk status rewrites.
- **Inputs**:
  - `self` (`OrderQuerySet`): Order queryset.
  - `objs` (`Iterable[Order]`): Orders to update.
  - `fields` (`Iterable[str]`): Field names.
  - `batch_size` (`int | None`): Optional batch size.
- **Outputs**: `int` affected-row count for allowed fields.
- **Dependencies**: `IllegalTransition` and Django bulk_update.
- **Behavior**: Rejects status in the field list and delegates other updates.
- **Side Effects**: May bulk-update non-status fields.

## Function: OrderQuerySet.bulk_create(self, objs, batch_size=None, ignore_conflicts=False, update_conflicts=False, update_fields=None, unique_fields=None)
- **Purpose**: Enforce Pending as the only initial order state and block conflict status updates.
- **Inputs**:
  - `self` (`OrderQuerySet`): Order queryset.
  - `objs` (`Iterable[Order]`): New orders.
  - `batch_size` (`int | None`): Optional batch size.
  - `ignore_conflicts` (`bool`): Insert option.
  - `update_conflicts` (`bool`): Upsert option.
  - `update_fields` (`Iterable[str] | None`): Upsert fields.
  - `unique_fields` (`Iterable[str] | None`): Conflict target fields.
- **Outputs**: `list[Order]`.
- **Dependencies**: OrderStatus, IllegalTransition, and Django bulk_create.
- **Behavior**: Materializes input, validates every recognized status as Pending, forbids conflict updates of status, and delegates valid inserts.
- **Side Effects**: May insert or conflict-update allowed order fields.

## Function: Order.save(self, *args, **kwargs)
- **Purpose**: Enforce Pending insertion and reject direct/stale status assignment.
- **Inputs**:
  - `self` (`Order`): Order instance.
  - `args` (`tuple[object, ...]`): Django save arguments.
  - `kwargs` (`dict[str, object]`): Save options including `update_fields`/`using`.
- **Outputs**: `None`.
- **Dependencies**: OrderStatus, IllegalTransition, transaction.atomic, and select_for_update.
- **Behavior**: Validates new orders, permits explicit non-status field saves, and otherwise locks the stored row to ensure the instance status still matches before delegating.
- **Side Effects**: Inserts or updates an Order and may acquire a row lock.

## Function: Order.transition_to(self, new_status)
- **Purpose**: Perform the sole sanctioned order-state transition.
- **Inputs**:
  - `self` (`Order`): Persisted order.
  - `new_status` (`OrderStatus | str`): Requested target.
- **Outputs**: Updated caller `Order`.
- **Dependencies**: ALLOWED_TRANSITIONS, transaction.atomic, select_for_update, and IllegalTransition.
- **Behavior**: Rejects unsaved/unknown targets, locks a fresh row, validates the current-to-target edge, writes status through the parent save implementation, and refreshes caller state.
- **Side Effects**: Updates one Order status atomically.

# Module / File: apps/core/money.py

## Function: require_centavos(value, field_name="amount", *, allow_negative=False)
- **Purpose**: Enforce the shared integer-centavo type and MySQL range boundary.
- **Inputs**:
  - `value` (`object`): Candidate amount.
  - `field_name` (`str`): Error-context label.
  - `allow_negative` (`bool`): Explicit signed-report opt-in.
- **Outputs**: `int` validated amount.
- **Dependencies**: `MAX_CENTAVOS` and MoneyValueError.
- **Behavior**: Rejects Boolean/non-integer input, unauthorized negatives, and magnitudes beyond unsigned MySQL INT.
- **Side Effects**: None.

## Function: format_centavos(value, symbol=None)
- **Purpose**: Format a valid amount as grouped Philippine-peso display text.
- **Inputs**:
  - `value` (`int`): Nonnegative centavos.
  - `symbol` (`str | None`): Optional display symbol override.
- **Outputs**: `str` formatted major/minor units.
- **Dependencies**: `require_centavos`, `CURRENCY_SYMBOL`, and `CURRENCY_MINOR_UNITS`.
- **Behavior**: Validates amount/symbol/scale and formats without float arithmetic.
- **Side Effects**: None.

## Function: multiply_centavos(unit_price, quantity)
- **Purpose**: Compute an order-line total exactly.
- **Inputs**:
  - `unit_price` (`int`): Unit price in centavos.
  - `quantity` (`int`): Positive non-Boolean units.
- **Outputs**: `int` line total.
- **Dependencies**: `require_centavos`.
- **Behavior**: Validates both inputs, multiplies integers, and validates overflow.
- **Side Effects**: None.

## Function: sum_centavos(amounts)
- **Purpose**: Sum nonnegative amounts with immediate overflow detection.
- **Inputs**:
  - `amounts` (`Iterable[int]`): Centavo values.
- **Outputs**: `int` total.
- **Dependencies**: `require_centavos`.
- **Behavior**: Validates each indexed item and the running total.
- **Side Effects**: Consumes the iterable; performs no external write.

# Module / File: apps/orders/services.py

## Function: next_order_no(year=None)
- **Purpose**: Allocate a race-safe `MD-YYYY-NNNNN` identifier.
- **Inputs**:
  - `year` (`int | None`): Four-digit business year or current Manila year.
- **Outputs**: `str` order number.
- **Dependencies**: OrderNumberSequence, timezone.localdate, transaction.atomic, select_for_update, and sequence-domain exceptions.
- **Behavior**: Rejects Boolean/non-four-digit years, locks or creates the annual row, rejects exhaustion at 99999, increments once, and zero-pads five digits.
- **Side Effects**: Inserts or updates one OrderNumberSequence.

# Module / File: apps/core/admin.py and apps/orders/admin.py

## Function: ExportCsvMixin.export_as_csv(self, request, queryset)
- **Purpose**: Export selected model rows using their concrete database fields.
- **Inputs**:
  - `self` (`ModelAdmin mixin`): Admin instance with a model.
  - `request` (`HttpRequest`): Staff request.
  - `queryset` (`QuerySet`): Selected rows.
- **Outputs**: CSV `HttpResponse`.
- **Dependencies**: Python csv and Django model metadata.
- **Behavior**: Writes a header of field names and one raw-value row per selected object.
- **Side Effects**: Evaluates the queryset and streams response bytes; does not mutate the database.

## Function: OrderAdmin.get_urls(self)
- **Purpose**: Add sales-report and printable-invoice routes to Order admin.
- **Inputs**:
  - `self` (`OrderAdmin`): Bound admin instance.
- **Outputs**: `list[URLPattern]`.
- **Dependencies**: Django admin URL wrapping and path.
- **Behavior**: Prepends protected custom routes to inherited model-admin URLs.
- **Side Effects**: None.

## Function: OrderAdmin.sales_report_view(self, request)
- **Purpose**: Render aggregate revenue/order counts and per-status counts.
- **Inputs**:
  - `self` (`OrderAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
- **Outputs**: Sales-report HTML.
- **Dependencies**: Order ORM, Count, Sum, `format_centavos`, and template rendering.
- **Behavior**: Counts revenue only for paid/packed/shipped/delivered states, formats it, aggregates all status counts, and supplies admin context.
- **Side Effects**: Database reads only.

## Function: OrderAdmin.invoice_view(self, request, object_id)
- **Purpose**: Render one staff-accessible printable order invoice.
- **Inputs**:
  - `self` (`OrderAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
  - `object_id` (`str`): Order primary-key path value.
- **Outputs**: Invoice HTML or 404.
- **Dependencies**: Order ORM and invoice template.
- **Behavior**: Loads the order by primary key and renders it.
- **Side Effects**: Database read only.

## Function: OrderAdmin.mark_as_packed(self, request, queryset)
- **Purpose**: Transition selected paid orders to Packed and book mock shipments.
- **Inputs**:
  - `self` (`OrderAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff action request.
  - `queryset` (`QuerySet[Order]`): Selected orders.
- **Outputs**: `None`; admin result messages.
- **Dependencies**: Order.transition_to, Shipment, `book_shipment`, ContentType, and LogEntry.
- **Behavior**: Processes each order, transitions it, creates/gets a shipment, books it, writes an admin audit entry, and counts illegal transitions as failures.
- **Side Effects**: Updates Orders/Shipments, inserts Shipment/LogEntry rows, and writes messages.

## Function: OrderAdmin.mark_as_shipped(self, request, queryset)
- **Purpose**: Transition selected packed orders to Shipped and notify customers.
- **Inputs**:
  - `self` (`OrderAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff action request.
  - `queryset` (`QuerySet[Order]`): Selected orders.
- **Outputs**: `None`; admin result messages.
- **Dependencies**: Order transition API, ShipmentStatus, SMS adapter, and LogEntry.
- **Behavior**: Transitions each order, marks an existing shipment in transit, sends an optional phone notification, writes audit history, and reports illegal transitions.
- **Side Effects**: Updates Orders/Shipments, may call Semaphore, inserts LogEntry, and writes messages/logs.

## Function: OrderAdmin.mark_as_cancelled(self, request, queryset)
- **Purpose**: Cancel selected pending orders and release their active holds.
- **Inputs**:
  - `self` (`OrderAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff action request.
  - `queryset` (`QuerySet[Order]`): Selected orders.
- **Outputs**: `None`; admin result messages.
- **Dependencies**: Order transition API, Reservation, and `release_reservation`.
- **Behavior**: Transitions each eligible order then releases every active order-linked reservation.
- **Side Effects**: Updates Order, Reservation, and StockRecord rows and writes admin messages.

## Function: OrderAdmin.mark_as_refunded(self, request, queryset)
- **Purpose**: Transition selected fulfilled/paid orders to Refunded and restore units.
- **Inputs**:
  - `self` (`OrderAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff action request.
  - `queryset` (`QuerySet[Order]`): Selected orders.
- **Outputs**: `None`; admin result messages.
- **Dependencies**: Order transition API, order items, `adjust_stock`, and MovementReason.RETURN.
- **Behavior**: Transitions the order first, then restores each line with a positive return movement; illegal transitions are reported. The multi-line orchestration is not yet one encompassing transaction.
- **Side Effects**: Updates Order/StockRecord rows, inserts StockMovement rows, and writes messages.

# Module / File: apps/payments/services.py

## Function: _auth_headers()
- **Purpose**: Build PayMongo Basic-auth JSON headers.
- **Inputs**:
  - `None` (`None`): Reads the configured secret.
- **Outputs**: `dict[str, str]` request headers.
- **Dependencies**: Base64 and `PAYMONGO_SECRET_KEY`.
- **Behavior**: Encodes `secret:` and returns Authorization, Content-Type, and Accept headers.
- **Side Effects**: Reads settings.

## Function: create_checkout_session(order, success_url, cancel_url)
- **Purpose**: Create one pending Payment and hosted or mocked checkout session.
- **Inputs**:
  - `order` (`Order`): Persisted order with items/address/totals.
  - `success_url` (`str`): Signed post-payment return URL.
  - `cancel_url` (`str`): Cart return URL.
- **Outputs**: `tuple[str, str]` checkout URL and provider/session ID.
- **Dependencies**: settings, Payment, PayMongo API, requests, item snapshots, and PayMongoError.
- **Behavior**: Mock mode records a deterministic pending Payment and appends `mock=1`. Provider mode builds exact PHP line items and billing metadata, POSTs with a timeout, rejects bad status/schema, and records the returned pending session.
- **Side Effects**: Inserts Payment and may make one external HTTPS request.

## Function: confirm_order_paid(*, order, method=None)
- **Purpose**: Idempotently confirm payment, consume stock holds, and transition the order.
- **Inputs**:
  - `order` (`Order`): Order whose one-to-one Payment exists.
  - `method` (`str | None`): Provider-reported method.
- **Outputs**: `bool`; true for first confirmation, false for replay.
- **Dependencies**: Payment row lock, inventory commit/reserve services, Order transition API, transaction.atomic, and logger.
- **Behavior**: Locks Payment, short-circuits an already-paid row, stamps payment status/time/method, commits active order reservations, attempts reserve+commit for shortfalls, logs a critical unfillable paid line without overselling, and transitions Pending → Paid.
- **Side Effects**: Updates Payment/Order/Reservation/StockRecord, inserts sale movements or replacement reservations, and may write warning/critical logs.

# Module / File: apps/payments/views.py

## Function: _signature_valid(request)
- **Purpose**: Fail-closed verify the PayMongo webhook HMAC.
- **Inputs**:
  - `request` (`HttpRequest`): Raw body and `Paymongo-Signature`.
- **Outputs**: `bool`.
- **Dependencies**: HMAC-SHA256, constant-time comparison, and `PAYMONGO_WEBHOOK_SECRET`.
- **Behavior**: Rejects an unset secret or missing timestamp, computes HMAC over `<timestamp>.<raw body>`, and accepts a matching test/live signature.
- **Side Effects**: May write an error log when the secret is absent.

## Function: _extract_reference_and_method(payload)
- **Purpose**: Normalize supported PayMongo event shapes into an order reference and payment method.
- **Inputs**:
  - `payload` (`dict[str, object]`): Parsed provider event.
- **Outputs**: `tuple[str, str]`.
- **Dependencies**: Provider JSON structure and `_METHOD_ALIASES`.
- **Behavior**: Reads reference_number or a known description prefix, extracts direct/nested source type, and maps `paymaya` to `maya`.
- **Side Effects**: None.

## Function: paymongo_webhook(request)
- **Purpose**: Process signed paid events idempotently and acknowledge provider retries.
- **Inputs**:
  - `request` (`HttpRequest`): POST webhook request.
- **Outputs**: Empty `HttpResponse` with HTTP 400 or 200.
- **Dependencies**: `_signature_valid`, JSON, Order, `confirm_order_paid`, Signer, notifications, and `require_POST`.
- **Behavior**: Verifies before parsing, rejects malformed/empty-reference paid events, acknowledges unsubscribed and unknown-order events appropriately, confirms known orders, and sends notifications only on first confirmation while isolating notification failures.
- **Side Effects**: May mutate all payment-confirmation state, send email/SMS, and write logs.

# Module / File: apps/notifications/services.py and apps/notifications/sms.py

## Function: send_order_confirmation(order, status_url)
- **Purpose**: Email an order summary and signed tracking link.
- **Inputs**:
  - `order` (`Order`): Confirmed order.
  - `status_url` (`str`): Tokenized tracking URL.
- **Outputs**: `bool` sent indicator.
- **Dependencies**: Django email backend, order items, and `format_centavos`.
- **Behavior**: Skips/logs orders without email, formats line/totals, and sends one plain-text message.
- **Side Effects**: May query items, send email, and write a warning log.

## Function: send_contact_alert(contact_message)
- **Purpose**: Notify configured staff about a stored contact inquiry.
- **Inputs**:
  - `contact_message` (`ContactMessage`): Persisted inquiry.
- **Outputs**: `bool` sent indicator.
- **Dependencies**: `CONTACT_ALERT_RECIPIENTS` and Django email backend.
- **Behavior**: Logs and returns false when recipients are absent; otherwise sends sender/message details.
- **Side Effects**: May send email and write an informational log.

## Function: send_low_stock_alert(records)
- **Purpose**: Email configured staff a low-stock SKU report.
- **Inputs**:
  - `records` (`Iterable[StockRecord]`): Low-stock rows.
- **Outputs**: `int` number of rows included in a sent alert, otherwise zero.
- **Dependencies**: `LOW_STOCK_ALERT_RECIPIENTS`, Django email backend, and StockRecord relations.
- **Behavior**: Materializes input, skips empty data, degrades to logging without recipients, formats counters, and sends one summary email.
- **Side Effects**: May query related data, send email, and write logs.

## Function: send_sms(phone_number, message)
- **Purpose**: Send a Semaphore SMS while keeping notifications off the critical path.
- **Inputs**:
  - `phone_number` (`str`): Destination.
  - `message` (`str`): Message body.
- **Outputs**: `bool` provider-success indicator.
- **Dependencies**: Semaphore settings, requests, and logger.
- **Behavior**: Logs a mock message when unconfigured, otherwise POSTs with a five-second timeout and converts every exception to false.
- **Side Effects**: May make an external request and currently logs destination/message/provider error details.

# Module / File: apps/shipping/jnt.py

## Function: book_shipment(shipment)
- **Purpose**: Simulate J&T booking for a pending Shipment.
- **Inputs**:
  - `shipment` (`Shipment`): Shipment row.
- **Outputs**: `bool`; false for non-pending, true after booking.
- **Dependencies**: Python random, timezone, and ShipmentStatus.
- **Behavior**: Generates a random 12-digit mock waybill, derives the J&T tracking URL, stamps Booked/time, and saves.
- **Side Effects**: Updates Shipment and consumes nondeterministic randomness.

# Module / File: apps/reviews/views.py and apps/reviews/admin.py

## Function: submit_review(request)
- **Purpose**: Create or update a moderated verified-purchase review.
- **Inputs**:
  - `request` (`HttpRequest`): Authenticated POST with order_no, product_id, rating, and body.
- **Outputs**: Redirect to the signed order-status page.
- **Dependencies**: Order ownership/items/status, Product, Review, Signer, messages, and decorators.
- **Behavior**: Hides foreign order existence, validates rating and Delivered/product membership, upserts one review per customer/product, and resets edits to Pending.
- **Side Effects**: Inserts/updates Review and writes a user message.

## Function: ReviewAdmin.approve_reviews(self, request, queryset)
- **Purpose**: Bulk-approve pending reviews.
- **Inputs**:
  - `self` (`ReviewAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
  - `queryset` (`QuerySet[Review]`): Selected rows.
- **Outputs**: `None`.
- **Dependencies**: ReviewStatus and admin messaging.
- **Behavior**: Updates only Pending rows and reports the count.
- **Side Effects**: Bulk-updates Review status and writes an admin message.

## Function: ReviewAdmin.reject_reviews(self, request, queryset)
- **Purpose**: Bulk-reject pending reviews.
- **Inputs**:
  - `self` (`ReviewAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
  - `queryset` (`QuerySet[Review]`): Selected rows.
- **Outputs**: `None`.
- **Dependencies**: ReviewStatus and admin messaging.
- **Behavior**: Updates only Pending rows and reports the count.
- **Side Effects**: Bulk-updates Review status and writes an admin message.

# Module / File: apps/storefront/views.py

## Function: homepage(request)
- **Purpose**: Render active CMS banners and the eight newest active products.
- **Inputs**:
  - `request` (`HttpRequest`): GET request.
- **Outputs**: Homepage HTML cached for five minutes outside tests.
- **Dependencies**: Product, HomepageBanner, template renderer, `require_GET`, and `cache_page`.
- **Behavior**: Selects product categories efficiently, orders products newest first, orders active banners by CMS order, and renders `banner.image_url` directly.
- **Side Effects**: Database reads and cache read/write.

## Function: shop_listing(request)
- **Purpose**: Render the searchable/filterable/sortable paginated shop.
- **Inputs**:
  - `request` (`HttpRequest`): GET filters, sort, search, and page.
- **Outputs**: Full shop HTML or HTMX grid fragment.
- **Dependencies**: Catalog query services, Paginator, Size/Fit choices, and templates.
- **Behavior**: Builds nonblank filters, executes the catalog service, paginates 12 per page, returns a fragment for HX-Request, and otherwise supplies filter metadata.
- **Side Effects**: Database reads.

## Function: product_detail(request, slug)
- **Purpose**: Render product content and stock-aware variant-picker data.
- **Inputs**:
  - `request` (`HttpRequest`): GET request and user session.
  - `slug` (`str`): Product slug.
- **Outputs**: Product-detail HTML or 404.
- **Dependencies**: `get_product_detail`, StockRecord, money formatter, WishlistItem, and JSON serialization.
- **Behavior**: Maps every variant to axes/price/available data, treats missing stock as sold out, orders sizes by enum, computes wishlist state, and renders the picker/reviews.
- **Side Effects**: Database reads.

## Function: cart_page(request)
- **Purpose**: Render the browser-managed cart shell.
- **Inputs**:
  - `request` (`HttpRequest`): GET request.
- **Outputs**: Cart HTML.
- **Dependencies**: Template renderer and `require_GET`.
- **Behavior**: Returns the page whose Alpine component hydrates `metrodrip_cart`.
- **Side Effects**: None server-side.

## Function: cart_availability(request)
- **Purpose**: Return authoritative availability for up to 50 variant IDs.
- **Inputs**:
  - `request` (`HttpRequest`): GET comma-list or POST JSON `ids`.
- **Outputs**: `JsonResponse` availability map or HTTP 400/405.
- **Dependencies**: JSON, StockRecord, and HttpResponseNotAllowed.
- **Behavior**: Parses integer IDs, rejects empty/oversized/malformed input, queries tracked rows, and returns zero for unknown/unstocked IDs.
- **Side Effects**: Database read only.

## Function: _parse_checkout_items(raw_items)
- **Purpose**: Validate checkout cart shape and merge duplicate variant lines.
- **Inputs**:
  - `raw_items` (`object`): Expected non-empty list of mappings.
- **Outputs**: `dict[int, int]` variant-to-total quantity.
- **Dependencies**: `MAX_CHECKOUT_LINES` and `MAX_LINE_QTY`.
- **Behavior**: Rejects empty/non-list/oversized input, converts IDs/quantities to integers, validates each original line at 1..99, and sums duplicate quantities.
- **Side Effects**: None.

## Function: checkout_page(request)
- **Purpose**: Render checkout or atomically create an order with stock holds and payment session.
- **Inputs**:
  - `request` (`HttpRequest`): GET or JSON POST containing items, customer/address fields, and zone_id.
- **Outputs**: Checkout HTML, success JSON with checkout URL, or HTTP 400/409/502 JSON error.
- **Dependencies**: ShippingZone, ProductVariant, Order/OrderItem, order-number service, inventory reservation service, payment service, session framework, and transaction.atomic.
- **Behavior**: GET lists active zones. POST parses items, requires name/email, validates zone, ensures a session, reloads authoritative variants, calculates effective-price subtotal, inserts reconciled totals/order/items and order-linked holds atomically, maps stock/input errors, then creates a checkout session. Provider failure releases active holds and returns a retryable error.
- **Side Effects**: Creates session, Order, OrderItem, Reservation, StockRecord updates, Payment/provider request, and logs; provider failure releases holds but leaves the pending order.

## Function: checkout_success(request, token)
- **Purpose**: Render the signed post-payment landing page and support the development mock-confirmation path.
- **Inputs**:
  - `request` (`HttpRequest`): Request with optional `mock=1`.
  - `token` (`str`): Signer token containing order primary key.
- **Outputs**: Success HTML or 404.
- **Dependencies**: Signer, Order, settings, `confirm_order_paid`, and notifications.
- **Behavior**: Rejects bad/missing orders, optionally confirms only when mock payments are enabled and explicitly requested, sends first-confirmation notifications with graceful failure, and renders order/token.
- **Side Effects**: Development mock path may execute full payment/inventory/order mutation and notifications.

## Function: order_status(request, token)
- **Purpose**: Render a read-only token-protected order tracking timeline.
- **Inputs**:
  - `request` (`HttpRequest`): GET request.
  - `token` (`str`): Signed order primary key.
- **Outputs**: Order-status HTML or 404.
- **Dependencies**: Signer, Order with payment/shipment/items, `_PROGRESS_STEPS`, and `require_GET`.
- **Behavior**: Rejects invalid tokens/orders, loads related commerce data, builds done/current/todo steps for the happy path, and uses terminal badges for cancelled/refunded orders.
- **Side Effects**: Database reads.

## Function: contact_page(request)
- **Purpose**: Store contact inquiries and attempt a staff alert.
- **Inputs**:
  - `request` (`HttpRequest`): GET or form POST.
- **Outputs**: Contact HTML with form, validation error, or success.
- **Dependencies**: ContactMessage, `send_contact_alert`, template renderer, and logger.
- **Behavior**: Requires trimmed name/email/message, stores first, isolates notification exceptions, and keeps storage as the required outcome.
- **Side Effects**: Inserts ContactMessage, may send email, and may log notification exceptions.

## Function: staging_seed_preview(request)
- **Purpose**: Expose read-only seeded-catalog evidence behind an explicit staging flag.
- **Inputs**:
  - `request` (`HttpRequest`): GET request.
- **Outputs**: Preview HTML, 404 while disabled, or 405 for an enabled non-GET request.
- **Dependencies**: Staging setting, Product ORM, Count, and template renderer.
- **Behavior**: Loads active products/category/variant counts, materializes totals, and renders the temporary acceptance page.
- **Side Effects**: Database reads only.

# Module / File: apps/storefront/templatetags/money.py and storefront_tags.py

## Function: peso(value)
- **Purpose**: Format template centavos without allowing malformed context to crash a page.
- **Inputs**:
  - `value` (`object`): Candidate centavo value.
- **Outputs**: `str` peso display or empty string.
- **Dependencies**: `format_centavos` and MoneyValueError.
- **Behavior**: Delegates valid values and suppresses domain-format exceptions.
- **Side Effects**: None.

## Function: sign(value)
- **Purpose**: Mint the same signed token consumed by order success/status views.
- **Inputs**:
  - `value` (`object`): Usually an Order primary key.
- **Outputs**: `str` Django Signer token.
- **Dependencies**: `django.core.signing.Signer`.
- **Behavior**: Stringifies and signs the value with the configured Django secret.
- **Side Effects**: None.

## Function: format_centavos_filter(value)
- **Purpose**: Provide a second template-safe alias for peso formatting.
- **Inputs**:
  - `value` (`object`): Candidate centavo value.
- **Outputs**: `str` formatted amount or empty string.
- **Dependencies**: `format_centavos` and MoneyValueError.
- **Behavior**: Delegates valid values and suppresses malformed display input.
- **Side Effects**: None.

# Module / File: static/js/cart.js and storefront templates

## Function: cartPage()
- **Purpose**: Supply the Alpine.js cart state machine backed by browser localStorage.
- **Inputs**:
  - `metrodrip_cart` (`JSON string | absent`): Browser-stored cart lines.
  - `cart-updated/storage events` (`Event`): Same-page and cross-tab updates.
- **Outputs**: Alpine component with items, loading state, item/subtotal getters, mutations, and peso formatting.
- **Dependencies**: Alpine.js, localStorage, CustomEvent, and optional `window.checkCartAvailability`.
- **Behavior**: Loads malformed storage as empty, persists mutations, dispatches update events, removes quantities below one, computes display totals, and requests advisory server availability after initialization.
- **Side Effects**: Reads/writes browser localStorage and registers/dispatches browser events.

## Function: N/A — template and design-layer contract
- **Purpose**: Describe server-rendered pages and their client-side enhancement boundary.
- **Inputs**:
  - `Django context` (`mapping[str, object]`): Products, orders, account data, messages, tokens, and settings.
  - `browser interaction` (`DOM events`): Variant/cart/checkout/wishlist actions.
- **Outputs**: Storefront/account/admin HTML styled by `static/css/storefront.css`.
- **Dependencies**: Django templates, HTMX 2.0.4 with SRI, Alpine.js 3.14.9, Google Fonts, and cart.js.
- **Behavior**: Base template provides navigation/footer/cart badge. Product detail and checkout embed Alpine components; cart uses cart.js and availability fetches. Cycle 1 corrected homepage banner rendering to the model’s `image_url`. Current CSS remains the pre-plan token system and still requires the dedicated UI/accessibility cycle.
- **Side Effects**: Browser scripts use localStorage, fetch JSON endpoints, redirect to hosted checkout, and may load third-party CDN/font resources.

# Module / File: Dockerfile, docker-compose.yml, deploy/, and .github/workflows/ci.yml

## Function: N/A — deployment and CI contract
- **Purpose**: Describe local database, hardened staging, startup, and continuous-validation mechanics.
- **Inputs**:
  - `environment` (`mapping[str, str]`): Secrets, hosts, ports, MySQL credentials, and staging flags.
  - `repository source` (`Docker build context`): Application and dependency manifest.
- **Outputs**: Local MySQL service, non-root Django image, four-service staging stack, HTTPS ingress, and two CI jobs.
- **Dependencies**: Docker 28+, Compose 2.40+, `python:3.14-slim`, `mysql:8.4`, `caddy:2-alpine`, Gunicorn, and WhiteNoise.
- **Behavior**: Local Compose publishes only MySQL for host-run Django. The image installs requirements, keeps source root-owned, grants UID/GID 10001 write access only to static output, and runs the entrypoint. Entrypoint validates seed flags, collects static, migrates, optionally seeds, then execs Gunicorn. Staging isolates MySQL on an internal network and exposes only Caddy. CI now compiles Python before Ruff, runs real-MySQL tests/reversible migrations, builds the image, checks ownership, and exercises disposable HTTPS persistence.
- **Side Effects**: Builds images, creates containers/networks/volumes, applies migrations/seeds, and may obtain public certificates when deployed with real DNS.

## Function: N/A — executable-mode invariant
- **Purpose**: Guarantee that `manage.py` and `deploy/entrypoint.sh` are mode 755 inside the image on every build host, which the CI ownership gate asserts.
- **Inputs**:
  - `build context file modes` (`POSIX mode bits`): Modes carried by the checkout that Docker copies.
  - `git index modes` (`100644 | 100755`): The executable bit recorded in the tree.
- **Outputs**: `/app/manage.py` and `/app/deploy/entrypoint.sh` at mode 755, root-owned, non-writable by UID 10001.
- **Dependencies**: Dockerfile `RUN chmod` layer, Git tree metadata, `actions/checkout`.
- **Behavior**: Windows checkouts cannot carry a POSIX executable bit, and Docker Desktop's Windows build context reports 0755 for every file, so a mode defect is invisible locally and only appears on a Linux runner. Both files are therefore recorded as `100755` in the Git tree *and* chmodded explicitly in the image build. The chmod is authoritative: the image contract holds even if a future checkout, archive, or export drops the bit.
- **Side Effects**: None beyond the mode change in the built image layer.

# Module / File: index.html, .nojekyll, and docs/images/

## Function: N/A — GitHub Pages onboarding-guide contract
- **Purpose**: Serve the team's local setup and testing guide at the repository's GitHub Pages URL, replacing the auto-rendered README.
- **Inputs**:
  - `repository root` (`GitHub Pages publishing source`): Branch `main`, root directory.
  - `viewer OS selection` (`radio input state`): Chooses which platform's commands are displayed. Defaults to Windows.
- **Outputs**: A static, self-contained fifteen-section guide covering toolchain installation, configuration, database startup, migration and seeding, running the server, admin creation, verification, tests, teardown, troubleshooting, and a command cheat sheet.
- **Dependencies**: GitHub Pages static hosting, Google Fonts (Anton, Inter, IBM Plex Mono). No build step, no framework, no external scripts, no local asset references.
- **Behavior**: Pages serves static files only and executes no application code, so the Django storefront cannot be hosted there; the guide states this explicitly rather than implying a broken deployment. Empty `.nojekyll` disables the Jekyll build, which would otherwise pass tracked Markdown containing Django template tags through Liquid. Documentation links target GitHub's blob view because Pages serves sibling `.md` files as raw text. Platform-specific commands are switched by one radio group at the top of `.osroot` using CSS sibling selectors, so the guide works without JavaScript; `.only-win|mac|linux` toggle `display:block` and `.only-win-i|mac-i|linux-i` toggle `display:inline` for OS-specific words mid-sentence. Inline `style` attributes must never be used on these classes — they defeat the `display:none` default and reveal all three platforms simultaneously. The single script adds clipboard buttons as progressive enhancement. An inline SVG renders the browser → Django → MySQL topology with a `<title>`/`<desc>` pair for screen readers. Seven `<figure>` elements carry captured images from `docs/images/`, each with a descriptive `alt`, `loading="lazy"`, and accurate `width`/`height` so scrolling does not reflow. The `.ph` placeholder styling is retained for figures added before their image exists.
- **Side Effects**: Publishes a public page at the repository's Pages URL on push to `main`.

## Function: N/A — guide image provenance
- **Purpose**: Record how the seven guide images were produced so they can be regenerated rather than retouched when the UI changes.
- **Inputs**:
  - `running dev server` (`http://127.0.0.1:8000`): Live storefront and admin, seeded catalogue.
  - `real command output` (`text`): Version checks and Compose status from a development machine.
- **Outputs**: `docs/images/01`-`07` PNGs, roughly 390 KB total, each at most 1600 px wide.
- **Dependencies**: Playwright driving the installed Edge (`channel="msedge"`), the seeded MySQL database, and a local superuser for the admin capture.
- **Behavior**: Application screenshots (03-06) were captured by navigating the real storefront - opening a product, selecting one option per variant axis, adding to cart, and logging into the admin - so the cart and checkout images carry a genuine SKU rather than fabricated data. Selecting one option per axis matters: Alpine keeps the add-to-cart button disabled until Size, Color, and Fit are all chosen, so a loop that re-queries a global button list re-clicks the same element and never enables it. Images 01 and 02 are real terminal output typeset as a terminal, which stays legible at the guide's column width where a console crop would not. Image 07 is a hand-authored SVG rendered to PNG. Captures use a 1280 px viewport at a 1.25 device scale factor, landing exactly on the 1600 px ceiling.
- **Side Effects**: None on the application; capture is read-only apart from the cart entry written to browser localStorage in a disposable context.

# Module / File: tests/

## Function: N/A — automated regression contract
- **Purpose**: Summarize executable coverage without treating test helpers as production APIs.
- **Inputs**:
  - `pytest invocation` (`command`): `python -m pytest` using `config.settings.test`.
  - `MySQL service` (`MySQL 8/InnoDB`): Real lock and constraint behavior.
- **Outputs**: 276 collected passing cases from 174 source-level test functions as of Cycle 1.
- **Dependencies**: pytest, pytest-django, Django test client, threading/concurrency helpers, seeded data, HMAC fixtures, and MySQL metadata.
- **Behavior**: Coverage spans admin actions/registration, checkout/payment/webhook flow, two inventory concurrency gates, reservation/ledger semantics, model/database constraints, order allocation/state guards, centavo boundaries, health probes, staging settings/preview, catalog/storefront behavior, template rendering, banner URL regression, and migration-operation regression. Parametrization expands source functions into the 276 executed cases.
- **Side Effects**: Creates and destroys isolated test database state, sends mail only through the test backend, and may run concurrent database transactions.

# Module / File: apps/accounts/admin.py

## Function: WishlistItemAdmin.has_add_permission(self, request)
- **Purpose**: Prevent staff from fabricating storefront-managed wishlist rows.
- **Inputs**:
  - `self` (`WishlistItemAdmin`): Bound admin instance.
  - `request` (`HttpRequest`): Staff request.
- **Outputs**: `bool` false.
- **Dependencies**: Django ModelAdmin permission contract.
- **Behavior**: Denies add access unconditionally.
- **Side Effects**: None.

## Function: WishlistItemAdmin.has_delete_permission(self, request, obj=None)
- **Purpose**: Prevent staff from deleting customer-managed wishlist rows.
- **Inputs**:
  - `self` (`WishlistItemAdmin`): Bound admin instance.
  - `request` (`HttpRequest`): Staff request.
  - `obj` (`WishlistItem | None`): Optional row.
- **Outputs**: `bool` false.
- **Dependencies**: Django ModelAdmin permission contract.
- **Behavior**: Denies deletion unconditionally.
- **Side Effects**: None.

# Module / File: apps/catalog/admin.py display helpers

## Function: ProductVariantInline.effective_price_display(self, obj)
- **Purpose**: Display the resolved variant price in the inline editor.
- **Inputs**:
  - `self` (`ProductVariantInline`): Bound inline.
  - `obj` (`ProductVariant`): Variant or unsaved inline object.
- **Outputs**: `str` formatted pesos or em dash.
- **Dependencies**: ProductVariant.price and `format_centavos`.
- **Behavior**: Returns an em dash before persistence; otherwise formats the effective price.
- **Side Effects**: May read the related Product; performs no write.

## Function: CategoryAdmin.product_count(self, obj)
- **Purpose**: Display the number of products assigned to a category.
- **Inputs**:
  - `self` (`CategoryAdmin`): Bound admin.
  - `obj` (`Category`): Category row.
- **Outputs**: `int` related product count.
- **Dependencies**: Category.products manager.
- **Behavior**: Executes the related count query.
- **Side Effects**: Database read only.

## Function: ProductAdmin.base_price_display(self, obj)
- **Purpose**: Display a product’s base price in pesos.
- **Inputs**:
  - `self` (`ProductAdmin`): Bound admin.
  - `obj` (`Product`): Product row.
- **Outputs**: `str` formatted price.
- **Dependencies**: `format_centavos`.
- **Behavior**: Formats the integer-centavo base price.
- **Side Effects**: None.

## Function: ProductAdmin.variant_count(self, obj)
- **Purpose**: Display the number of variants belonging to a product.
- **Inputs**:
  - `self` (`ProductAdmin`): Bound admin.
  - `obj` (`Product`): Product row.
- **Outputs**: `int` related variant count.
- **Dependencies**: Product.variants manager.
- **Behavior**: Executes the related count query.
- **Side Effects**: Database read only.

# Module / File: apps/inventory/admin.py

## Function: StockRecordInline.available_display(self, obj)
- **Purpose**: Display computed availability in the variant inline.
- **Inputs**:
  - `self` (`StockRecordInline`): Bound inline.
  - `obj` (`StockRecord`): Stock row or unsaved inline.
- **Outputs**: `int | str` available units or em dash.
- **Dependencies**: StockRecord.available.
- **Behavior**: Returns an em dash for an unsaved row and computed availability otherwise.
- **Side Effects**: None.

## Function: StockRecordAdmin.available_display(self, obj)
- **Purpose**: Display computed availability in the stock list/detail.
- **Inputs**:
  - `self` (`StockRecordAdmin`): Bound admin.
  - `obj` (`StockRecord`): Stock row.
- **Outputs**: `int` available units.
- **Dependencies**: StockRecord.available.
- **Behavior**: Returns on-hand minus reserved.
- **Side Effects**: None.

## Function: StockMovementAdmin.has_add_permission(self, request)
- **Purpose**: Keep ledger insertion behind inventory services.
- **Inputs**:
  - `self` (`StockMovementAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
- **Outputs**: `bool` false.
- **Dependencies**: Django ModelAdmin permissions.
- **Behavior**: Denies manual add access.
- **Side Effects**: None.

## Function: StockMovementAdmin.has_change_permission(self, request, obj=None)
- **Purpose**: Prevent staff from rewriting append-only ledger rows.
- **Inputs**:
  - `self` (`StockMovementAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
  - `obj` (`StockMovement | None`): Optional row.
- **Outputs**: `bool` false.
- **Dependencies**: Django ModelAdmin permissions.
- **Behavior**: Denies change access.
- **Side Effects**: None.

## Function: StockMovementAdmin.has_delete_permission(self, request, obj=None)
- **Purpose**: Prevent staff from erasing append-only ledger rows.
- **Inputs**:
  - `self` (`StockMovementAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
  - `obj` (`StockMovement | None`): Optional row.
- **Outputs**: `bool` false.
- **Dependencies**: Django ModelAdmin permissions.
- **Behavior**: Denies delete access.
- **Side Effects**: None.

## Function: ReservationAdmin.session_key_short(self, obj)
- **Purpose**: Limit session-key exposure in the reservation list.
- **Inputs**:
  - `self` (`ReservationAdmin`): Bound admin.
  - `obj` (`Reservation`): Reservation row.
- **Outputs**: `str` blank marker, full short key, or first 12 characters plus ellipsis.
- **Dependencies**: Reservation.session_key.
- **Behavior**: Truncates values longer than 12 characters.
- **Side Effects**: None.

## Function: ReservationAdmin.has_add_permission(self, request)
- **Purpose**: Keep reservation creation behind checkout services.
- **Inputs**:
  - `self` (`ReservationAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
- **Outputs**: `bool` false.
- **Dependencies**: Django ModelAdmin permissions.
- **Behavior**: Denies manual creation.
- **Side Effects**: None.

## Function: ReservationAdmin.has_change_permission(self, request, obj=None)
- **Purpose**: Keep reservation state transitions behind inventory services.
- **Inputs**:
  - `self` (`ReservationAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
  - `obj` (`Reservation | None`): Optional row.
- **Outputs**: `bool` false.
- **Dependencies**: Django ModelAdmin permissions.
- **Behavior**: Denies manual changes.
- **Side Effects**: None.

## Function: ReservationAdmin.has_delete_permission(self, request, obj=None)
- **Purpose**: Preserve reservation lifecycle evidence.
- **Inputs**:
  - `self` (`ReservationAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
  - `obj` (`Reservation | None`): Optional row.
- **Outputs**: `bool` false.
- **Dependencies**: Django ModelAdmin permissions.
- **Behavior**: Denies deletion.
- **Side Effects**: None.

# Module / File: apps/inventory/models.py display methods

## Function: StockRecord.__str__(self)
- **Purpose**: Return readable current stock counters.
- **Inputs**:
  - `self` (`StockRecord`): Stock row.
- **Outputs**: `str` variant ID, on-hand, and reserved values.
- **Dependencies**: Stored StockRecord fields.
- **Behavior**: Formats the current counters.
- **Side Effects**: None.

## Function: Reservation.__str__(self)
- **Purpose**: Return readable hold identity and lifecycle state.
- **Inputs**:
  - `self` (`Reservation`): Reservation row.
- **Outputs**: `str` variant ID, quantity, and status.
- **Dependencies**: Stored Reservation fields.
- **Behavior**: Formats the hold summary.
- **Side Effects**: None.

## Function: StockMovement.__str__(self)
- **Purpose**: Return readable signed-ledger information.
- **Inputs**:
  - `self` (`StockMovement`): Movement row.
- **Outputs**: `str` variant ID, signed delta, and reason.
- **Dependencies**: Stored StockMovement fields.
- **Behavior**: Formats positive deltas with an explicit plus sign.
- **Side Effects**: None.

# Module / File: apps/orders/admin.py display and permission helpers

## Function: OrderItemInline.unit_price_display(self, obj)
- **Purpose**: Display historical unit price in pesos.
- **Inputs**:
  - `self` (`OrderItemInline`): Bound inline.
  - `obj` (`OrderItem`): Item or unsaved inline.
- **Outputs**: `str` formatted price or em dash.
- **Dependencies**: `format_centavos`.
- **Behavior**: Returns an em dash for unsaved rows and formats the snapshot otherwise.
- **Side Effects**: None.

## Function: OrderItemInline.has_add_permission(self, request, obj=None)
- **Purpose**: Prevent staff from adding historical order lines.
- **Inputs**:
  - `self` (`OrderItemInline`): Bound inline.
  - `request` (`HttpRequest`): Staff request.
  - `obj` (`Order | None`): Parent order.
- **Outputs**: `bool` false.
- **Dependencies**: Django inline permissions.
- **Behavior**: Denies add access.
- **Side Effects**: None.

## Function: OrderItemInline.has_delete_permission(self, request, obj=None)
- **Purpose**: Prevent staff from deleting historical order lines.
- **Inputs**:
  - `self` (`OrderItemInline`): Bound inline.
  - `request` (`HttpRequest`): Staff request.
  - `obj` (`Order | None`): Parent order.
- **Outputs**: `bool` false.
- **Dependencies**: Django inline permissions.
- **Behavior**: Denies delete access.
- **Side Effects**: None.

## Function: OrderAdmin.subtotal_display(self, obj)
- **Purpose**: Display order subtotal in pesos.
- **Inputs**:
  - `self` (`OrderAdmin`): Bound admin.
  - `obj` (`Order`): Order row.
- **Outputs**: `str` formatted subtotal.
- **Dependencies**: `format_centavos`.
- **Behavior**: Formats integer centavos.
- **Side Effects**: None.

## Function: OrderAdmin.shipping_fee_display(self, obj)
- **Purpose**: Display order shipping fee in pesos.
- **Inputs**:
  - `self` (`OrderAdmin`): Bound admin.
  - `obj` (`Order`): Order row.
- **Outputs**: `str` formatted shipping fee.
- **Dependencies**: `format_centavos`.
- **Behavior**: Formats integer centavos.
- **Side Effects**: None.

## Function: OrderAdmin.total_display(self, obj)
- **Purpose**: Display order total in pesos.
- **Inputs**:
  - `self` (`OrderAdmin`): Bound admin.
  - `obj` (`Order`): Order row.
- **Outputs**: `str` formatted total.
- **Dependencies**: `format_centavos`.
- **Behavior**: Formats integer centavos.
- **Side Effects**: None.

## Function: OrderAdmin.has_add_permission(self, request)
- **Purpose**: Prevent staff from fabricating orders outside checkout.
- **Inputs**:
  - `self` (`OrderAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
- **Outputs**: `bool` false.
- **Dependencies**: Django ModelAdmin permissions.
- **Behavior**: Denies add access.
- **Side Effects**: None.

## Function: OrderAdmin.has_delete_permission(self, request, obj=None)
- **Purpose**: Prevent staff from erasing commercial history.
- **Inputs**:
  - `self` (`OrderAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
  - `obj` (`Order | None`): Optional order.
- **Outputs**: `bool` false.
- **Dependencies**: Django ModelAdmin permissions.
- **Behavior**: Denies deletion.
- **Side Effects**: None.

# Module / File: apps/orders/models.py display methods

## Function: Order.__str__(self)
- **Purpose**: Return the public order identifier for display/logging.
- **Inputs**:
  - `self` (`Order`): Order row.
- **Outputs**: `str` order number.
- **Dependencies**: Order.order_no.
- **Behavior**: Returns the stored `MD-YYYY-NNNNN` value.
- **Side Effects**: None.

## Function: OrderItem.__str__(self)
- **Purpose**: Return readable order-line identity.
- **Inputs**:
  - `self` (`OrderItem`): Order line.
- **Outputs**: `str` order ID, variant ID, and quantity.
- **Dependencies**: Stored foreign-key IDs and quantity.
- **Behavior**: Formats the line without loading related objects.
- **Side Effects**: None.

## Function: OrderNumberSequence.__str__(self)
- **Purpose**: Return readable annual allocator state.
- **Inputs**:
  - `self` (`OrderNumberSequence`): Sequence row.
- **Outputs**: `str` year and last value.
- **Dependencies**: Stored sequence fields.
- **Behavior**: Formats the allocator state.
- **Side Effects**: None.

# Module / File: apps/payments/admin.py and apps/payments/models.py

## Function: PaymentAdmin.amount_display(self, obj)
- **Purpose**: Display the payment amount in pesos.
- **Inputs**:
  - `self` (`PaymentAdmin`): Bound admin.
  - `obj` (`Payment`): Payment row.
- **Outputs**: `str` formatted amount.
- **Dependencies**: `format_centavos`.
- **Behavior**: Formats integer centavos.
- **Side Effects**: None.

## Function: PaymentAdmin.has_add_permission(self, request)
- **Purpose**: Keep Payment creation behind checkout.
- **Inputs**:
  - `self` (`PaymentAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
- **Outputs**: `bool` false.
- **Dependencies**: Django ModelAdmin permissions.
- **Behavior**: Denies manual creation.
- **Side Effects**: None.

## Function: PaymentAdmin.has_delete_permission(self, request, obj=None)
- **Purpose**: Preserve provider reconciliation history.
- **Inputs**:
  - `self` (`PaymentAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
  - `obj` (`Payment | None`): Optional payment.
- **Outputs**: `bool` false.
- **Dependencies**: Django ModelAdmin permissions.
- **Behavior**: Denies deletion.
- **Side Effects**: None.

## Function: Payment.__str__(self)
- **Purpose**: Return readable payment identity/state.
- **Inputs**:
  - `self` (`Payment`): Payment row.
- **Outputs**: `str` order ID, method, and status.
- **Dependencies**: Stored Payment fields.
- **Behavior**: Formats the payment summary.
- **Side Effects**: None.

# Module / File: apps/reviews/admin.py and apps/reviews/models.py

## Function: ReviewAdmin.has_add_permission(self, request)
- **Purpose**: Keep review creation behind verified storefront submission.
- **Inputs**:
  - `self` (`ReviewAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
- **Outputs**: `bool` false.
- **Dependencies**: Django ModelAdmin permissions.
- **Behavior**: Denies manual creation.
- **Side Effects**: None.

## Function: ReviewAdmin.has_delete_permission(self, request, obj=None)
- **Purpose**: Preserve submitted review history while allowing moderation status.
- **Inputs**:
  - `self` (`ReviewAdmin`): Bound admin.
  - `request` (`HttpRequest`): Staff request.
  - `obj` (`Review | None`): Optional review.
- **Outputs**: `bool` false.
- **Dependencies**: Django ModelAdmin permissions.
- **Behavior**: Denies deletion.
- **Side Effects**: None.

## Function: Review.__str__(self)
- **Purpose**: Return readable product/rating/customer/moderation text.
- **Inputs**:
  - `self` (`Review`): Review row.
- **Outputs**: `str` summary.
- **Dependencies**: Stored Review fields.
- **Behavior**: Formats product ID, star rating, customer ID, and status.
- **Side Effects**: None.

# Module / File: apps/shipping/models.py

## Function: ShippingZone.__str__(self)
- **Purpose**: Return the zone’s display name.
- **Inputs**:
  - `self` (`ShippingZone`): Zone row.
- **Outputs**: `str` name.
- **Dependencies**: ShippingZone.name.
- **Behavior**: Returns the stored name.
- **Side Effects**: None.

## Function: Shipment.__str__(self)
- **Purpose**: Return readable order/courier/tracking identity.
- **Inputs**:
  - `self` (`Shipment`): Shipment row.
- **Outputs**: `str` order ID, courier, and waybill or fallback text.
- **Dependencies**: Stored Shipment fields.
- **Behavior**: Uses `(no waybill)` until booking/manual entry.
- **Side Effects**: None.

# Module / File: apps/accounts/admin.py

## Function: CustomerAdmin.console_display(self, obj)
- **Purpose**: Show which console an account can actually enter, not merely which role it carries.
- **Inputs**:
  - `obj` (`Customer`): The row being rendered.
- **Outputs**: `str` — the console label, "(superuser)"-suffixed where applicable, or "— storefront only".
- **Dependencies**: `Customer.console`, `StaffRole`.
- **Behavior**: Reads `obj.console` and renders its label. Sortable by `role`.
- **Side Effects**: None.
- **DSA Used**: None; adds no query per row.
- **Data Analysis Notes**: The `role` column alone is misleading, because an inactive or non-staff account with the Administrator role opens nothing. This column makes a suspended administrator visibly powerless in the changelist.
- **Responsive & Accessibility Notes**: Plain text in a standard admin column.
- **Security Notes**: Read-only display.

## Function: CustomerAdmin.get_readonly_fields(self, request, obj=None)
- **Purpose**: Enforce the two privilege tiers of FR Admin-03 on the server.
- **Inputs**:
  - `request` (`HttpRequest`): The acting administrator's request.
  - `obj` (`Customer | None`): The account being edited, or None on the add form.
- **Outputs**: `tuple[str, ...]` of field names rendered read-only.
- **Dependencies**: `PRIVILEGE_FIELDS`, `_FIELD_ORDER`.
- **Behavior**: Always locks `date_joined` and `last_login`. Adds every privilege field (`role`, `is_staff`, `is_superuser`, `groups`, `user_permissions`) when the requester is not a superuser, and adds those plus `is_active` when the target is the requester. Filters through `_FIELD_ORDER` so the returned order is deterministic and the admin's field-ordering checks pass.
- **Side Effects**: None.
- **DSA Used**: Set union for accumulation, then one ordered pass over `_FIELD_ORDER` — O(n) in field count with a stable result.
- **Data Analysis Notes**: Fields are returned read-only rather than dropped from the form, so an administrator investigating an account can still see that it is a merchant without being able to change it.
- **Responsive & Accessibility Notes**: Django renders read-only fields as text, announced by screen readers as static content rather than as a disabled input.
- **Security Notes**: The self-lockout guard stops an operator editing their own way out of the console they are signed in to; recovering would need shell access. Escalation is blocked server-side — a hand-crafted POST carrying `is_superuser` is ignored, because Django excludes read-only fields from the form entirely.

## Function: CustomerAdmin.has_change_permission / has_delete_permission(self, request, obj=None)
- **Purpose**: Prevent horizontal privilege escalation through the account screen.
- **Inputs**:
  - `request` (`HttpRequest`): The acting administrator's request.
  - `obj` (`Customer | None`): Target account.
- **Outputs**: `bool`.
- **Dependencies**: `BaseUserAdmin`.
- **Behavior**: Both return False when the target is a superuser and the requester is not. `has_delete_permission` additionally refuses self-deletion.
- **Side Effects**: None.
- **DSA Used**: None.
- **Data Analysis Notes**: None.
- **Responsive & Accessibility Notes**: Denied actions are absent from the rendered page rather than shown disabled.
- **Security Notes**: Without the superuser check, a non-superuser administrator could reset the password of the account that outranks them and then sign in as it — the classic escalation through an account-management screen. Object-level checks run on the change view, the delete view, and the changelist action confirmation.

## Function: CustomerAdmin._set_active(self, request, queryset, active)
- **Purpose**: Back the activate/suspend actions and record each change in the audit trail (FR Admin-02, FR Admin-05).
- **Inputs**:
  - `request` (`HttpRequest`): Acting administrator.
  - `queryset` (`QuerySet[Customer]`): Selected accounts.
  - `active` (`bool`): Target state.
- **Outputs**: `None`; messages the operator with a count.
- **Dependencies**: `ModelAdmin.log_change`, `ModelAdmin.message_user`.
- **Behavior**: Excludes the acting account, excludes superusers when the requester is not one, then saves each remaining row individually with `update_fields=["is_active"]` and writes a `LogEntry`.
- **Side Effects**: Updates `is_active`; inserts one `LogEntry` per changed account.
- **DSA Used**: Two queryset-level exclusions push filtering into SQL; the per-row loop is bounded by the operator's selection.
- **Data Analysis Notes**: Deliberately not `queryset.update()`. A bulk UPDATE writes no `LogEntry` rows, and a suspension that leaves no trace is precisely the event an audit trail exists to capture. The `.exclude(is_active=active)` filter also keeps the reported count honest — re-suspending an already-suspended account reports 0, not 1.
- **Responsive & Accessibility Notes**: Result reported through the standard admin messages region.
- **Security Notes**: Suspension takes effect on the next request, not at the next login: `ModelBackend.get_user` refuses an inactive user, so any live session stops authenticating immediately (FR Customer-21). Self-exclusion means bulk-selecting every row cannot lock the operator out.

## Function: N/A — AuditTrailAdmin read-only contract
- **Purpose**: Expose Django's `LogEntry` as the administrator console's audit trail (FR Admin-05).
- **Inputs**:
  - `LogEntry` rows (`django.contrib.admin.models.LogEntry`): Written automatically by both consoles.
- **Outputs**: A filterable, searchable, date-hierarchical changelist.
- **Dependencies**: `django.contrib.admin`, `django.contrib.contenttypes`.
- **Behavior**: `has_add_permission`, `has_change_permission`, and `has_delete_permission` all return False unconditionally. `list_select_related = ("user", "content_type")` keeps the changelist at a constant query count. `action_description` maps the numeric `action_flag` (1/2/3) to Added/Changed/Deleted.
- **Side Effects**: None.
- **DSA Used**: Single join-backed changelist query; the flag-to-word mapping is a dict lookup with a default, so an unknown flag renders "Unknown" instead of raising.
- **Data Analysis Notes**: Django writes a `LogEntry` for every add, change, and delete performed through either console, so this one screen covers merchant activity as well as administrator activity.
- **Responsive & Accessibility Notes**: Standard Django admin changelist; the date hierarchy is keyboard navigable.
- **Security Notes**: Registered on the administrator console only — letting merchants read, edit, or prune the log of their own actions would defeat the point. Read-only for everyone including superusers, giving it the same append-only guarantee `StockMovement` has.

# Module / File: apps/core/admin.py

## Function: ExportCsvMixin.export_as_csv(self, request, queryset)
- **Purpose**: Stream the selected rows as CSV (FR Merchant-06).
- **Inputs**:
  - `request` (`HttpRequest`): Acting staff request.
  - `queryset` (`QuerySet`): Selected rows.
- **Outputs**: `HttpResponse` with `text/csv` and a `Content-Disposition` attachment header.
- **Dependencies**: `csv`, `django.http.HttpResponse`.
- **Behavior**: Walks `model._meta.fields`, skipping any name listed in `csv_export_exclude`, and writes a header row followed by one row per object.
- **Side Effects**: None persisted.
- **DSA Used**: Single pass over the queryset; O(rows x columns).
- **Data Analysis Notes**: Concrete fields only — reverse relations and many-to-many are not exported, so an order export carries the order, not its line items.
- **Responsive & Accessibility Notes**: Not applicable; the response is a file download.
- **Security Notes**: `csv_export_exclude` defaults to `("password",)`. Without it the mixin wrote every selected account's password hash into a downloadable file when used on `CustomerAdmin` — offline-crackable, and a category of personal data the export has no reason to carry (NFR Privacy-11).

# Module / File: apps/accounts/management/commands/sync_console_roles.py

## Function: allowed_actions(model_admin)
- **Purpose**: Determine which permission verbs a ModelAdmin actually permits.
- **Inputs**:
  - `model_admin` (`ModelAdmin`): A registered admin class instance.
- **Outputs**: `set[str]` drawn from `{"view", "add", "change", "delete"}`.
- **Dependencies**: `_ProbeRequest`, `_PermissiveUser`.
- **Behavior**: `view` is unconditional — registering a model on a console states that the console may look at it. The other three are asked of the ModelAdmin using a stub request whose user answers True to every permission check, so the answer reflects the ModelAdmin's own policy with the permission layer taken out of the picture.
- **Side Effects**: None.
- **DSA Used**: Set accumulation; four constant-time calls per model.
- **Data Analysis Notes**: This is why append-only and webhook-owned models come back view-only without being named anywhere in the command: `StockMovement`, `Reservation`, `Payment`, and `LogEntry` all override these hooks to return False.
- **Responsive & Accessibility Notes**: None.
- **Security Notes**: The stub grants permissions only to probe the ModelAdmin. It never touches a request path and is never used for authorization.

## Function: permissions_for_site(site)
- **Purpose**: Resolve one console's registry to concrete `Permission` rows.
- **Inputs**:
  - `site` (`AdminSite`): The console to read.
- **Outputs**: `tuple[list[Permission], list[str]]` — the grants, and any codenames that do not exist yet.
- **Dependencies**: `ContentType.objects.get_for_model`, `Permission`, `allowed_actions`.
- **Behavior**: Builds `(content_type_id, codename)` pairs for every registered model times allowed action, queries the two columns with `__in`, then re-pairs the results exactly.
- **Side Effects**: None.
- **DSA Used**: One bulk query instead of N per-permission lookups; results are indexed into a dict keyed by the pair, giving O(1) reassembly. `ContentType.objects.get_for_model` is itself cached per process.
- **Data Analysis Notes**: The exact re-pairing matters — filtering `content_type_id__in` and `codename__in` independently is a cross product and would over-match wherever two models share a codename.
- **Responsive & Accessibility Notes**: None.
- **Security Notes**: A codename missing because `post_migrate` has not run yet is reported, not raised on: the remaining grants are still correct and a later `migrate` completes the set. Silently granting nothing would be worse than saying so.

## Function: Command._sync_group(self, role, site, dry_run)
- **Purpose**: Make one group's permissions equal to its console's derived set.
- **Inputs**:
  - `role` (`StaffRole`): Which group to write.
  - `site` (`AdminSite`): The console to derive from.
  - `dry_run` (`bool`): Report only.
- **Outputs**: `None`; prints an added/removed summary.
- **Dependencies**: `Group`, `permissions_for_site`.
- **Behavior**: `get_or_create`s the group, then uses `.set(permissions)` rather than `.add(...)`.
- **Side Effects**: Rewrites `auth_group_permissions` for the two managed groups only.
- **DSA Used**: Set difference against the existing grants to report the delta without a second query.
- **Data Analysis Notes**: `.set()` is the whole point — a model that moved to the other console loses its grant here, which a bare `.add()` would never do.
- **Responsive & Accessibility Notes**: None.
- **Security Notes**: Only the two groups named in `GROUP_NAMES` are touched; any other group in the database is left completely alone.

## Function: Command._sync_memberships(self, dry_run)
- **Purpose**: Put every staff account in its console's group, and only that one.
- **Inputs**:
  - `dry_run` (`bool`): Report only.
- **Outputs**: `None`; prints per-group membership deltas.
- **Dependencies**: `Group`, `Customer`.
- **Behavior**: Computes target membership per group from `role` plus `is_staff`, diffs it against current membership, and applies additions and removals.
- **Side Effects**: Writes `auth_user_groups` rows for the two managed groups.
- **DSA Used**: Two set differences over primary keys pulled with `values_list`, so no model instances are loaded to compute the diff.
- **Data Analysis Notes**: Non-staff accounts are removed from both groups even when their `role` still says "merchant" — without staff status they open nothing, and a dormant grant is the kind of thing that becomes live again by accident.
- **Responsive & Accessibility Notes**: None.
- **Security Notes**: Roles are mutually exclusive, so a re-roled merchant must not keep an Administrators membership from a previous role.

# Module / File: apps/accounts/management/commands/create_console_account.py

## Function: Command.handle(self, *args, **options)
- **Purpose**: Create or re-role a scoped, non-superuser console account.
- **Inputs**:
  - `--role` (`str`): `merchant` or `administrator`.
  - `--email` (`str`): Login email.
  - `--name` (`str`): Optional display name; defaults to the email local part.
  - `--password` (`str | None`): Falls back to `METRODRIP_CONSOLE_PASSWORD`, then an interactive prompt.
- **Outputs**: `None`; prints the resulting role, console path, and the follow-up `sync_console_roles` reminder.
- **Dependencies**: `Customer`, `StaffRole`, `validate_password`, `transaction.atomic`.
- **Behavior**: Normalises and lower-cases the email. Creates the account as `is_staff=True, is_superuser=False` with the requested role, or updates an existing account's role, staff, and active flags. Raises `CommandError` when asked to scope a superuser. The password is written only when one is supplied, so re-running purely to change a role does not require it.
- **Side Effects**: Inserts or updates one `Customer` row inside one transaction.
- **DSA Used**: None.
- **Data Analysis Notes**: Idempotent by email, so it is safe inside a setup script.
- **Responsive & Accessibility Notes**: None.
- **Security Notes**: Exists because `createsuperuser` only makes superusers, and a superuser reaches both consoles — using it is the fastest way to accidentally prove nothing about the separation. Passwords go through `AUTH_PASSWORD_VALIDATORS`: console accounts are the highest-value credentials in the system and are not waved through because a management command created them. Scoping an existing superuser is refused rather than silently writing a misleading role.

# Module / File: tests/test_console_separation.py

## Function: N/A — console boundary regression contract
- **Purpose**: Make the administrator/merchant separation falsifiable.
- **Inputs**:
  - `admin.site` and `merchant_site` registries, plus real HTTP sessions via the Django test client.
- **Outputs**: 65 tests across seven classes.
- **Dependencies**: pytest, pytest-django, real MySQL.
- **Behavior**: `TestRegistrySeparation` asserts disjoint ownership per model. `TestConsoleAccess` drives both consoles with real logins, including suspension and staff revocation mid-session. `TestLoginBoundary` pins the wrong-console rejection and the absence of the redirect loop. `TestPrivilegeEscalation` covers the superuser-only privilege tier, the self-lockout guard, audit-trail writing, and password-hash exclusion from CSV. `TestRolePermissionSync` and `TestCreateConsoleAccount` cover the two commands. `TestRoleModel` covers the `console` predicate and the data migration's promotion rule. `TestHomepageCacheIsolation` covers ADR-C-004.
- **Side Effects**: Creates and destroys test-database rows.
- **DSA Used**: Set intersection for the disjointness assertion.
- **Data Analysis Notes**: The guarded failure mode is not "a page 500s" — it is a model quietly appearing on both consoles, or a role check a signed-in merchant walks straight through.
- **Responsive & Accessibility Notes**: Two tests assert no raw template syntax reaches the browser on the denial page.
- **Security Notes**: `TestHomepageCacheIsolation` installs a real `LocMemCache` through a fixture, because the suite's settings use `DummyCache`, under which every page-cache assertion passes whether the bug is present or not. All three of its tests were verified to fail with `@vary_on_cookie` removed.

# Module / File: Cycle 2 — console separation

## Function: N/A — Cycle 2 QA gate
- **Purpose**: Record the post-change acceptance evidence for the administrator/merchant console separation.
- **Inputs**:
  - `Cycle 2 change set` (`git worktree`): Two admin sites, `Customer.role` plus migration `accounts.0002`, re-pointed registrations across nine apps, two management commands, the wrong-console page, the storefront console shortcut, and the homepage cache fix.
  - `local services` (`Docker Desktop, MySQL 8.4`): Real database plus a live `runserver` instance on port 8123.
- **Outputs**: `QA_PASSED`.
- **Dependencies**: Python 3.14.4, Django 5.2.16, Ruff, pytest 8.4.2, requests.
- **Behavior**: 388 tests pass against real MySQL, up from 323. `ruff check` and `ruff format --check` are clean across 106 files; `compileall` is clean; `manage.py check` reports no issues; `makemigrations --check --dry-run` reports no drift; `check --deploy --fail-level WARNING` under staging settings reports no issues, 1 silenced. `accounts.0002_customer_role` was verified forward, reverse, and forward again on a throwaway database, and its data migration was verified against rows inserted at the 0001 schema: a pre-existing `is_staff` row lands on `administrator` and keeps console access, a shopper row stays `customer`. Registry inspection confirms 6 administrator models, 12 merchant models, and an empty intersection. Live-server checks confirm both login pages render their own heading, a merchant reaches all 12 merchant model pages, `/merchant/accounts/customer/` returns 404, `/admin/accounts/customer/` returns 302 then 403 with no customer data in the body, merchant credentials are refused at `/admin/login/` with an explanatory message rather than a redirect loop, and the storefront navbar shows the console shortcut to staff only. The three homepage-cache tests were each confirmed to fail with the fix removed.
- **Side Effects**: Applied `accounts.0002_customer_role` to the local development database; created the `Merchants` and `Administrators` groups with 36 and 19 permissions and a demo merchant account `seller@metrodrip.test`; created and destroyed throwaway test databases. No public deployment was changed.

## Function: N/A — Sprint P3/P4 capabilities updates
- **Purpose**: Log the changes made during the P3 and P4 sprint execution.
- **Inputs**: None
- **Outputs**: None
- **Dependencies**: Redis, FastAPI
- **Behavior**: The inventory service was successfully extracted to a standalone FastAPI microservice using the Strangler Fig pattern. Read/write operations from Django are bridged over HTTP and Redis Pub/Sub events. The UI design system (colors, focus states) was made consistent and accessible (WCAG AA). Missing loading and error states for the AlpineJS cart component were implemented, and the missing product images were correctly wired from the catalog through the JS cart representation.
- **Side Effects**: Reduced monolithic complexity, decoupled the catalog from inventory management in anticipation of separate scaling characteristics.


## Sprint H — Mobile Application and Public API (2026-08-01)

- **Purpose:** Document the public mobile surface and the React Native client added by the v1.3 Planning Addendum.
- **Inputs:** Mobile HTTP requests carrying `X-Client-Version` and (mostly) a JWT bearer token.
- **Outputs:** JSON payloads whose money fields are integer centavos **plus** a server-formatted display string.
- **Dependencies:** DRF, SimpleJWT (rotation + blacklist), the existing domain services, Expo SDK 51.
- **Behavior:** The API is a second consumer of the same services the web storefront uses; the app computes nothing (addendum D-13).

### Module: `apps/mobile_api/views.py`

- **Purpose:** All `/api/mobile/v1/` endpoints: auth, catalog, cart validation, checkout, orders, account, wishlist, reviews, devices, notification centre.
- **Inputs:** JSON bodies of user intent (ids, quantities, contact block, zone id, credentials).
- **Outputs:** Server-computed payloads; `{"error": {...}}` envelopes on failure.
- **Dependencies:** `apps.orders.checkout.place_order`, `apps.payments.services.confirm_order_paid`, `apps.catalog.services`, `apps.inventory.services.get_stock_record`.
- **Behavior:** Guest checkout needs no token. Order detail scopes to `customer=request.user`, so another shopper's order number returns 404. `SimulatedPaymentConfirmView` returns 404 unless `PAYMENT_PROVIDER == "simulated"` (ADR-H-003). The tracking timeline is derived server-side from the order state machine (FR-26).

### Module: `apps/mobile_api/middleware.py`, `errors.py`, `pagination.py`

- **Purpose:** Enforce the NFR-22 version header, the documented error schema, and the NFR-18 page cap.
- **Inputs:** Any request under `/api/mobile/`; any DRF exception; any list response.
- **Outputs:** 400 `missing_client_version`; `{"error": {"code", "message", "fields?"}}`; pages of at most 20 items.
- **Dependencies:** DRF exception handler hook and `PageNumberPagination`.
- **Behavior:** `max_page_size` equals `page_size`, so `?page_size=` cannot be used to exceed the cap.

### Module: `apps/orders/checkout.py`

- **Purpose:** The single checkout implementation shared by web and mobile (ADR-H-002).
- **Inputs:** Cart lines, zone id, contact block, optional customer, success/cancel URLs.
- **Outputs:** `(order, checkout_url)`; raises `CheckoutError` (400), `InsufficientStock` (409), `PaymentSessionError` (502, holds already released).
- **Dependencies:** Catalog variants, inventory reservations, order numbering, the payment provider registry.
- **Behavior:** One atomic block — effective variant prices, totals correct at INSERT, order-linked holds, order items. Retries up to three times on MySQL deadlock 1213 (the victim transaction rolled back fully). A `__TOKEN__` placeholder in a redirect URL is substituted with the signed status token after the order row exists.

### Module: `apps/notifications/push.py` and `models.py`

- **Purpose:** FR-27 push fan-out and FR-28 notification-centre persistence.
- **Inputs:** Order transitions, shipment status changes, registered Expo device tokens.
- **Outputs:** `Notification` rows and Expo push messages; `DeviceToken` per install.
- **Dependencies:** `PUSH_PROVIDER` (`simulated` or `expo`), `transaction.on_commit`.
- **Behavior:** Hooked into `Order.transition_to()` and `Shipment.save()`; every failure is logged and swallowed so delivery can never fail a business transition. Guest orders are skipped.

### Client: `mobile/`

- **Purpose:** The iOS/Android customer app, 11 screens matching the Figma frames one-to-one.
- **Inputs:** `/api/mobile/v1/`, the OS colour scheme, biometric enrolment, push permission.
- **Outputs:** Rendered screens, server-validated checkout, deep links back from the payment flow.
- **Dependencies:** Expo SDK 51, React Navigation 6, `expo-secure-store`, `expo-local-authentication`, `expo-notifications`.
- **Behavior:** `src/theme/theme.ts` is the only file containing colour literals (grep-verified). Money is never computed on-device (grep-verified). JWTs live only in the OS keychain. `src/api/client.ts` transparently refreshes an expired access token once then replays the request; a network failure raises `OfflineError`, which screens render as the FR-30 offline banner over cached content.

| Screen | Figma frame | Node |
|---|---|---|
| `SplashScreen` | M01 Splash and Onboarding | `63:3` |
| `HomeScreen` | M02 Home (Tab) | `63:67` |
| `ShopScreen` | M03 Shop and Search (Tab) | `63:155` |
| `ProductDetailScreen` | M04 Product Detail | `64:2` |
| `CartScreen` | M05 Cart | `64:74` |
| `CheckoutScreen` | M06 Checkout | `64:152` |
| `OrderTrackingScreen` | M07 Order Tracking | `65:2` |
| `NotificationsScreen` | M08 Notifications | `65:83` |
| `AccountScreen` | M09 Account | `65:155` |
| `AuthScreen` | M10 Sign In / Register | `67:2` |
| `WishlistScreen` | M11 Saved / Wishlist | `67:45` |

### Test Module: `tests/test_mobile_api.py`

- **Purpose:** Pin the Epic H contracts including the M7 QA gate.
- **Inputs:** Real MySQL, version-header clients, 20 concurrent checkout threads.
- **Outputs:** 19 passing cases.
- **Dependencies:** pytest-django, `override_settings`, the simulated payment provider.
- **Behavior:** Covers the missing-version-header 400, anonymous 401, credential 429, register/login/refresh/logout with refresh-token blacklisting, guest-order claiming on registration, password reset round-trip, the 20-item page cap, server-priced cart validation, tamper-proof checkout (client prices ignored), 409 rollback, gated and idempotent simulated confirmation, **20 parallel API buyers against 10 units producing exactly 10 orders**, tracking timeline states, cross-customer order 404, wishlist toggle, the verified-purchase review rule, and device registration plus notification-centre read state.

### Regression: inventory provider registry

- **Purpose:** Record why `apps/inventory/services.py` became a facade (ADR-P3-002).
- **Inputs:** The state of `main` before this sprint.
- **Outputs:** `providers/local.py` (default) and `providers/service.py` (opt-in).
- **Dependencies:** `INVENTORY_PROVIDER` setting.
- **Behavior:** The microservice extraction had replaced the row-locked implementation outright, leaving `adjust_stock`, `release_expired_reservations`, and `scan_low_stock` as stubs and making commits/releases fire-and-forget. 19 tests including the M2 no-oversell gate were failing. The proven Epic B code is restored as the default provider; the service client is preserved verbatim behind an explicit opt-in.

### QA gate — Sprint H

| Check | Command | Result |
|---|---|---|
| Ruff lint | `.venv/Scripts/ruff check .` | Passed |
| Ruff format | `.venv/Scripts/ruff format --check .` | Passed; 139 files |
| Django system check | `manage.py check` | Passed; 0 issues |
| Migration drift | `manage.py makemigrations --check --dry-run` | Passed; no changes |
| Backend tests | `.venv/Scripts/pytest -q` | Passed; 407 on MySQL 8 |
| Mobile typecheck | `npx tsc --noEmit` | Passed; 0 errors |
| No on-device money math | grep for arithmetic on price/total/fee in `mobile/src` | Passed; comments only |
| No hardcoded hex | grep for `#RRGGBB` in `mobile/src` | Passed; `theme.ts` only |

## Sprint I — Fulfillment completion and printable documents (2026-08-02)

- **Purpose:** Record the courier webhook, the FR-19 documents, and the FR-9 dashboard flag.
- **Inputs:** Carrier status callbacks; merchant and customer print requests; merchant stock list views.
- **Outputs:** Shipment/order state transitions, two printable HTML documents, a low-stock filter and badge.
- **Dependencies:** `COURIER_WEBHOOK_SECRET`, the order state machine, `OrderItem.line_total`.
- **Behavior:** Closes the second inbound webhook required by section 7 and the remaining half of FR-19.

### Module: `apps/shipping/webhooks.py`

- **Purpose:** `/api/webhooks/courier/` — the second inbound webhook (section 7).
- **Inputs:** POST with `{waybill_no, status}` and an `X-Courier-Signature` HMAC-SHA256 header over the raw body.
- **Outputs:** 400 (bad/missing signature, malformed body, missing fields); 200 (applied, replayed, unknown waybill, or unmapped status).
- **Dependencies:** `COURIER_WEBHOOK_SECRET`, `Shipment`, `Order.transition_to`.
- **Behavior:** Fails closed with no secret configured. Normalizes carrier vocabulary through `COURIER_STATUS_MAP`. Only `delivered` advances the order state machine; `out_for_delivery` sets shipment status, which fires FR-27's fourth push through `Shipment.save()`. An `IllegalTransition` (e.g. the order was already refunded) is logged, not raised.

### Property: `OrderItem.line_total`

- **Purpose:** Exact line total in integer centavos (Hard Invariant 2).
- **Inputs:** `unit_price_snapshot`, `qty`.
- **Outputs:** Integer centavos.
- **Dependencies:** None.
- **Behavior:** Replaces a `widthratio` template calculation that did integer division and rounded — ₱899.50 × 3 printed as ₱2,697 instead of ₱2,698.50. Templates must never multiply money.

### Views: printable documents (FR-19)

- **Purpose:** Packing slip for the warehouse; invoice for the customer.
- **Inputs:** `OrderAdmin.packing_slip_view` (merchant console, by order id); `storefront.views.order_invoice` (signed token).
- **Outputs:** `admin/orders/order/packing_slip.html` and `storefront/invoice.html`, both print-styled.
- **Dependencies:** Signed-token authorization (ADR-D-004) for the customer copy.
- **Behavior:** The packing slip carries SKU, attributes, quantity, tick boxes, and the waybill, and shows **no prices**. The customer invoice is standalone (does not extend `base.html`) and is linked from both order history and the tokenized status page, so guests can print one too.

### Admin: low-stock flag (FR-9)

- **Purpose:** The dashboard leg of the low-stock requirement.
- **Inputs:** Merchant console StockRecord list.
- **Outputs:** A `LowStockFilter` ("Low stock" / "Healthy") and an OUT / LOW / OK badge column.
- **Dependencies:** `available_units` annotation on the admin queryset.
- **Behavior:** Compares availability (on hand minus reserved), matching the scan job — shelf count alone would hide units already promised to holds. The badge spells the state out in words, so colour is not the only cue.

### Test Module: `tests/test_fulfillment_docs.py`

- **Purpose:** Pin the courier webhook and the FR-19 documents.
- **Outputs:** 9 passing cases.
- **Behavior:** Covers status advance to Delivered, replay idempotency, bad/missing signature rejection, fail-closed with no secret, acknowledged unknown waybill and unmapped status, exact centavo line totals, invoice rendering and token requirement, and that the packing slip contains no prices.

### QA gate — Sprint I

| Check | Command | Result |
|---|---|---|
| Ruff lint + format | `ruff check .` / `ruff format --check .` | Passed |
| Backend tests | `pytest -q` | Passed; 416 on MySQL 8 |
| Web route sweep | 13 public routes probed on a live server | All 200 |
| Mobile API journey | register to checkout to track, live server | 23/23 |
| Fulfillment lifecycle | pack, ship, out-for-delivery, deliver, refund, CSV, invoice | 13/13 |

### Gap inventory — amended after Sprint I (2026-08-02)

Closed by this sprint (previously listed as outstanding):

- Second inbound webhook (section 7): `/api/webhooks/courier/` now exists, signature-verified and idempotent.
- FR-19 in full: packing slip (merchant) and customer-facing invoice (tokenized) both ship; line totals are exact centavos.
- FR-9 dashboard leg: low-stock filter and OUT/LOW/OK badge on the merchant stock list.

Still outstanding, unchanged:

- Email verification on registration and web password reset (the **mobile** reset flow is complete; the web one is not).
- Saved-address CRUD and checkout prefill; the `addresses` JSON field exists and is returned by the API but has no editing UI.
- Geocoded zone auto-detection (FR-13): Places fills address/city; server mapper auto-selects zone (dropdown remains fallback). See apps/shipping/zones.py.
- Admin 2FA and login rate limiting (F-2). DRF throttling covers the mobile API only.
- Real PayMongo and J&T credentials: both live-API branches are written against documented contracts but unverified against real endpoints.
- Public staging evidence (M1): host, DNS, and trusted certificate remain operator actions.
- Catalog data quality: `seed_assignment.py` / `seed_more.py` have padded the dev database to ~156 products with placeholder copy. `seed_demo` (the canonical five, ADR-A-012) is unaffected, but a demo database should be reseeded from `seed_demo` alone.


# Module / File: services/notifications/main.py
## Function: FastAPI notifications delivery service
- **Purpose**: Opt-in outbound email/SMS/push delivery sidecar (Phase 3 strangler).
- **Inputs**: POST /v1/email|sms|push JSON DTOs + optional Bearer token
- **Outputs**: {delivered, mode}; /healthz/live and /healthz/ready
- **Dependencies**: requests, SMTP/Semaphore/Expo when configured
- **Behavior**: simulated when credentials absent; auth default-deny when NOTIFICATION_SERVICE_TOKEN set
- **Side Effects**: external network I/O when configured
- **DSA Used**: n/a
- **Data Analysis Notes**: no DB — inbox stays in Django
- **Responsive & Accessibility Notes**: n/a
- **Security Notes**: service token; no card/PII beyond email/phone in payload

# Module / File: apps/notifications/providers/http.py
## Function: HttpNotificationProvider
- **Purpose**: Django adapter posting DTOs to notifications service when NOTIFICATION_PROVIDER=http
- **Inputs**: same facade as email_sms/console
- **Outputs**: bool success; never raises
- **Dependencies**: requests, NOTIFICATION_SERVICE_URL/TOKEN, correlation id
- **Behavior**: log+False on transport/4xx/5xx so checkout is never blocked
- **Side Effects**: HTTP POST
- **DSA Used**: n/a
- **Data Analysis Notes**: n/a
- **Responsive & Accessibility Notes**: n/a
- **Security Notes**: Bearer token; enhancement-tier only

# Module / File: static/css/storefront.css
## Function: design tokens (Phase 5)
- **Purpose**: WCAG AA palette + dark mode; volt/on-volt/accent-text rules
- **Inputs**: data-theme, prefers-color-scheme
- **Outputs**: CSS custom properties
- **Dependencies**: templates/base.html theme toggle
- **Behavior**: light tokens + dark overrides; ink bands → elevated in dark
- **Side Effects**: none
- **DSA Used**: n/a
- **Data Analysis Notes**: muted #63635C, danger #C2282D contrast on white
- **Responsive & Accessibility Notes**: theme toggle ≥44×44; focus-visible volt ring
- **Security Notes**: n/a

# Module / File: seed_200.py
## Function: run
- **Purpose**: Generates logically suitable subcategories for existing root categories and fills them with placeholder products until exactly 200 products exist per root category.
- **Inputs**: None.
- **Outputs**: None (script execution).
- **Dependencies**: apps.catalog.models (Category, Product, ProductVariant, Size, Fit), apps.inventory.models (StockRecord).
- **Behavior**: Retrieves all root categories, creates Men/Women/Unisex subcategories if missing, counts existing products, and bulk-inserts new placeholder products to hit exactly 200 items per root. Also creates 1 variant and 1 stock record per new product.
- **Side Effects**: Modifies the MySQL database via Django ORM.
- **DSA Used**: O(N) generation iteration per root category; O(1) bulk_create operations minimizing database roundtrips.
- **Data Analysis Notes**: The script accurately computes 
eeded = 200 - current_count dynamically to prevent over-seeding on reruns.
- **Responsive & Accessibility Notes**: N/A
- **Security Notes**: Development/seeding utility only; should not run in production.

# Module / File: seed_collections.py
## Function: run
- **Purpose**: Generates curated collection categories (New Arrivals, Best-Sellers, On-Sale, Pre-Order) and seeds 200 placeholder products for each.
- **Inputs**: None.
- **Outputs**: None (script execution).
- **Dependencies**: apps.catalog.models (Category, Product, ProductVariant, Size, Fit), apps.inventory.models (StockRecord).
- **Behavior**: Iterates over hardcoded collections, creates the root categories, computes required product count, and bulk-inserts items. Applies static discount logic to "On-Sale" and sets 0 initial stock for "Pre-Order".
- **Side Effects**: Modifies the MySQL database via Django ORM.
- **DSA Used**: O(N) generation loop with bulk database operations.
- **Data Analysis Notes**: Avoids dynamic discount calculations by setting a lowered ase_price explicitly during generation, aligning with invariant #2 (no client-side price math).
- **Responsive & Accessibility Notes**: N/A
- **Security Notes**: Development/seeding utility only; should not run in production.


# Module / File: apps/payments/holds.py

## Function: consume_order_holds
- **Purpose**: Commit every active hold on an order and cover any shortfall.
- **Inputs**:
  - order (Order): The order containing the active stock holds.
- **Outputs**: dict[int, int] mapping variant_id to the actually committed quantity.
- **Dependencies**: pps.inventory.services.commit_holds, pps.orders.outbox.enqueue, pps.orders.models.StockHoldState.
- **Behavior**: Groups active stock holds by checkout_id. For each unique checkout_id, enqueues an outbox message and calls commit_holds. On success, retires the outbox message and updates all holds for that checkout_id to COMMITTED. If commit_holds throws ReservationUnavailable, the state is set to UNKNOWN and left for the outbox retry worker. Finally, calls _cover_shortfall to ensure the required items are reserved if they expired.
- **Side Effects**: Modifies StockHold states in DB, pushes messages to OutboxMessage, delegates to inventory service which writes StockMovement rows.
- **DSA Used**: O(H) time where H is number of active holds to group them by checkout_id, avoiding N+1 HTTP calls.
- **Data Analysis Notes**: N/A
- **Responsive & Accessibility Notes**: N/A
- **Security Notes**: Outbox pattern protects against distributed transaction failure between payment system and inventory ledger.
- **Verification Status**: Tested manually via latency measurement script; verified the fix reduces N+1 HTTP calls to O(1) per checkout group.
