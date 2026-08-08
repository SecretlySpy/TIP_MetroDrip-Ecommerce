# Adversarial Challenge Report — M2 Sidecar & Cross-Platform Integration

## Challenge Summary

**Overall risk assessment**: LOW

Empirical testing confirmed that all FastAPI sidecars (`notifications`, `fulfillment`, `inventory`) implement strict fail-closed security mechanics, returning HTTP 503 `auth_not_configured` on `/healthz/ready` and on all protected routes when unconfigured. Cross-platform responsive checks passed with 100% coverage (40/40 route/width combinations clean). The React Native mobile application under `mobile/` passed both TypeScript typechecking (`tsc --noEmit`) and ESLint (`eslint src --ext .ts,.tsx`) with 0 errors.

---

## Challenges

### [Low] Challenge 1: Timing Leak Protection in Token Comparison
- **Assumption challenged**: Bearer token authentication in strangler sidecars could be susceptible to timing attack side-channels if string comparison (`==`) were used.
- **Attack scenario**: An attacker sends forged `Authorization: Bearer <token_guess>` headers and measures response latency to guess the valid token character-by-character.
- **Blast radius**: Unauthorized execution of sidecar write operations (email/SMS delivery, shipment booking, stock reservation).
- **Mitigation / Status**: **PASSED**. Empirical code audit and test execution confirmed `services/_shared/security.py` line 77 uses `hmac.compare_digest(authorization, expected_header)` which provides constant-time comparison.

### [Low] Challenge 2: Unconfigured Sidecar Ingestion Security (Fail-Closed Mechanics)
- **Assumption challenged**: Unconfigured sidecars (empty or unset environment variable tokens) might default to lenient/pass-through behavior or report ready to load balancers.
- **Attack scenario**: A deployed container without `NOTIFICATION_SERVICE_TOKEN`, `SHIPPING_SERVICE_TOKEN`, or `INVENTORY_SERVICE_TOKEN` receives unauthenticated internal traffic and processes requests.
- **Blast radius**: Full bypass of internal service authentication boundaries.
- **Mitigation / Status**: **PASSED**. Empirical verification demonstrated that unconfigured sidecars return HTTP 503 `auth_not_configured` on both `/healthz/ready` and all protected endpoints.

---

## Stress Test Results

| # | Stress Test Scenario | Expected Behavior | Actual Empirical Result | Pass/Fail |
|---|----------------------|-------------------|------------------------|-----------|
| 1 | `GET /healthz/ready` with `NOTIFICATION_SERVICE_TOKEN` unset | HTTP 503, `{"status": "unavailable", "auth": "unconfigured"}` | HTTP 503, `{"status": "unavailable", "auth": "unconfigured"}` | **PASS** |
| 2 | `POST /v1/email` with `NOTIFICATION_SERVICE_TOKEN` unset | HTTP 503 `auth_not_configured` | HTTP 503 `auth_not_configured` | **PASS** |
| 3 | `GET /healthz/ready` with `SHIPPING_SERVICE_TOKEN` unset | HTTP 503, `{"status": "unavailable", "auth": "unconfigured"}` | HTTP 503, `{"status": "unavailable", "auth": "unconfigured"}` | **PASS** |
| 4 | `POST /v1/shipments/book` with `SHIPPING_SERVICE_TOKEN` unset | HTTP 503 `auth_not_configured` | HTTP 503 `auth_not_configured` | **PASS** |
| 5 | `GET /healthz/ready` with `INVENTORY_SERVICE_TOKEN` unset | HTTP 503, `{"status": "unavailable", "auth": "unconfigured"}` | HTTP 503, `{"status": "unavailable", "auth": "unconfigured"}` | **PASS** |
| 6 | `POST /v1/reservations` with `INVENTORY_SERVICE_TOKEN` unset | HTTP 503 `auth_not_configured` | HTTP 503 `auth_not_configured` | **PASS** |
| 7 | Sidecar request with missing `Authorization` header | HTTP 401 `unauthorized` | HTTP 401 `unauthorized` | **PASS** |
| 8 | Sidecar request with invalid bearer token | HTTP 401 `unauthorized` | HTTP 401 `unauthorized` | **PASS** |
| 9 | Sidecar contract pytest suite (`test_inventory_v1.py`, `test_notifications_v1.py`, `test_fulfillment_v1.py`) | 25/25 tests pass | 25/25 passed (2.96s) | **PASS** |
| 10 | `node scripts/check-responsive.mjs` (10 public routes × 4 viewports) | 100% pass (40/40) | 40/40 passed (0 page scroll overflow, 0 clipped tables, 0 target violations) | **PASS** |
| 11 | `cd mobile && npm run typecheck` (`tsc --noEmit`) | Exit code 0, 0 errors | 0 errors | **PASS** |
| 12 | `cd mobile && npm run lint` (`eslint src --ext .ts,.tsx`) | Exit code 0, 0 errors | 0 errors | **PASS** |

---

## Unchallenged Areas

- **Live Database Infrastructure Integration for `test_ledger_roundtrip.py`**: Unit contract tests pass with test mock clients, but running multi-container round-trip network tests requires `metrodrip-mysql` test database creation (`test_metrodrip`).
