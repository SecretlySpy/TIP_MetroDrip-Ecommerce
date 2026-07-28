# Module / File: Repository architecture and current delivery state

## Function: N/A — runtime architecture contract
- **Purpose**: Describe the deployed shape, ownership boundaries, and principal dependencies of the MetroDrip application.
- **Inputs**:
  - `HTTP request` (`django.http.HttpRequest`): Browser, admin, health-probe, or PayMongo webhook traffic.
  - `scheduled invocation` (`APScheduler job`): Reservation-expiry and low-stock work.
- **Outputs**: HTML responses, narrow JSON responses, provider acknowledgements, email/SMS attempts, and transactional MySQL state.
- **Dependencies**: Python 3.14, Django 5.2, MySQL 8.4/InnoDB, Django templates, HTMX 2.0.4, Alpine.js 3.14.9, APScheduler, Gunicorn, WhiteNoise, Caddy, PayMongo, Semaphore, and Google Maps.
- **Behavior**: The repository is one Django modular monolith containing 10 first-party apps (`catalog`, `inventory`, `orders`, `payments`, `shipping`, `notifications`, `accounts`, `reviews`, `cms`, and `storefront`), one MySQL database, and one dedicated scheduler process. Views delegate catalog queries and stock/order/payment mutations to domain services. Direct model relationships cross app boundaries inside the same database. The staging topology is Caddy → Gunicorn/Django → MySQL, with one separate scheduler container using the same image.
- **Side Effects**: This documentation entry performs none; the described runtime writes orders, reservations, payments, shipments, reviews, CMS content, notification logs, and inventory ledger rows.

## Function: N/A — request and data-flow contract
- **Purpose**: Record the principal control flow from storefront input to persisted commerce state.
- **Inputs**:
  - `storefront input` (`HTML form or JSON body`): Search/filter values, cart variant IDs, checkout identity/address data, reviews, and contact messages.
  - `provider event` (`signed JSON body`): PayMongo payment event.
- **Outputs**: Product pages, reservations, pending orders/payments, paid orders, immutable stock movements, fulfillment state, and notifications.
- **Dependencies**: `apps.storefront.views`, `apps.catalog.services`, `apps.inventory.services`, `apps.orders.services`, `apps.payments.services`, and the Django ORM.
- **Behavior**: Catalog reads annotate active products and approved reviews. Checkout parses a client-side cart, reloads authoritative variants/prices, allocates an order number, creates the order and lines, and reserves stock inside one transaction. Hosted checkout creation then creates a pending Payment. In deployment, only a signature-verified PayMongo webhook calls `confirm_order_paid`; development can use the explicitly gated mock path. Confirmation locks the Payment, commits the order’s reservations, writes sale movements, and transitions the Order to Paid. Admin actions drive later order transitions and fulfillment side effects.
- **Side Effects**: Creates and updates commerce rows, obtains InnoDB row locks, calls PayMongo/Semaphore/email adapters, and writes logs.

## Function: N/A — implemented capability inventory
- **Purpose**: Enumerate the capabilities present at the Cycle 1 baseline.
- **Inputs**:
  - `repository source` (`filesystem tree`): Application, templates, assets, migrations, tests, and deployment configuration.
- **Outputs**: A machine-readable implementation boundary for later cycles.
- **Dependencies**: All modules documented below.
- **Behavior**: Implemented capabilities include email-based Django authentication; customer profiles; order history; guest-order claiming; wishlists; a CMS banner/contact/flatpage layer; product/category/three-axis variants; catalog search/filter/sort; localStorage cart; stock availability checks; atomic checkout holds; integer-centavo money; hosted/mock payment checkout; signed webhook confirmation; tokenized order pages; order state enforcement; inventory reservation/ledger services; scheduler jobs; shipping-zone rates; mock J&T booking; review moderation; admin reports/invoices/CSV actions; container health probes; and provider-neutral local HTTPS staging.
- **Side Effects**: None.

## Function: N/A — known implementation-gap inventory
- **Purpose**: Prevent requested future behavior from being reported as delivered.
- **Inputs**:
  - `project plan` (`MetroDrip_Project_Plan_UIUX_AI_Prompt.md`): Requested target state.
  - `current source` (`repository revision 653324fc3af66263cdc5da1135e442d6a7d8a50d` plus Cycle 1 worktree): Verified implementation state.
