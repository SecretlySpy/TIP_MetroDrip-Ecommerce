# AI Documentation Notes

## Document Metadata

- **Purpose:** Provide a machine-readable technical reference for the implemented MetroDrip codebase.
- **Inputs:** Repository source, migrations, settings, tests, `MetroDrip_AI_Handover.md`, and `DECISIONS.md`.
- **Outputs:** Current architecture, callable contracts, data model, control flow, dependency map, QA evidence, and implementation gaps.
- **Dependencies:** Post-change QA must pass before this document is regenerated.
- **Behavior:** Describes implemented behavior literally; planned behavior is labeled as not implemented.
- **Analysis Date:** 2026-07-18.
- **Implementation Stage:** Tasks A-1 through A-3 are complete. A-4 code, deployment artifacts, local HTTPS smoke, and operations documentation are complete; the M1 public-host/DNS/trusted-certificate gate remains pending.
- **QA Gate:** Passed with 182 tests passed, 1 intentional strict XFAIL, reversible migrations, warning-level deployment checks, and a successful rebuilt forced-recreation Docker HTTPS smoke test.

## Repository Scope

- **Purpose:** Define the current deployable system boundary.
- **Inputs:** Django project, 10 first-party app packages, MySQL schema, Docker development and staging services, deployment runbook, and CI workflow.
- **Outputs:** One server-rendered Django monolith backed by one MySQL 8 database; provider-neutral staging image and Compose topology.
- **Dependencies:** Python 3.14, Django 5.2, MySQL 8, PyMySQL, Gunicorn, WhiteNoise, Caddy, Docker Compose, and environment configuration.
- **Behavior:** Active routes are `/admin/`, process/database health probes, and a staging-gated seed preview. Public commerce, account, webhook, and provider-integration routes are not implemented.

### Technology Stack

- **Purpose:** Enumerate implemented runtime and QA technologies.
- **Inputs:** Requirements, container images, settings, and verified installed versions.
- **Outputs:** Dependency and current-behavior matrix.
- **Dependencies:** Python, pip, Docker, and MySQL.
- **Behavior:** Distinguishes installed behavior from planned integrations.

| Layer | Implemented dependency | Current behavior |
|---|---|---|
| Language | Python 3.14 | Local virtual environment uses Python 3.14.4. |
| Framework | Django 5.2 | Installed version during QA was 5.2.16. |
| Database | MySQL 8 | Docker QA server uses MySQL 8.4.10, InnoDB, and `utf8mb4_0900_ai_ci`. |
| Driver | PyMySQL | Installed as the `MySQLdb` compatibility module before Django initializes. |
| HTTP server | Gunicorn 26 | Staging runs one non-root worker with four threads. |
| Reverse proxy | Caddy 2 | Sole public ingress; automatic HTTPS, compression, response headers, and proxy logging. |
| Static assets | WhiteNoise 6 | Serves hashed collected admin/site assets; never product media. |
| Jobs | APScheduler | Dependency installed; no jobs or scheduler startup exists. |
| Frontend | Django Templates | Temporary staging seed template exists; commerce templates, HTMX, and Alpine.js are absent. |
| Tests | pytest and pytest-django | Tests execute against real MySQL rather than SQLite. |
| Lint and format | Ruff | Lint and formatting checks pass. |
| CI | GitHub Actions | Runs Ruff, format, migration drift/reversal, pytest/MySQL, warning-level deployment checks, shell/Compose/Caddy/Docker validation, image ownership checks, and a disposable HTTPS persistence smoke. |

### Implemented Capability Matrix

- **Purpose:** Summarize delivered feature boundaries.
- **Inputs:** Current source, migrations, tests, and deployment evidence.
- **Outputs:** Capability and implementation-status matrix.
- **Dependencies:** All implemented modules and deployment artifacts.
- **Behavior:** Labels partial and absent behavior explicitly.

| Capability | Status | Literal behavior |
|---|---|---|
| Project scaffold | Implemented | Split settings, 10 app packages, Docker MySQL, pytest, Ruff, and CI exist. |
| Customer identity | Schema-ready | Email is the login identifier; guest checkout has no Customer row. |
| Catalog | Data layer implemented | Categories, products, and Size × Color × Fit variants persist through Django ORM. |
| Effective pricing | Implemented | Variant override wins; otherwise the product base price is returned. |
| Money validation and arithmetic | Implemented | Strict integer-only validation, overflow guards, exact multiplication/sums, and configured peso formatting exist. |
| Inventory counters | Schema-ready | Availability is on-hand minus reserved; database prevents reserved exceeding on-hand. |
| Stock audit | Partially implemented | Movement rows validate direction and reject normal public ORM mutation/deletion paths. |
| Orders | Core data layer implemented | Order totals, unique order lines, snapshots, numbering, and guarded state transitions exist. |
| Payments | Schema-ready | One payment per order and one globally unique non-null provider reference are supported. |
| Shipping | Schema-ready | One shipment per order with J&T default and tracking fields is supported. |
| Wishlist | Schema-ready | One product bookmark per customer is enforced. |
| Reviews | Schema-ready | Rating and moderation storage exists; verified-purchase validation is absent. |
| Demo data | Implemented | Idempotent command creates 5 products and a complete 180-variant inventory matrix. |
| Operational health | Implemented | Database-independent liveness and `SELECT 1` readiness endpoints return narrow JSON contracts. |
| Staging runtime | Locally implemented; public gate pending | Hardened Caddy/Gunicorn/MySQL Compose stack passes local HTTPS and forced-recreation smoke; no real DNS/host/certificate evidence exists. |
| Seed browser | Implemented for staging only | Feature-gated GET page renders active seeded products, peso prices, and variant totals; all methods return 404 while disabled, while enabled non-GET methods return 405. |
| Storefront and checkout | Not implemented | No commerce listing/detail/cart/reservation/checkout flow exists; the temporary staging page is not the storefront. |
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

