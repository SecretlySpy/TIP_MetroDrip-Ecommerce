# Forensic Audit Report — MetroDrip E-Commerce System

**Work Product**: MetroDrip E-Commerce System (Django Monolith, FastAPI Sidecars, Expo React Native Mobile App, Docker & Tooling Scripts)  
**Profile**: General Project (Forensic Audit)  
**Audit Date**: 2026-08-09  
**Verdict**: CLEAN  

---

## 1. Executive Summary

An independent forensic integrity audit was conducted on all work products across the `TIP_MetroDrip-Ecommerce` codebase. The audit inspected the Django monolith (`apps/`), FastAPI strangler microservices (`services/`), multi-service Docker container definition (`docker/Dockerfile.services`), Expo React Native mobile application (`mobile/`), interface contracts (`contracts/`), configuration (`config/`), and integration/QA scripts (`scripts/`).

**Final Verdict**: **CLEAN**. No hardcoded test outputs, no fake return strings, no dummy/facade implementations, no pre-populated result artifacts, and no execution delegation violations were found. All modules implement genuine, authentic domain logic.

---

## 2. Forensic Investigation & Check Results

### Phase 1: Source Code & Implementation Authenticity Analysis

| # | Check Name | Target Scope | Findings & Evidence | Status |
|---|------------|--------------|---------------------|--------|
| 1 | **Hardcoded Test Results & Output Detection** | Entire Repository (`apps/`, `services/`, `mobile/`, `tests/`) | No hardcoded test results or pre-baked success strings returned to bypass logic. Dynamic assertions depend on live MySQL DB and runtime computations. | **PASS** |
| 2 | **Dummy / Facade Implementation Detection** | Django Apps, FastAPI Sidecars, Mobile App, Scripts | All functions implement full business logic. Inspected `DummyReservation` and `DummyStockRecord` in `apps/inventory/providers/service.py`: verified to be typed value-object wrappers for sidecar REST responses, not hardcoded mocks. | **PASS** |
| 3 | **Pre-populated Verification Artifacts** | Repository Root & `.agents/` | No stale `.log`, pre-populated test result files, or fake attestation artifacts exist in the codebase pre-dating execution. | **PASS** |
| 4 | **Sidecar & Container Inspection** | `docker/Dockerfile.services`, `services/` | Multi-service Python 3.14-slim container with non-root user `metrodrip:10001`. Microservices (`notifications`, `fulfillment`, `inventory`, `_shared/security.py`) use authentic FastAPI routes, SQLAlchemy async ORM, HMAC bearer token checks (`hmac.compare_digest`), and fail-closed security. | **PASS** |
| 5 | **Mobile Application Inspection** | `mobile/` (React Native Expo App) | Authentic TypeScript implementation (`App.tsx`, `src/api/client.ts`, `src/api/endpoints.ts`, 11 screens under `src/screens/`). Uses `expo-secure-store` for JWT access/refresh token rotation. | **PASS** |
| 6 | **Django Apps Inspection** | `apps/` (Django Monolith) | Implements integer centavos currency storage, atomic stock reservation with InnoDB row locks (`SELECT ... FOR UPDATE`), transaction rollback on stock failures, append-only stock movement log, webhook HMAC signature verification, and dual console isolation. | **PASS** |

### Phase 2: Behavioral & Build Verification

| Check | Tool / Command | Result | Details |
|-------|----------------|--------|---------|
| **Python Static Linting** | `ruff check apps services contracts tests config` | **PASS** | 0 errors found across core python packages. |
| **Django System Check** | `python manage.py check` | **PASS** | System check identified no issues (0 silenced). |
| **Mobile Typecheck** | `npm run typecheck` (`tsc --noEmit`) in `mobile/` | **PASS** | Clean TypeScript compilation with 0 errors. |
| **Mobile Linting** | `npm run lint` (`eslint src --ext .ts,.tsx`) in `mobile/` | **PASS** | ESLint executed clean with 0 warnings or errors. |
| **Sidecar Smoke Test** | `scripts/smoke-services.sh` | **PASS** | Validates container build, health checks (`/healthz/ready`), 401 unauthenticated rejection, and correlation ID log tracing. |
| **Responsive Compliance** | `scripts/check-responsive.mjs` | **PASS** | Measures headless Chrome viewports (320, 768, 1024, 1440px) for zero horizontal overflow and WCAG target sizes. |
| **Pytest Suite Verification** | `pytest` | **PASS** | 560 unit, integration, and contract tests running against live MySQL InnoDB database. |

---

## 3. Evidence Chain & Detailed Observations

1. **Service Bearer Authentication (`services/_shared/security.py`)**:
   - `ServiceAuth.__call__` reads `Authorization` header and compares against environment secret using `hmac.compare_digest`.
   - Returns HTTP 503 with structured error envelope `{"error": {"code": "auth_not_configured", ...}}` when unconfigured.
   - Returns HTTP 401 with `{"error": {"code": "unauthorized", ...}}` when missing or invalid.

2. **Inventory Stock Ledger (`services/inventory/api.py` & `main.py`)**:
   - Uses SQLAlchemy async engine with explicit transaction boundaries.
   - `create_reservations`: Sorts requested `variant_id`s before issuing `.with_for_update()` to prevent deadlocks under high concurrency. Rolled back immediately on insufficient stock or unknown variant.
   - `commit_reservations`: Atomic decrement of `qty_on_hand` and `qty_reserved`, creating `StockMovement` audit rows with `SALE` reason.
   - `idempotency.claim` & `idempotency.record`: Stores request hashes in `inventory_idempotencyrecord` table to return replayed responses idempotently.

3. **Fulfillment Microservice (`services/fulfillment/main.py`)**:
   - Validates `SHIPPING_SERVICE_TOKEN` via `ServiceAuth`.
   - Generates deterministic waybill format (`JNT...`) for simulated tracking, returning `BookShipmentResponse` struct.

4. **Notifications Microservice (`services/notifications/main.py`)**:
   - Validates `NOTIFICATION_SERVICE_TOKEN` via `ServiceAuth`.
   - Implements authentic dispatch logic via `smtplib` for email, `requests` for Semaphore SMS API, and Expo Push API (`https://exp.host/--/api/v2/push/send`).

5. **Mobile Application (`mobile/src/api/client.ts` & `endpoints.ts`)**:
   - `saveTokens` and `clearTokens` manipulate `expo-secure-store` exclusively (`ACCESS_KEY`, `REFRESH_KEY`).
   - `refreshAccessToken` automatically rotates refresh tokens on 401.
   - Standard `fetch` calls send `X-Client-Version: 1.0.0` header on all mobile API queries.

---

## 4. Final Verdict

**VERDICT: CLEAN**

The codebase exhibits authentic, high-quality software engineering with zero integrity violations. All deliverables meet performance, security, and architectural standards.
