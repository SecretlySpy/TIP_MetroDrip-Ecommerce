# Code Review Report — FastAPI Sidecars, Dockerfile & Mobile App

**Verdict**: APPROVE

## Executive Summary
As Reviewer 2 (Sidecars & Mobile Reviewer), a thorough code review and automated verification of the FastAPI sidecars (`services/`), Dockerfile (`docker/Dockerfile.services`), and Mobile app (`mobile/`) was conducted. All checks pass and conform to project specifications and hard invariants.

---

## 1. Dockerfile Inspection (`docker/Dockerfile.services`)

- **Layer Placement of `COPY contracts ./contracts`**:
  - `COPY contracts ./contracts` is placed at line 23 immediately after `WORKDIR /app` and before installing dependencies (`RUN python -m pip install -r requirements-services.txt`) and copying sidecars (`COPY services ./services`).
  - **Verdict**: Correctly placed. `/app/contracts` is present in the working directory and cleanly importable by all FastAPI sidecars (`contracts.notifications_v1`, `contracts.fulfillment_v1`, `contracts.inventory_v1`, `contracts.errors`).
- **Security & User Non-Root Isolation**:
  - Non-root user `metrodrip` (UID 10001) is created and set via `USER ${APP_UID}:${APP_GID}` prior to `CMD`.

---

## 2. FastAPI Sidecars Audit (`services/`)

### Notifications Service (`services/notifications/main.py`)
- **Health Probes**:
  - `/healthz/live`: Returns `{"status": "ok"}` (200 OK).
  - `/healthz/ready`: Probes `auth.configured`. Returns 503 `{"status": "unavailable", "auth": "unconfigured"}` if `NOTIFICATION_SERVICE_TOKEN` is unset/empty; returns 200 `{"status": "ok", "auth": "configured"}` when set.
- **Token Auth & Fail-Closed**:
  - Secured by `ServiceAuth("NOTIFICATION_SERVICE_TOKEN")`. Unconfigured state fails closed by throwing 503 `auth_not_configured` error envelope.
  - Validates `Authorization: Bearer <token>` using constant-time `hmac.compare_digest`.
- **Contract Parity**:
  - Uses contract routes `ROUTE_EMAIL`, `ROUTE_SMS`, `ROUTE_PUSH` and Pydantic schemas `EmailPayload`, `SmsPayload`, `PushPayload` from `contracts.notifications_v1`.

### Fulfillment Service (`services/fulfillment/main.py`)
- **Health Probes**:
  - `/healthz/live`: Returns `{"status": "ok"}` (200 OK).
  - `/healthz/ready`: Returns 503 `{"status": "unavailable", "auth": "unconfigured"}` if `SHIPPING_SERVICE_TOKEN` is unset/empty; returns 200 when configured.
- **Token Auth & Fail-Closed**:
  - Secured by `ServiceAuth("SHIPPING_SERVICE_TOKEN")`. Fails closed with 503 if unconfigured.
- **Contract Parity**:
  - Uses `ROUTE_BOOK`, `BookShipmentRequest`, `BookShipmentResponse` from `contracts.fulfillment_v1`.

### Inventory Service (`services/inventory/main.py`, `api.py`, `database.py`, `idempotency.py`)
- **Health Probes**:
  - `/healthz/live`: Returns `{"status": "ok"}` (200 OK).
  - `/healthz/ready`: Probes `auth.configured` (returns 503 if unconfigured) and executes `SELECT 1` against the MySQL database. Returns 503 `{"status": "unavailable", "auth": "configured", "db": "down"}` if DB unreachable.
- **Token Auth & Fail-Closed**:
  - Secured by `ServiceAuth("INVENTORY_SERVICE_TOKEN")` applied across all router endpoints. Fails closed with 503 if unconfigured.
- **Contract Parity & Invariants**:
  - Mutating routes (`/v1/reservations`, `/v1/reservations/{checkout_id}/commit`, `/v1/reservations/{checkout_id}/release`, `/v1/stock/adjustments`) require `Idempotency-Key` headers (or payload keys) and enforce atomic hold/commit semantics with `with_for_update()` to prevent overselling.

---

## 3. Automated Mobile & Script Verification

| Check | Command | Result | Verification Notes |
|-------|---------|--------|-------------------|
| **Mobile Typecheck** | `cd mobile && npm run typecheck` | **PASS** | 0 TypeScript errors (`tsc --noEmit`) |
| **Mobile Lint** | `cd mobile && npm run lint` | **PASS** | 0 ESLint errors/warnings (`eslint src --ext .ts,.tsx`) |
| **Responsive Check** | `node scripts/check-responsive.mjs` | **PASS** | 40/40 tests passed across 10 routes at 320px, 768px, 1024px, 1440px |
| **Notifications & Shipping Contract Pytest** | `.venv/bin/pytest tests/contract/test_notifications_v1.py tests/contract/test_fulfillment_v1.py` | **PASS** | 10/10 contract tests passed |
| **Notifications & Shipping HTTP Pytest** | `.venv/bin/pytest tests/test_notifications_http.py tests/test_shipping_http.py` | **PASS** | 7/7 HTTP provider tests passed |

---

## 4. Integrity & Security Audit

- **Integrity Violations Check**:
  - Hardcoded test outputs / expected values in code: **None**
  - Facade / mock implementations bypassing real logic: **None**
  - Bypassed core tasks: **None**
  - Fabricated verification outputs: **None** (all test outputs executed and captured directly)
- **Token Security**:
  - Mobile app (`mobile/src/api/client.ts`) stores JWT access and refresh tokens strictly in `expo-secure-store` (Keychain / Keystore), complying with NFR-19.
  - Sidecars use constant-time `hmac.compare_digest` to mitigate timing attacks.
  - Unconfigured sidecars default to 503 fail-closed behavior rather than skipping auth.

---

## Verified Claims Matrix

| Claim | Source | Verification Command / Method | Result |
|-------|--------|------------------------------|--------|
| `COPY contracts ./contracts` in Dockerfile | `docker/Dockerfile.services:23` | `view_file` inspection | Verified |
| Notifications `/healthz/ready` checks token | `services/notifications/main.py:54` | `view_file` inspection & pytest | Verified |
| Fulfillment `/healthz/ready` checks token | `services/fulfillment/main.py:47` | `view_file` inspection & pytest | Verified |
| Inventory `/healthz/ready` checks token + DB | `services/inventory/main.py:69-81` | `view_file` inspection | Verified |
| Mobile TypeScript typecheck clean | `mobile/` | `npm run typecheck` | Verified (PASS) |
| Mobile ESLint clean | `mobile/` | `npm run lint` | Verified (PASS) |
| Layout responsive across 4 viewports | `scripts/check-responsive.mjs` | `node scripts/check-responsive.mjs` | Verified (40/40 PASS) |