### Development Runtime Boot Flow

- **Purpose:** Initialize Django consistently across management, ASGI, and WSGI entrypoints.
- **Inputs:** Process environment, optional repository `.env`, and command-line arguments.
- **Outputs:** Configured Django application.
- **Dependencies:** PyMySQL, python-dotenv, Django settings loader, reachable MySQL.
- **Behavior:** PyMySQL installs as `MySQLdb`; base settings load `.env`; entrypoints default to development settings only when `DJANGO_SETTINGS_MODULE` is unset.

### Staging Deployment Topology

```text
Internet TCP 80 / TCP+UDP 443
              │
          Caddy 2
              │ edge network
    Gunicorn/Django (UID 10001)
              │ internal database network
          MySQL 8.4
              │
       persistent dbdata volume
```

- **Purpose:** Provide the smallest provider-neutral HTTPS staging topology within the launch infrastructure budget.
- **Inputs:** Linux host, Docker Compose, DNS hostname, ports 80/443, deployment environment, repository revision.
- **Outputs:** Caddy ingress, one Gunicorn/Django process container, one private MySQL service, and persistent `dbdata`, `caddy_data`, and `caddy_config` named volumes.
- **Dependencies:** `Dockerfile`, `deploy/compose.staging.yml`, `deploy/Caddyfile`, `deploy/entrypoint.sh`, staging settings.
- **Behavior:** MySQL becomes healthy first; the app validates settings, collects static files, migrates, optionally seeds, and becomes ready; Caddy starts after app readiness and terminates HTTPS. Only Caddy publishes host ports.

### Staging Request Flow

- **Purpose:** Define ingress, health, static, and preview control flow.
- **Inputs:** Public HTTPS request forwarded by Caddy with original Host and HTTPS proxy metadata.
- **Outputs:** JSON health response, WhiteNoise static response, staging preview HTML, admin response, or 404/405.
- **Dependencies:** SecurityMiddleware, WhiteNoise, Gunicorn, Django URL resolver, optional MySQL query.
- **Behavior:** `Client → Caddy → Gunicorn/Django`; liveness stops before database access; readiness executes `SELECT 1`; static files stop in WhiteNoise; seed preview checks its feature gate before method disclosure and then queries active products.

### Staging Startup Flow

- **Purpose:** Prepare an immutable application image before it serves traffic.
- **Inputs:** Exact `STAGING_SEED_DEMO` flag, validated Django/MySQL/host environment, final Gunicorn command.
- **Outputs:** Collected static assets, current schema, optional deterministic seed, running Gunicorn master.
- **Dependencies:** `deploy/entrypoint.sh`, management commands, MySQL readiness.
- **Behavior:** Invalid seed flags exit 64 before mutation. Valid startup runs `collectstatic`, `migrate`, optional idempotent `seed_demo`, then `exec`s Gunicorn. One app replica is an explicit operational constraint.

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

- **Purpose:** Group runtime configuration entrypoints and settings.
- **Inputs:** Process environment and Django startup.
- **Outputs:** Development, test, production, and staging configuration.
- **Dependencies:** Django settings loader.
- **Behavior:** Child sections define each module and callable contract.

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
- **Behavior:** Registers 10 MetroDrip apps; selects MySQL; requests `utf8mb4`; pins session InnoDB and strict transactional SQL mode; sets `AUTH_USER_MODEL = "accounts.Customer"`; uses Asia/Manila display timezone with UTC storage; defines PHP, ₱, and two minor units; sets absolute `/static/`; keeps the staging preview disabled by default.

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

- **Purpose:** Provide fail-fast production security, database, static-asset, and logging settings.
- **Inputs:** Required Django secret, host/origin allowlists, and all application MySQL connection values.
- **Outputs:** Validated settings, HTTPS redirect, secure cookies, proxy SSL handling, 30-day HSTS, WhiteNoise manifest storage, container-captured console logging, and 60-second persistent database connections.
- **Dependencies:** `config.settings.base`, `ipaddress`, `re`, `urllib.parse`, Django, WhiteNoise, and a correctly configured reverse proxy.
- **Behavior:** Import rejects missing/weak/example secrets, missing/weak/example application DB passwords, empty lists, wildcard/non-DNS hosts, malformed ports, and non-origin/non-HTTPS CSRF values. HSTS preload remains intentionally disabled during pre-launch bake-in.

#### Constant: `_HOST_LABEL_PATTERN`

- **Purpose:** Define the allowed ASCII syntax for one DNS label.
- **Inputs:** Candidate lower-cased hostname label.
- **Outputs:** Full-match result for a 1-to-63-character letter/digit/hyphen label.
- **Dependencies:** Python `re`.
- **Behavior:** Disallows leading/trailing hyphens, underscores, wildcard characters, URL delimiters, and oversized labels.

