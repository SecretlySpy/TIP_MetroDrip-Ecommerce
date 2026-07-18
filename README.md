# TIP_MetroDrip-Ecommerce

**MetroDrip** — B2C e-commerce + inventory system for a Metro Manila streetwear brand.
Django 5.2 / MySQL 8 (InnoDB, utf8mb4) / Django Templates + HTMX + Alpine.js.

The approved plan is [MetroDrip_AI_Handover.md](MetroDrip_AI_Handover.md);
implementation choices made along the way are logged in [DECISIONS.md](DECISIONS.md);
machine-readable architecture notes live in [AI Documentation Notes.md](AI%20Documentation%20Notes.md).

## Local development

```bash
# 1. Python env (Python 3.14)
uv venv .venv --python 3.14        # or: python -m venv .venv
.venv/Scripts/pip install -r requirements.txt

# 2. Secrets
cp .env.example .env               # defaults match docker-compose

# 3. Database (MySQL 8 in Docker)
docker compose up -d db

# 4. Schema + demo data
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py seed_demo

# 5. Run
.venv/Scripts/python manage.py runserver
```

## QA

```bash
.venv/Scripts/ruff check .
.venv/Scripts/pytest            # needs the Docker MySQL up — concurrency tests use real InnoDB locks
```
