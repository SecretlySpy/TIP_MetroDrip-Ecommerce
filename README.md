# MetroDrip

B2C e-commerce + inventory system for a Metro Manila streetwear brand.

**Stack:** Django 5.2 · MySQL 8 (InnoDB, utf8mb4) · Django Templates + HTMX + Alpine.js · DRF mobile API · Expo / React Native client.

Governing docs: [AI Documentation Notes.md](AI%20Documentation%20Notes.md) · [DECISIONS.md](DECISIONS.md) · [Tech Stack Setup Guide.md](Tech%20Stack%20Setup%20Guide.md) · [mobile/README.md](mobile/README.md) · [deploy/README.md](deploy/README.md) · [Guide](https://secretlyspy.github.io/TIP_MetroDrip-Ecommerce/) 

## What is built (Epics A–H)

| Surface | Path / package | Notes |
|---|---|---|
| Customer storefront | `/`, `/shop/`, `/cart/`, `/checkout/` | Catalog, wishlist, verified reviews, CMS banners, printable invoices |
| Merchant console | `/merchant/` | Orders, packing slips, inventory — staff role enforced |
| Administrator console | `/admin/` | Full admin; **not** interchangeable with merchant (see `tests/test_console_separation.py`) |
| Mobile API | `/api/mobile/v1/` | JWT auth, catalog, cart validate, checkout, orders, account, wishlist, reviews, notifications |
| Mobile app | `mobile/` | Expo SDK 57 / React Native 0.86, 12 screens, SecureStore tokens, **no client-side money math (D-13)** |
| Health | `/healthz/live/`, `/healthz/ready/` | Liveness + readiness |
| Providers | payments / shipping / notifications | Config-driven adapters; **`PAYMENT_PROVIDER=simulated`** is the local default |

Architecture today is a **service-oriented modular monolith** (Django apps, one deployable, one MySQL instance) with a strangler migration in progress. **Microservices are not shipped**, and stock is not owned by a service.

FastAPI sidecars under `services/` are opt-in; every default stays in-process:

| Sidecar | Owns | Toggle | State |
|---|---|---|---|
| `notifications` | email/SMS/push delivery I/O | `NOTIFICATION_PROVIDER=http` | cut-over capable |
| `fulfillment` | courier booking I/O | `SHIPPING_PROVIDER=http` | cut-over capable |
| `inventory` | stock ledger: reserve/commit/release, adjustments, TTL sweep, low-stock | `INVENTORY_PROVIDER=service` | full contract; parity + no-oversell-over-network proven; **selectable, default stays `local`** |

The first two became genuinely cut-over capable only recently: `prod.py` previously discarded the provider environment variable and reassigned a hardcoded value, so `=http` was unreachable in every deployed environment (ADR-P3-008). Both ends of each seam also failed *open* on an unset token (ADR-P3-009).

Remaining strangler steps: **3** stock ownership is **complete and evidenced** — the ledger implements the full contract, 30 parity assertions cover both providers, and the M2 no-oversell gate passes with 20 concurrent buyers reserving across a real socket to a real ledger process. **4** schema split is designed and deliberately not executed (ADR-P3-013). **5** checkout saga stays gated (ADR-P3-007).

`INVENTORY_PROVIDER=service` is now *permitted* in deployed environments; the **default is still `local`**. The sidecars ship behind the `services` Compose profile in staging too (`docker compose --profile services up -d --build`), so a default deploy runs none of them. Widening the allowlist does not flip a default — it lets an operator open the seam deliberately. The stock commit is still a synchronous HTTP call made inside the payment transaction, but it no longer carries the full retry budget: it runs on a single tight attempt (measured 2.0s worst case, down from 15.1s) because the transactional outbox already guarantees delivery, and the drainer retries outside the transaction. See `DECISIONS.md` ADR-P3-025 and ADR-P3-028.

## Local development

Requires **Python 3.14** and Docker (MySQL 8 + Redis). Mobile development additionally requires
Node.js **22.13+**; native Android development uses JDK 17 and Android API 36.

```bash
# 1. Python env
uv venv .venv --python 3.14          # or: python3.14 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt   # or: pip install -r requirements.txt
pre-commit install                   # compileall + ruff on every commit

# 2. Secrets (defaults match docker-compose)
cp .env.example .env

# 3. Infrastructure
docker compose up -d                 # MySQL 8.4 + Redis

# 4. Schema + demo catalog
python manage.py migrate
python manage.py seed_demo

# 5. API (bind 0.0.0.0 so the Android emulator can reach it)
PAYMENT_PROVIDER=simulated python manage.py runserver 0.0.0.0:8080
```

### Which seed command is canonical

**`seed_demo` is the only canonical catalog seed** (ADR-A-012): five curated products with stable
copy, variants, inventory, shipping zones, flatpages, and a homepage banner. It does **not** attach
product imagery or create Men/Women child categories. Anything customer- or stakeholder-facing
should start from it alone; add approved imagery separately.

The other scripts are **development fixtures, not alternatives**, and they are not equivalent:

| Script | Produces | Use it for |
|---|---|---|
| `manage.py seed_demo` | 5 curated products | **Canonical.** Demos, stakeholder review, screenshots |
| `manage.py seed_mock_catalog` | bulk mock catalog | Pagination and filter testing |
| `seed_assignment.py`, `seed_more.py`, `seed_200.py`, `seed_collections.py` | ~150+ placeholder-copy products | Local pagination/perf work only |

A dev database that has had the padded scripts run against it can hold **far more** than the
canonical five. The count depends on which fixtures ran and is not an API or screenshot contract.
Check the active database instead of assuming a number:
`python manage.py shell -c "from apps.catalog.models import Product; print(Product.objects.count())"`.

That is useful for exercising pagination and filters and harmless locally — but it is **not** what the demo is supposed to look like. To reset a demo-facing environment, truncate the catalog and run `seed_demo` alone.

### Back-office 2FA and login limits

`/admin/` and `/merchant/` are rate-limited and support TOTP two-factor (ADR-P3-029).

```bash
# Who could still sign in with only a password?
python manage.py check_console_otp            # --strict exits non-zero if any account is unenrolled
```

The stock `/admin/otp_totp/totpdevice/add/` form is a low-level device editor,
not a verified enrolment wizard. A newly saved device can become confirmed before
the user proves a code, and this repository has no self-service recovery-code
flow. Do not direct a beginner through that form. Keep `CONSOLE_REQUIRE_OTP` off
unless an authorized operator has tested provisioning and recovery with a second
administrator. **Once an account has a confirmed device, its password alone stops
working while that device exists.**

| Setting | Default | Notes |
|---|---|---|
| `CONSOLE_LOGIN_MAX_ATTEMPTS_PER_USER` | `5` | Per 15-minute window. The load-bearing limit |
| `CONSOLE_LOGIN_MAX_ATTEMPTS_PER_IP` | `20` | Looser on purpose — staff share office NAT |
| `CONSOLE_LOGIN_TRUSTED_PROXY_DEPTH` | `0` | `0` reads `REMOTE_ADDR` and ignores `X-Forwarded-For`. **Set to `1` behind Caddy**, or per-IP limiting is measuring the proxy |
| `CONSOLE_REQUIRE_OTP` | off | Requires 2FA of *every* account, enrolled or not |

> **Audit before enabling `CONSOLE_REQUIRE_OTP`.** It refuses any account without a
> confirmed device, including the superuser needed to recover others. Run
> `check_console_otp` first; it reports exactly who would be locked out. Production
> rollout remains an operator task until a scan-and-confirm and recovery workflow exists.

> **Rate-limit counters live in `CACHES["default"]`,** which is unconfigured and
> therefore per-process. Under multiple Gunicorn workers the effective limit is
> roughly the configured value × worker count. Point `CACHES` at the Redis already
> in Compose before treating the numbers as exact.

Optional sidecars (not required for normal dev — defaults are in-process):

```bash
# Every sidecar now refuses all traffic and reports NOT ready without its token
# (ADR-P3-009), so each command below sets one.

# Inventory (experimental; keep INVENTORY_PROVIDER=local unless you know the gaps)
INVENTORY_SERVICE_TOKEN=local-dev-inventory-token \
  uvicorn services.inventory.main:app --reload --port 8001

# Notifications delivery only (email/SMS/push DTOs). Opt-in:
#   NOTIFICATION_PROVIDER=http NOTIFICATION_SERVICE_URL=http://127.0.0.1:8002
NOTIFICATION_SERVICE_TOKEN=local-dev-notifications-token \
  uvicorn services.notifications.main:app --reload --port 8002

# Fulfillment booking only (waybill I/O). Opt-in:
#   SHIPPING_PROVIDER=http SHIPPING_SERVICE_URL=http://127.0.0.1:8003
SHIPPING_SERVICE_TOKEN=local-dev-fulfillment-token \
  uvicorn services.fulfillment.main:app --reload --port 8003

# Or run all three sidecars in Docker (Compose profile `services`):
docker compose --profile services up -d --build
bash scripts/smoke-services.sh
```

### Mobile app

```bash
cd mobile
npm ci
cp .env.example .env                 # EXPO_PUBLIC_API_URL → host API
npm run android:emulator             # first API 36 emulator build/install + Metro
# Later emulator JavaScript-only sessions:
npm run start:android:emulator       # restores ADB reverse and reconnects safely
```

Android emulator alias for the host machine: `http://10.0.2.2:8080/api/mobile/v1`.
Both named-emulator commands first require the database-backed host check at
`http://127.0.0.1:8080/healthz/ready/` to return `{"status":"ok"}`. If Django or its data
services are stopped, the launcher now fails before opening the app and prints the recovery
commands. Use `npm run start:android:emulator -- --allow-offline` only when deliberately testing
the saved-content/offline UI.
The first iOS build is `npm run ios` on macOS with Xcode 26.4+; Apple-side execution has not been
verified from this Linux workspace. `npm start` remains the LAN-oriented development-client command
for physical devices. Expo Go is not the supported client.

Two different purchase checks are intentional:

- **Guest:** checkout reaches public Order Tracking at **Paid**. A guest order has no customer, so
  it does not create an in-app notification or appear in a later account automatically.
- **Signed in:** checkout reaches **Paid**, Home's bell opens Notifications with **Order
  confirmed**, and the matching order is visible to staff in `/merchant/`.

## QA gate (run before every PR)

```bash
python -m compileall -q apps config contracts jobs services tests manage.py
ruff check .
ruff format --check .
python manage.py check
python manage.py makemigrations --check --dry-run
pytest                               # needs Docker MySQL — concurrency tests use real InnoDB locks
```

Mobile QA, from `mobile/`, is `npm ci`, `npm run dependencies:check`, `npm run doctor`,
`npm run typecheck`, `npm run lint`, `npm run export:android`, and `npm run export:ios`. A clean
native Android gate additionally runs `npm run prebuild:android` followed by
`./android/gradlew -p android --no-daemon :app:assembleDebug` under JDK 17/API 36.

**Never write `except A, B:`** — use `except (A, B):`. Guarded by `tests/test_source_compiles.py` and the pre-commit `compile-python` hook.

## GitHub Pages guide deployment

The public setup guide is deployed by `.github/workflows/static.yml`. The repository setting must
remain **Settings → Pages → Build and deployment → Source: GitHub Actions**; no publication branch
or `/docs` folder is selected. The workflow needs no repository secret and requests its own
job-scoped permissions: read-only source access while building, then Pages write plus OpenID Connect
only in the `github-pages` deployment job. The repository-wide Actions default may remain read-only.

The deployment does not upload the repository. It runs
`python scripts/build-pages-site.py --output .pages-site`, which creates a new artifact containing
only `index.html` and the PNG/SVG files that the guide references under `docs/images/`. Missing,
escaping, symlinked, or non-image references fail before deployment. Pushes to `main` redeploy only
when the guide, its public images, the builder, or the Pages workflow changes; the Actions tab also
offers a manual `workflow_dispatch` run.

## Key environment variables

| Variable | Purpose |
|---|---|
| `MYSQL_*` | Database (see `.env.example`) |
| `DJANGO_SECRET_KEY` | Required |
| `PAYMENT_PROVIDER` | `simulated` or `paymongo`; explicit values win, otherwise dev infers from the PayMongo key |
| `PAYMONGO_SECRET_KEY` / `PAYMONGO_WEBHOOK_SECRET` | Live payments |
| `GOOGLE_MAPS_API_KEY` | FR-13 Places autocomplete on web checkout |
| `COURIER_WEBHOOK_SECRET` | Inbound courier webhooks (fail-closed if unset) |
| `PUSH_PROVIDER` | `simulated` \| `expo` |

## Staging

Provider-neutral Caddy/Gunicorn/MySQL deployment, env contract, backups, and smoke checks: [deploy/README.md](deploy/README.md).