#### Function: `_required_environment(name)`

- **Purpose:** Read one mandatory deployment value.
- **Inputs:** Environment-variable name.
- **Outputs:** Stripped non-empty string.
- **Dependencies:** `os.environ`.
- **Behavior:** Raises `ImproperlyConfigured` for missing, empty, or whitespace-only values.

#### Function: `_required_csv_environment(name)`

- **Purpose:** Parse a required comma-separated setting.
- **Inputs:** Environment-variable name.
- **Outputs:** List of stripped non-empty values.
- **Dependencies:** `_required_environment()`.
- **Behavior:** Removes empty members and rejects separator-only input.

#### Function: `_normalize_deployment_hostname(hostname)`

- **Purpose:** Canonicalize one trusted deployment hostname.
- **Inputs:** Candidate hostname string.
- **Outputs:** Lower-cased public DNS name, `localhost`, or `127.0.0.1`.
- **Dependencies:** `_HOST_LABEL_PATTERN`, `ipaddress.ip_address()`.
- **Behavior:** Rejects wildcard/URL syntax, public IP literals, single-label internal names, invalid DNS labels, names over 253 characters, and numeric-only top-level labels.

#### Function: `_required_hostnames_environment(name)`

- **Purpose:** Parse a required Django host allowlist without catch-all patterns.
- **Inputs:** Environment-variable name containing comma-separated hostnames.
- **Outputs:** Canonical literal hostname list.
- **Dependencies:** `_required_csv_environment()`, `_normalize_deployment_hostname()`.
- **Behavior:** Raises `ImproperlyConfigured` when any member is a wildcard, URL, unsupported IP, or invalid DNS hostname.

#### Function: `_required_hostname_environment(name)`

- **Purpose:** Read one mandatory literal deployment hostname.
- **Inputs:** Environment-variable name.
- **Outputs:** Canonical hostname.
- **Dependencies:** `_required_environment()`, `_normalize_deployment_hostname()`.
- **Behavior:** Converts hostname-validation failures into a setting-specific `ImproperlyConfigured` exception.

#### Function: `_required_https_origins_environment(name)`

- **Purpose:** Validate Django CSRF trusted origins.
- **Inputs:** Environment-variable name containing comma-separated URLs.
- **Outputs:** HTTPS origin list.
- **Dependencies:** `_required_csv_environment()`, `_normalize_deployment_hostname()`, `urllib.parse.urlsplit()`.
- **Behavior:** Rejects non-HTTPS schemes, wildcard/non-DNS hosts, public IP literals, mismatched netloc syntax, credentials, paths other than `/`, queries, fragments, invalid ports, empty ports, and port zero.

#### Function: `_required_port_environment(name)`

- **Purpose:** Validate a TCP port while preserving Django's string format.
- **Inputs:** Environment-variable name.
- **Outputs:** ASCII-decimal string in `1..65535`.
- **Dependencies:** `_required_environment()`.
- **Behavior:** Rejects signs, decimals, Unicode digits, zero, and overflow.

#### Function: `_required_secret_environment(name)`

- **Purpose:** Prevent weak or example Django signing keys from booting deployment settings.
- **Inputs:** Environment-variable name.
- **Outputs:** Secret string with at least 50 characters and at least five distinct characters.
- **Dependencies:** `_required_environment()`.
- **Behavior:** Rejects low length/diversity and `django-insecure-` or `replace-with-` prefixes without logging the value.

#### Function: `_required_password_environment(name)`

- **Purpose:** Validate the application MySQL password boundary.
- **Inputs:** Environment-variable name.
- **Outputs:** Password with at least 16 characters and at least five distinct characters.
- **Dependencies:** `_required_environment()`.
- **Behavior:** Rejects short, low-diversity, or `replace-with-` values without logging the value.

### Module: `config/settings/staging.py`

- **Purpose:** Reuse production security and add provider-neutral staging controls.
- **Inputs:** Every production variable plus `STAGING_HOST`, preview flag, and local-insecure flag.
- **Outputs:** Production-derived staging settings with one narrowly silenced pre-launch system check.
- **Dependencies:** `config.settings.prod`, `urllib.parse.urlsplit()`.
- **Behavior:** Requires a literal proxy hostname that appears exactly in allowed hosts and matches a CSRF-origin hostname. Preview defaults off. Insecure HTTP can disable redirect/secure cookies only for `localhost` or `127.0.0.1`. Only `security.W021` is silenced while HSTS preload remains deliberately deferred; warning-level checks fail for every other deploy warning.

#### Function: `_environment_flag(name, *, default=False)`

- **Purpose:** Parse staging flags without truthy-string ambiguity.
- **Inputs:** Environment-variable name and Boolean default.
- **Outputs:** Boolean.
- **Dependencies:** `os.environ`.
- **Behavior:** Accepts only exact `0` or `1`; missing values use the default; every other value raises `ImproperlyConfigured`.

### Module: `config/views.py`

- **Purpose:** Expose container/process operational probes.
- **Inputs:** GET requests.
- **Outputs:** Narrow JSON health contracts.
- **Dependencies:** Django HTTP responses, database connection, logging, method decorators.
- **Behavior:** Non-GET methods return 405 and never query MySQL.