- **Outputs**: Explicit continuation boundary.
- **Dependencies**: Future architecture, catalog, identity, commerce, accessibility, and deployment cycles.
- **Behavior**: The canonical seed still contains 5 products rather than the requested deterministic 45-product rich catalog. Product media/specification entities, verified email, password reset, saved-address CRUD/prefill, stronger order-claim proof, comprehensive server-side checkout forms, timestamp-fresh webhook validation, atomic fulfillment/refund orchestration, deterministic courier simulation, notification templates/preferences, Developers page, approved design-token rollout, WCAG/browser QA, and the target five-service topology are not complete. Public DNS, trusted certificate, external URL, and uptime evidence require operator infrastructure. Five higher-precedence course/Phase 1 documents referenced by the supplied plan are absent, so exact FR/NFR traceability cannot yet be claimed.
- **Side Effects**: None.

## Function: N/A — Cycle 1 QA gate
- **Purpose**: Record the post-change acceptance evidence for the 2026-07-27 foundation cycle.
- **Inputs**:
  - `Cycle 1 change set` (`git worktree`): Banner rendering fix, migration enforcement, CI compilation step, and regression tests.
  - `local services` (`Docker Desktop and MySQL 8.4.10`): Real database and disposable HTTPS stack.
- **Outputs**: `QA_PASSED`.
- **Dependencies**: Python 3.14.4, Ruff 0.15.22, pytest 8.4.2, Django 5.2.16, Docker 28.5.1, and Compose 2.40.2.
- **Behavior**: `compileall`, Ruff lint, Ruff formatting, `uv pip check`, Django system checks, migration drift, warning-level staging checks, local/staging Compose validation, Dockerfile checks, image build/ownership checks, and 276 real-MySQL tests passed. `catalog.0002_enforce_mysql_defaults` passed forward → reverse → forward. Metadata reported database defaults `utf8mb4/utf8mb4_0900_ai_ci` and zero noncompliant tables. A disposable Caddy/Gunicorn/MySQL/scheduler stack returned readiness 200, admin 302, static 200, rendered the seeded banner URL, retained `5/180/180/180/1` product/variant/stock/movement/banner counts after forced recreation, and was removed with its disposable volumes.
- **Side Effects**: Applied `catalog.0002_enforce_mysql_defaults` to the local development database, built local test images, and created then removed the isolated `metrodrip-cycle1` staging stack; no public deployment was changed or proven.

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
- **Dependencies**: `CustomerManager._create`.
- **Behavior**: Defaults both privilege flags true and rejects missing passwords or false privilege overrides.
- **Side Effects**: Inserts one customer row.

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
- **Purpose**: End the current authenticated session.
- **Inputs**:
  - `request` (`HttpRequest`): POST request.
- **Outputs**: Redirect to storefront home.
- **Dependencies**: Django `logout` and `require_POST`.
- **Behavior**: Clears the current session identity and redirects.
- **Side Effects**: Mutates/deletes session authentication data.

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

# Module / File: apps/orders/money.py

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
- **Behavior**: Pages serves static files only and executes no application code, so the Django storefront cannot be hosted there; the guide states this explicitly rather than implying a broken deployment. Empty `.nojekyll` disables the Jekyll build, which would otherwise pass tracked Markdown containing Django template tags through Liquid. Documentation links target GitHub's blob view because Pages serves sibling `.md` files as raw text. Platform-specific commands are switched by one radio group at the top of `.osroot` using CSS sibling selectors, so the guide works without JavaScript; `.only-win|mac|linux` toggle `display:block` and `.only-win-i|mac-i|linux-i` toggle `display:inline` for OS-specific words mid-sentence. Inline `style` attributes must never be used on these classes — they defeat the `display:none` default and reveal all three platforms simultaneously. The single script adds clipboard buttons as progressive enhancement. An inline SVG renders the browser → Django → MySQL topology with a `<title>`/`<desc>` pair for screen readers. Six `<figure>` elements hold dashed placeholders naming their expected `docs/images/` file; `docs/images/README.md` records the capture list, sizing conventions, redaction rules, and the markup swap for replacing a placeholder with a real image.
- **Side Effects**: Publishes a public page at the repository's Pages URL on push to `main`.

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
