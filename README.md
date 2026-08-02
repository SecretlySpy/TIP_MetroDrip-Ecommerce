# MetroDrip

B2C e-commerce + inventory system for a Metro Manila streetwear brand.

**Stack:** Django 5.2 · MySQL 8 (InnoDB, utf8mb4) · Django Templates + HTMX + Alpine.js · DRF mobile API · Expo / React Native client.

Governing docs: [MetroDrip_AI_Handover.md](MetroDrip_AI_Handover.md) · [DECISIONS.md](DECISIONS.md) · [AI Documentation Notes.md](AI%20Documentation%20Notes.md) · [mobile/README.md](mobile/README.md) · [deploy/README.md](deploy/README.md)

## What is built (Epics A–H)

| Surface | Path / package | Notes |
|---|---|---|
| Customer storefront | `/`, `/shop/`, `/cart/`, `/checkout/` | Catalog, wishlist, verified reviews, CMS banners, printable invoices |
| Merchant console | `/merchant/` | Orders, packing slips, inventory — staff role enforced |
| Administrator console | `/admin/` | Full admin; **not** interchangeable with merchant (see `tests/test_console_separation.py`) |
| Mobile API | `/api/mobile/v1/` | JWT auth, catalog, cart validate, checkout, orders, account, wishlist, reviews, notifications |
| Mobile app | `mobile/` | Expo SDK 51, 11 screens, SecureStore tokens, **no client-side money math (D-13)** |
| Health | `/healthz/live/`, `/healthz/ready/` | Liveness + readiness |
| Providers | payments / shipping / notifications | Config-driven adapters; **`PAYMENT_PROVIDER=simulated`** is the local default |

Architecture today is a **service-oriented modular monolith** (Django apps, one deployable, one MySQL instance). Optional FastAPI sidecars under `services/` (inventory experimental; notifications **delivery** only) are strangler opt-ins — defaults stay in-process. See `DECISIONS.md` ADR-P3-003.

## Local development

Requires **Python 3.14**, Docker (MySQL 8 + Redis), and Node 20+ for the mobile app.

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

Optional sidecars (not required for normal dev — defaults are in-process):

```bash
# Inventory (experimental; keep INVENTORY_PROVIDER=local unless you know the gaps)
uvicorn services.inventory.main:app --reload --port 8001

# Notifications delivery only (email/SMS/push DTOs). Opt-in:
#   NOTIFICATION_PROVIDER=http NOTIFICATION_SERVICE_URL=http://127.0.0.1:8002
uvicorn services.notifications.main:app --reload --port 8002

# Fulfillment booking only (waybill I/O). Opt-in:
#   SHIPPING_PROVIDER=http SHIPPING_SERVICE_URL=http://127.0.0.1:8003
uvicorn services.fulfillment.main:app --reload --port 8003
```

### Mobile app

```bash
cd mobile
npm install
cp .env.example .env                 # EXPO_PUBLIC_API_URL → host API
npm start                            # Expo Go / emulator; see mobile/README.md
```

Android emulator alias for the host machine: `http://10.0.2.2:8080/api/mobile/v1`.

## QA gate (run before every PR)

```bash
python -m compileall -q apps config jobs tests manage.py
ruff check .
ruff format --check .
python manage.py check
python manage.py makemigrations --check --dry-run
pytest                               # needs Docker MySQL — concurrency tests use real InnoDB locks
```

**Never write `except A, B:`** — use `except (A, B):`. Guarded by `tests/test_source_compiles.py` and the pre-commit `compile-python` hook.

## Key environment variables

| Variable | Purpose |
|---|---|
| `MYSQL_*` | Database (see `.env.example`) |
| `DJANGO_SECRET_KEY` | Required |
| `PAYMENT_PROVIDER` | `simulated` (default dev) or PayMongo |
| `PAYMONGO_SECRET_KEY` / `PAYMONGO_WEBHOOK_SECRET` | Live payments |
| `GOOGLE_MAPS_API_KEY` | FR-13 Places autocomplete on web checkout |
| `COURIER_WEBHOOK_SECRET` | Inbound courier webhooks (fail-closed if unset) |
| `PUSH_PROVIDER` | `simulated` \| `expo` |

## Staging

Provider-neutral Caddy/Gunicorn/MySQL deployment, env contract, backups, and smoke checks: [deploy/README.md](deploy/README.md).