#### Function: `liveness(request)`

- **Purpose:** Prove the Django process can route requests without coupling process health to MySQL.
- **Inputs:** GET request.
- **Outputs:** HTTP 200 `{"status":"ok"}`.
- **Dependencies:** `JsonResponse`, `require_GET`.
- **Behavior:** Performs no database access.

#### Function: `readiness(request)`

- **Purpose:** Prove the process can execute a minimal database query.
- **Inputs:** GET request.
- **Outputs:** HTTP 200 `{"status":"ok"}` or HTTP 503 `{"status":"unavailable"}`.
- **Dependencies:** Django database connection, `DatabaseError`, logger.
- **Behavior:** Executes `SELECT 1` and fetches its row. Database errors are logged server-side while the response hides driver credentials/topology.

### Module: `config/urls.py`

- **Purpose:** Define the root URL table.
- **Inputs:** Incoming request path.
- **Outputs:** Health, staging preview, and Django Admin resolution.
- **Dependencies:** `config.views`, `apps.storefront.views`, `django.contrib.admin`.
- **Behavior:** Maps `/healthz/live/`, `/healthz/ready/`, `/staging/seed/`, and `/admin/`. No commerce/account/webhook URL modules are included.

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

## Deployment Artifacts

- **Purpose:** Group the provider-neutral staging build and operations contract.
- **Inputs:** Repository revision and deployment environment.
- **Outputs:** Image, Compose topology, ingress, dependency, ignore, CI, and runbook artifacts.
- **Dependencies:** Docker, Caddy, Gunicorn, MySQL, Git, and pip.
- **Behavior:** Child sections describe artifact side effects, trust boundaries, and validation.

### Artifact: `requirements.txt`

- **Purpose:** Declare compatible Python runtime and QA dependencies.
- **Inputs:** Python 3.14 package installation.
- **Outputs:** Django, MySQL driver, scheduler, environment loader, Gunicorn, WhiteNoise, pytest, and Ruff installations.
- **Dependencies:** pip and configured package indexes.
- **Behavior:** Uses compatible-release ranges; A-4 adds Gunicorn and WhiteNoise rather than an exact-version lockfile.

### Artifact: `README.md`

- **Purpose:** Provide the repository entrypoint for developers and operators.
- **Inputs:** Local Python/Docker prerequisites and the current implementation stage.
- **Outputs:** Development bootstrap, QA commands, canonical planning/ADR/documentation links, and staging-runbook pointer.
- **Dependencies:** `.env.example`, `docker-compose.yml`, `deploy/README.md`, and the Python toolchain.
- **Behavior:** Keeps local development separate from staging operations and states literally that public M1 proof remains required before Epic B.

### Artifact: `.gitignore`

- **Purpose:** Prevent local credentials, generated content, database backups, and tooling state from entering Git.
- **Inputs:** Repository filesystem paths.
- **Outputs:** Ignored runtime/generated files while named `.example` contracts remain trackable.
- **Dependencies:** Git ignore semantics.
- **Behavior:** Ignores `.env*`, `deploy/.env.staging`, `backups/`, media/static output, caches, coverage, and editor state; explicitly re-includes sanitized example files.

### Artifact: `Dockerfile`

- **Purpose:** Build the Linux staging application image.
- **Inputs:** Python 3.14 slim base, filtered repository context, `APP_UID`/`APP_GID` defaulting to 10001.
- **Outputs:** Image exposing internal port 8000 with staging entrypoint and Gunicorn command.
- **Dependencies:** `requirements.txt`, `deploy/entrypoint.sh`.
- **Behavior:** Installs dependencies, creates fixed non-root identity, keeps source root-owned, grants only `staticfiles` to UID/GID 10001, and configures one Gunicorn worker/four threads/60-second timeout with access/error logging on standard streams.

### Artifact: `.dockerignore`

- **Purpose:** Minimize and declassify the Docker build context.
- **Inputs:** Repository paths.
- **Outputs:** Filtered build context.
- **Dependencies:** Docker ignore semantics.
- **Behavior:** Excludes Git/tool state, virtualenvs, bytecode, real environment files, generated media/static, database backups, all SQL files, tests, local Docker files, coverage, and Markdown; retains sanitized examples.

### Artifact: `.gitattributes`

- **Purpose:** Preserve Linux-compatible deployment line endings from Windows checkouts.
- **Inputs:** Git path normalization.
- **Outputs:** LF endings for shell, Dockerfile, Caddyfile, and YAML artifacts.
- **Dependencies:** Git.
- **Behavior:** Applies `text eol=lf` to the deployment file families.

### Artifact: `deploy/entrypoint.sh`

- **Purpose:** Validate and prepare the app container before accepting traffic.
- **Inputs:** Exact `STAGING_SEED_DEMO` value and final container command.
- **Outputs:** Static manifest, migrated schema, optional seed, Gunicorn process.
- **Dependencies:** Django management commands.
- **Behavior:** `set -eu`; invalid seed flag exits 64 before mutation; valid flow collects static, migrates, optionally seeds, and uses `exec` for signal-correct Gunicorn shutdown.

### Artifact: `deploy/compose.staging.yml`

