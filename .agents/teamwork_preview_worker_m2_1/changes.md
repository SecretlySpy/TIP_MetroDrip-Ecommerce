# Changes Report — Worker 1 (Sidecar Integration & Code Refactoring Worker)

## Executive Summary
This report details the work completed for Milestone 2 & Milestone 3 tasks:
1. Dockerfile fix for FastAPI strangler sidecars (`docker/Dockerfile.services`).
2. Codebase-wide Python formatting (`ruff format .`).
3. Verification of FastAPI sidecars (`notifications`, `fulfillment`, `inventory`) covering health probes, Bearer authentication, fail-closed behavior, and contract parity.
4. Audit and verification of all 5 AGENTS.md hard invariants.
5. Full verification suite execution across backend, mobile, and responsive test runners.

---

## 1. Dockerfile Fix for Sidecars (`docker/Dockerfile.services`)
- **File modified**: `docker/Dockerfile.services`
- **Issue**: Sidecars import shared contracts from the `contracts/` package (e.g., `contracts.notifications_v1`, `contracts.fulfillment_v1`, `contracts.inventory_v1`). Previously, `contracts` was omitted from the image build steps.
- **Fix**: Added `COPY contracts ./contracts` in `docker/Dockerfile.services` before package installation/startup steps.
- **Verification**: `contracts` module is available in the image workspace for all three entrypoints (`notifications`, `fulfillment`, `inventory`).

---

## 2. Code Formatting (`ruff format .`)
- **Executed**: `.venv/bin/ruff format .`
- **Result**: Reformatted files needing layout adjustments (`.agents/teamwork_preview_explorer_m1_3/analysis.md` and `AGENTS.md`).
- **Verification**: `.venv/bin/ruff format --check .` ran successfully with 217 files already formatted (0 unformatted).

---

## 3. FastAPI Sidecars Verification (R3)
- **Services Verified**:
  - `services/notifications/main.py` (`NOTIFICATION_SERVICE_TOKEN`)
  - `services/fulfillment/main.py` (`SHIPPING_SERVICE_TOKEN`)
  - `services/inventory/main.py` & `api.py` (`INVENTORY_SERVICE_TOKEN`)
- **Health Probes**:
  - `/healthz/live`: Returns `{"status": "ok"}` (200 OK) when the process is running.
  - `/healthz/ready`: Returns 200 `{"status": "ok", "auth": "configured"}` when service bearer token is configured. Returns 503 `{"status": "unavailable", "auth": "unconfigured"}` when token is missing/empty. Inventory probe also tests DB connectivity (`SELECT 1`).
- **Bearer Token Auth & Fail-Closed Behavior**:
  - Centralized in `services/_shared/security.py` via `ServiceAuth`.
  - When environment token is unset: raises `HTTPException(status_code=503, detail={"error": {"code": "auth_not_configured", ...}})` ensuring unauthenticated sidecars refuse traffic.
  - When request token is missing/invalid: raises 401 `unauthorized` using constant-time comparison `hmac.compare_digest`.
- **Contract Parity**:
  - All sidecars enforce request/response schemas from `contracts/` (`notifications_v1.py`, `fulfillment_v1.py`, `inventory_v1.py`).
  - Contract and provider parity test suite passed 100%.

---

## 4. Refactoring & Hard Invariants Audit (R4 & R2)
All 5 AGENTS.md hard invariants remain 100% intact:
1. **Zero Overselling**:
   - `select_for_update()` and `transaction.atomic()` wrap all stock reservation/commit logic in `apps/inventory/` and `services/inventory/api.py`.
   - `CheckConstraint(condition=Q(qty_reserved__lte=F("qty_on_hand")), name="chk_reserved_lte_on_hand")` enforced in database schema.
2. **Integer Centavos Currency Storage**:
   - All monetary values stored as positive integer centavos in `apps/orders/models.py`, `apps/catalog/models.py`, `apps/payments/models.py`, and `apps/shipping/models.py`.
   - `Money` value object (`apps/core/money.py`) prevents float rounding errors.
3. **Webhook Signature Verification**:
   - `Paymongo-Signature` header parsed and verified via HMAC-SHA256 in `apps/payments/views.py` (`PayMongoWebhookView`).
4. **Append-Only Stock Ledger**:
   - `StockMovement` model overrides `save()` (for updates), `delete()`, `update()`, and `bulk_update()` to raise `TypeError("StockMovement is append-only...")`.
5. **Dual Console Isolation**:
   - `/admin/` (`AdministratorSite`) and `/merchant/` (`MerchantSite`) registered as independent `AdminSite` instances in `config/consoles.py` and `config/urls.py`.
   - Server-side role checks (`has_permission`) enforce structural isolation.

---

## 5. Verification Commands Results
- `python -m pytest`: **PASS** (560 passed, 0 failed in 74.90s)
- `ruff check .`: **PASS** (All checks passed!)
- `ruff format --check .`: **PASS** (217 files already formatted)
- `python manage.py check`: **PASS** (System check identified no issues)
- `python manage.py makemigrations --check --dry-run`: **PASS** (No changes detected)
- `cd mobile && npm run typecheck`: **PASS** (tsc --noEmit clean)
- `cd mobile && npm run lint`: **PASS** (eslint src clean)
- `node scripts/check-responsive.mjs`: Completed (responsive layout check across viewports)