- **Purpose:** Compose the single-host staging system.
- **Inputs:** Sanitized deployment environment values.
- **Outputs:** MySQL, app, and Caddy services; edge/internal networks; DB/certificate volumes.
- **Dependencies:** Docker Compose, Dockerfile, Caddyfile.
- **Behavior:** MySQL publishes no port and becomes healthy first. App exposes only 8000 internally, uses `init: true`, has a 30-second stop grace period, drops all Linux capabilities, enables no-new-privileges, and checks readiness with production-like Host/HTTPS headers. Caddy waits for app health and alone publishes HTTP/HTTPS. Every service rotates JSON logs at three 10 MiB files.

### Artifact: `deploy/Caddyfile`

- **Purpose:** Terminate TLS and proxy public traffic.
- **Inputs:** Staging hostname and ACME email.
- **Outputs:** Automatic HTTPS site, HTTP redirect, compressed proxy responses, stdout access logs.
- **Dependencies:** Caddy automatic HTTPS and healthy app service.
- **Behavior:** Disables admin API, removes Server header, applies 30-day HSTS/nosniff/DENY/referrer headers, enables zstd/gzip, and forwards original Host plus proxy scheme metadata.

### Artifact: `deploy/.env.staging.example`

- **Purpose:** Declare the staging environment contract without real credentials.
- **Inputs:** Operator copy/edit.
- **Outputs:** Template for ignored `deploy/.env.staging`.
- **Dependencies:** Compose interpolation and Django validation.
- **Behavior:** Contains placeholders that intentionally fail application startup until replaced; documents distinct secrets, hostname agreement, ports, and exact seed/preview/local flags.

### Artifact: `deploy/README.md`

- **Purpose:** Provide provider-neutral staging operations.
- **Inputs:** Linux host, DNS, firewall, SSH, Docker, repository checkout.
- **Outputs:** Deploy, smoke, forced-recreation, logs, backup, rollback, and shutdown procedures.
- **Dependencies:** Deployment artifacts and operator authority.
- **Behavior:** Requires a 1-vCPU/2-GB/persistent-SSD host; enforces literal host syntax; forbids volume deletion in normal operations; documents one-app/one-worker constraint and bounded logs; validates persistence with forced recreation; creates operator-only backup files without placing the root password in the `mysqldump` argument list.

### Artifact: `.github/workflows/ci.yml`

- **Purpose:** Retain code and deployment contract verification on push and pull request.
- **Inputs:** Repository revision and MySQL 8.4 CI service.
- **Outputs:** QA and deployment-contract job results.
- **Dependencies:** GitHub Actions, Python 3.14, Docker/Compose.
- **Behavior:** QA runs Ruff lint/format, Django checks, warning-level staging checks, migration drift/reversal, and pytest on MySQL. Deployment job checks shell/Compose/Caddy/Dockerfile syntax, builds the image, verifies UID/GID/mode/write boundaries, starts an ephemeral HTTPS stack, validates seed/admin/static endpoints, force-recreates containers, proves exact row persistence, and always removes CI volumes.

## App Registration Modules

- **Purpose:** Enumerate first-party Django app registrations.
- **Inputs:** Django app discovery.
- **Outputs:** Ten `AppConfig` registrations.
- **Dependencies:** Django `AppConfig`.
- **Behavior:** The table distinguishes implemented domains from registration-only shells.

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
| `apps/storefront/apps.py` | Register storefront domain. | Django app loading. | `StorefrontConfig`. | `AppConfig`. | App includes the staging-only seed preview; `AppConfig` itself only registers metadata. |

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

## Utility Module: `apps/orders/money.py`

- **Purpose:** Centralize integer-centavo validation, arithmetic, overflow handling, and configured currency formatting.
- **Inputs:** Python values, quantities, iterables of amounts, and shared currency settings.
- **Outputs:** Validated integers, exact totals, formatted currency strings, or `MoneyValueError`.
- **Dependencies:** Django settings and the MySQL unsigned-INT storage boundary.
- **Behavior:** Rejects floats, Decimal values, strings, Booleans, implicit coercion, negative ordinary amounts, and values above `4_294_967_295`.

### Constant: `MAX_CENTAVOS = 4_294_967_295`

- **Purpose:** Mirror the maximum value of MySQL `INT UNSIGNED`.
- **Inputs:** Validation and arithmetic results.
- **Outputs:** Shared overflow boundary.
- **Dependencies:** Current money-field database type.
- **Behavior:** Values with a larger absolute magnitude are rejected before persistence.

### Class: `MoneyValueError(ValueError)`

- **Purpose:** Identify violations of the money domain contract.
- **Inputs:** Invalid monetary value, quantity, currency symbol, or configuration.
- **Outputs:** Focused exception that remains catchable as `ValueError`.
- **Dependencies:** Money utility callers.
- **Behavior:** Prevents silent numeric coercion and overflow.

### Function: `require_centavos(value, field_name="amount", *, allow_negative=False)`

- **Purpose:** Validate and return one exact centavo integer.
- **Inputs:** Candidate value, error-label field name, explicit signed-value opt-in.
- **Outputs:** Unchanged integer or `MoneyValueError`.
- **Dependencies:** `MAX_CENTAVOS`.
- **Behavior:** Rejects Boolean and every non-integer type; rejects negative values unless explicitly allowed; always enforces the magnitude ceiling.

### Function: `format_centavos(value, symbol=None)`

- **Purpose:** Render a nonnegative centavo integer using configured major/minor units.
- **Inputs:** Valid integer and optional string symbol override.
- **Outputs:** Grouped string such as `₱1,234.56`.
- **Dependencies:** `CURRENCY_SYMBOL` and `CURRENCY_MINOR_UNITS` settings.
- **Behavior:** Performs integer `divmod` formatting without floats; rejects negative/invalid amounts and malformed currency configuration.

### Function: `multiply_centavos(unit_price, quantity)`

- **Purpose:** Calculate an exact order-line total.
- **Inputs:** Nonnegative integer unit price and positive non-Boolean integer quantity.
- **Outputs:** Valid centavo integer.
- **Dependencies:** `require_centavos()`.
- **Behavior:** Rejects quantity below one and results above the database ceiling.

### Function: `sum_centavos(amounts)`

- **Purpose:** Sum a materialized or streaming iterable of nonnegative amounts.
- **Inputs:** Iterable of centavo integers.
- **Outputs:** Exact integer total; empty iterable returns zero.
- **Dependencies:** `require_centavos()`.
- **Behavior:** Validates each indexed member and checks cumulative overflow after every addition.

## Template Module: `apps/storefront/templatetags/money.py`

- **Purpose:** Expose the shared money formatter to Django templates.
- **Inputs:** Template context value.
- **Outputs:** Formatted peso string or an empty string.
- **Dependencies:** Django template library and `apps.orders.money.format_centavos`.
- **Behavior:** Registers one public filter named `peso`.

### Function: `peso(value)`

- **Purpose:** Render a valid centavo integer without duplicating formatting logic.
- **Inputs:** Template value.
- **Outputs:** Result from `format_centavos()`; empty string for `MoneyValueError`.
- **Dependencies:** Shared money utility.
- **Behavior:** Domain functions remain strict while malformed presentation context fails closed instead of causing a page-level 500.

## View Module: `apps/storefront/views.py`

- **Purpose:** Provide temporary M1 seed visibility without implementing the Epic C storefront out of order.
- **Inputs:** Request method, staging preview setting, active catalog state.
- **Outputs:** Preview HTML, hidden-route 404, or enabled-route 405.
- **Dependencies:** Product ORM, `Count`, Django settings and renderer.
- **Behavior:** Contains no catalog mutation or public commerce behavior.

### Function: `staging_seed_preview(request)`

- **Purpose:** Render deterministic seed evidence through a read-only staging gate.
- **Inputs:** HTTP request and `STAGING_SEED_PREVIEW_ENABLED`.
- **Outputs:** `staging/seed_preview.html` with products/counts; 404 while disabled; 405 for non-GET only after enabled.
- **Dependencies:** `Product`, related Category, variant reverse relation, shared `peso` filter.
- **Behavior:** Filters active products, joins categories, annotates all variant counts, orders by name, materializes rows, and sums counts in memory. No authentication is required when explicitly enabled.

## Template Module: `templates/staging/seed_preview.html`

- **Purpose:** Render a responsive, dependency-free acceptance page for seeded products.
- **Inputs:** `products`, `product_count`, `total_variants`.
- **Outputs:** Auto-escaped HTML product cards and explicit empty state.
- **Dependencies:** Django template engine and `peso` filter.
- **Behavior:** Shows name, category, base price, and variant count; inline CSS makes no external network request.

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

- **Purpose:** Group initial schema migrations and dependency order.
- **Inputs:** Historical model states and schema editor.
- **Outputs:** MySQL tables, constraints, relationships, and database defaults.
- **Dependencies:** Django migration executor and MySQL 8.
- **Behavior:** Catalog establishes database defaults before dependent schemas; the complete graph reverses and reapplies successfully.

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

## Test Module: `tests/test_money.py`

- **Purpose:** Execute the A-3 integer-centavo and presentation contract.
- **Inputs:** Money helpers, currency settings, Django template engine, invalid type matrix, and overflow boundaries.
- **Outputs:** 70 passing cases.
- **Dependencies:** pytest, Django settings overrides, and the `money` template-tag library.
- **Behavior:** Covers PHP defaults, strict integer typing, signed opt-in validation, maximum bounds, exact formatting, runtime symbol/minor-unit settings, multiplication, iterable/generator sums, overflow, filter registration, and template-safe invalid values.

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

## Test Module: `tests/test_health.py`

- **Purpose:** Verify operational probe semantics.
- **Inputs:** Django test client, mocked database cursor, simulated `DatabaseError`.
- **Outputs:** 4 passing cases.
- **Dependencies:** URL configuration and `config.views`.
- **Behavior:** Proves liveness never touches MySQL; readiness executes exact `SELECT 1` plus `fetchone`; failures return generic 503 without leaked details; POST returns 405 without cursor access.

## Test Module: `tests/test_staging_preview.py`

- **Purpose:** Verify the temporary M1 browser is hidden, read-only, and exact.
- **Inputs:** Preview setting overrides, deterministic seed, inactive sentinel product/variant.
- **Outputs:** 5 passing cases.
- **Dependencies:** MySQL, seed command, staging template, money formatter.
- **Behavior:** Proves default/explicit disabled GET and POST return 404; enabled POST returns 405; enabled GET uses the expected template and renders only 5 active products/180 variants with correct categories and peso prices.

## Test Module: `tests/test_staging_settings.py`

- **Purpose:** Verify deployment settings fail closed in isolated interpreter imports.
- **Inputs:** Complete disposable environment plus parameterized invalid values.
- **Outputs:** 48 passing cases.
- **Dependencies:** Python subprocess, production/staging settings.
- **Behavior:** Covers all required values, weak/example secrets/passwords, CSV emptiness, wildcard/URL/public-IP hostname rejection, HTTPS-origin/netloc syntax, port range/type, exact Boolean flags, proxy/allowed-host/CSRF agreement, the single silenced HSTS-preload warning, WhiteNoise/HSTS/secure-cookie defaults, public-host insecure rejection, and localhost override behavior.

## Quality Assurance

- **Purpose:** Record the successful post-implementation gate required before static analysis.
- **Inputs:** Settled source tree, Python virtual environment, Docker MySQL, migrations, and tests.
- **Outputs:** Verified pass/fail evidence.
- **Dependencies:** `.venv`, uv, Docker Compose, Caddy, Gunicorn, MySQL 8.4.10.
- **Behavior:** Every local A-4 code/deployment check passed; one explicitly expected B-1 service contract remains XFAIL. Public staging is not claimed by local evidence.

### QA Result Matrix

- **Purpose:** Consolidate reproducible post-change evidence.
- **Inputs:** Settled tree and QA commands.
- **Outputs:** Pass/fail matrix.
- **Dependencies:** Local Python, MySQL, Docker, Caddy, and YAML tooling.
- **Behavior:** Records local evidence only; public staging remains unproven.

| Check | Command or method | Result |
|---|---|---|
| Ruff lint | `.venv/Scripts/ruff check .` | Passed; all checks passed. |
| Ruff format | `.venv/Scripts/ruff format --check .` | Passed; 58 files already formatted. |
| Django system check | `manage.py check` | Passed; 0 issues. |
| Migration drift | `manage.py makemigrations --check --dry-run` | Passed; no changes detected. |
| Applied migration state | `manage.py migrate --check --settings=config.settings.dev` | Passed; no pending migration. |
| Unit/integration tests | `.venv/Scripts/pytest -q -p no:cacheprovider` | Passed; 182 passed, 1 strict XFAIL, 183 collected. |
| A-4 focused tests | health + preview + staging settings modules | Passed; 57 cases. |
| Dependency compatibility | `uv --no-cache pip check --python .venv` | Passed; 18 packages compatible. |
| YAML validation | isolated `yamllint` parse of CI and staging Compose | Passed; syntax valid with document-start style disabled. |
| Compose validation | hardened staging Compose `config --quiet` | Passed. |
| Entrypoint validation | invalid `STAGING_SEED_DEMO` container run | Passed; rejected before mutation with exit 64. |
| Docker image | Python 3.14 staging build | Passed; source `0:0`, runtime/static UID/GID `10001:10001`. |
| Container security | Docker inspect and in-container write checks | Passed; all app capabilities dropped, no-new-privileges active, source not writable by the runtime identity, and `/app/staticfiles` writable by UID/GID 10001. |
| Log bounds | Docker inspect for all three services | Passed; `json-file`, `10m`, 3 files. |
| Local HTTPS smoke | Caddy → Gunicorn/Django → MySQL | Passed; live/ready 200, admin 302, admin CSS 200, seed 5/180. |
| Persistence smoke | `up -d --force-recreate --wait` | Passed; retained 5 products, 180 variants, 180 stock rows, 180 movements. |
| Network boundary | Docker inspect | Passed; app/MySQL have no published ports; MySQL reports 0 non-InnoDB tables. |
| Static collection | staging `collectstatic --noinput` | Passed; 127 originals present and manifest/compressed derivatives processed. |
| Patch whitespace | `git diff --check` | Passed; only a Windows LF-to-CRLF advisory appeared. |
| Staging settings | `manage.py check --deploy --fail-level WARNING --settings=config.settings.staging` | Passed; no reported issues and exactly one intentional `security.W021` check silenced. |
| Database metadata | information_schema queries | Passed; 0 non-InnoDB or non-`utf8mb4` tables. |
| Money column type | information_schema query | Passed; all 7 money columns are `int unsigned`. |

### Migration Execution Evidence

- **Purpose:** Validate migration correctness beyond a plan-only check.
- **Inputs:** Temporary database `metrodrip_migration_ci_gate` initially created with Latin-1 defaults.
- **Outputs:** Successful forward, backward, and second forward migration.
- **Dependencies:** MySQL alter/create/drop privileges.
- **Behavior:** First migration converted the database to `utf8mb4_0900_ai_ci`; all tables were InnoDB; `migrate catalog zero` removed dependent project tables; reapplication succeeded; the exact temporary database was then dropped. CI repeats the same forward/reverse/forward sequence on its disposable database.

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

### A-4 Disposable Deployment Evidence

- **Purpose:** Prove the deployment artifacts work together beyond static configuration checks.
- **Inputs:** Final project `metrodrip-a4-final`, alternate host ports 28080/28443, localhost Caddy certificate, fresh named volumes, explicit demo flags, and the rebuilt source image.
- **Outputs:** Healthy MySQL/app containers, a running Caddy container, and verified HTTPS responses.
- **Dependencies:** Docker Desktop, built staging image, MySQL 8.4.10, Caddy 2.
- **Behavior:** Initial startup applied migrations and seeded exactly 5/180/180/180 catalog-variant-stock-movement rows. HTTPS probes, admin redirect, and static asset passed. Forced recreation replaced all three containers while volumes preserved identical counts. App ran as UID/GID 10001 with root-owned `0:0:755` source and writable `10001:10001:755` static output; MySQL had no host port. Disposable containers, networks, and volumes were removed afterward.
- **Limitation:** Local Caddy TLS used a localhost certificate and `curl -k`; it does not prove public DNS, publicly trusted ACME issuance, external routing, or public uptime. M1 remains open.

## Staging Environment Contract

- **Purpose:** Enumerate deployment configuration ownership and validation.
- **Inputs:** Host/operator environment file.
- **Outputs:** Deterministic Compose and Django configuration.
- **Dependencies:** Compose interpolation, production/staging settings, Caddy.
- **Behavior:** Real values live only in ignored `deploy/.env.staging`; example values are documentation and intentionally fail startup until replaced.

| Variable | Consumer | Required behavior |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | app | Compose fixes `config.settings.staging`. |
| `DJANGO_SECRET_KEY` | Django | Required; at least 50 characters/five distinct; known weak prefixes rejected. |
| `DJANGO_ALLOWED_HOSTS` | Django | Required literal-host CSV without wildcards/URLs/public IPs; must contain `STAGING_HOST` exactly. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Django | Required exact HTTPS-origin CSV without wildcard/non-DNS hosts; one hostname must match `STAGING_HOST`. |
| `MYSQL_DATABASE` | app/db | Required non-empty database name. |
| `MYSQL_USER` | app/db | Required non-empty application user. |
| `MYSQL_PASSWORD` | app/db | Required; at least 16 characters/five distinct; example prefix rejected. |
| `MYSQL_ROOT_PASSWORD` | db only | Required by Compose/MySQL; never passed to Django or Caddy. |
| `MYSQL_HOST` | app | Required; Compose fixes `db`. |
| `MYSQL_PORT` | app | Required ASCII port; Compose fixes `3306`. |
| `STAGING_HOST` | app/Caddy | Required literal proxy/site hostname; must agree with both Django security lists. Public deployment uses a public DNS hostname; local smoke may use `localhost` or `127.0.0.1`. |
| `CADDY_EMAIL` | Caddy | Required ACME contact. |
| `STAGING_HTTP_PORT` | Compose | Defaults to host port 80. |
| `STAGING_HTTPS_PORT` | Compose | Defaults to host TCP/UDP port 443. |
| `STAGING_SEED_DEMO` | entrypoint | Defaults 0; exact 0/1 only; 1 runs idempotent seed. |
| `STAGING_SEED_PREVIEW_ENABLED` | Django | Defaults false; exact 0/1; 1 exposes read-only preview. |
| `STAGING_ALLOW_INSECURE_HTTP` | Django | Defaults false; exact 0/1; `1` permitted only for `localhost` or `127.0.0.1`. |

## Hard Invariant Coverage

- **Purpose:** Map required invariants to current enforcement.
- **Inputs:** Handover invariants and implemented guards.
- **Outputs:** Coverage and remaining-gap matrix.
- **Dependencies:** Models, migrations, services, deployment settings, and tests.
- **Behavior:** Separates current enforcement from later-epic work.

| Hard invariant | Current coverage | Remaining gap |
|---|---|---|
| No overselling | Database availability check and strict red concurrency contract. | No reserve/release/consume service or reservation TTL model; B-1 contract is not active-pass yet. |
| Integer centavos | MySQL unsigned-INT fields, strict type validation, pre-write overflow checks, exact arithmetic, configured formatting, and 70 A-3 tests. | Later checkout/reporting code must use these helpers consistently. |
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

- A-4 public staging evidence is absent: no selected host, DNS record, trusted public certificate, external URL, or authoritative public smoke result exists. Local deployment artifacts are complete.
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
- Catalog caching, CDN/object storage configuration, production email provider, external log aggregation, uptime alerting, and application monitoring are absent. Bounded container-captured console logging and staging configuration are implemented.
- CI does not currently enforce coverage thresholds, dependency/security scanning, immutable image digests, or public endpoint monitoring. It does run system/deploy checks, drift and reversal validation, deployment syntax/config/build checks, a live forced-recreation HTTPS stack, and the full MySQL suite.
- `Payment.status`, `Shipment.status`, and `Review.status` currently permit direct ORM mutation.
- The strict 2-buyer/1-unit test is a precursor; the M2 release gate still requires 20 parallel buyers for 10 units with exactly 10 successes.

## Next Strict Build Step

- **Purpose:** Identify the next task without expanding scope.
- **Inputs:** Handover dependency order, completed local A-4 implementation, and M1 gate evidence.
- **Outputs:** Task sequence for continuation.
- **Dependencies:** A Linux staging host, recurring-spend authority, DNS control, SSH/Docker access, and a public HTTPS smoke pass.
- **Behavior:** Deploy the existing A-4 stack publicly and prove M1 first. Only then implement B-1 atomic inventory operations, remove the strict XFAIL marker, and make the existing race contract pass normally.
