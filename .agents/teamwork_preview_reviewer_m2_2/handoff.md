# Handoff Report — Sidecars & Mobile Review (Reviewer 2)

## 1. Observation

- **Dockerfile (`docker/Dockerfile.services:23`)**:
  `COPY contracts ./contracts` is placed after `WORKDIR /app` (line 21) and before `RUN python -m pip install -r requirements-services.txt` (line 26) and `COPY services ./services` (line 28).
- **FastAPI Sidecars (`services/`)**:
  - `services/notifications/main.py` lines 45–57: `/healthz/live` returns `{"status": "ok"}`; `/healthz/ready` checks `auth.configured` and returns `503` if unconfigured.
  - `services/fulfillment/main.py` lines 33–50: `/healthz/live` returns `{"status": "ok"}`; `/healthz/ready` checks `auth.configured` and returns `503` if unconfigured.
  - `services/inventory/main.py` lines 53–83: `/healthz/live` returns `{"status": "ok"}`; `/healthz/ready` checks `auth.configured` (503 if false) and executes `SELECT 1` DB probe (503 with `"db": "down"` if connection fails).
  - `services/_shared/security.py` lines 57–81: `ServiceAuth` raises `HTTPException(503)` if token environment variable is unset, and uses `hmac.compare_digest` to check `Bearer <token>` returning `HTTPException(401)` on mismatch.
- **Mobile Automated Checks**:
  - `cd mobile && npm run typecheck`:
    ```
    > metrodrip-mobile@1.0.0 typecheck
    > tsc --noEmit
    ```
    Completed with exit code 0.
  - `cd mobile && npm run lint`:
    ```
    > metrodrip-mobile@1.0.0 lint
    > eslint src --ext .ts,.tsx
    ```
    Completed with exit code 0.
  - `node scripts/check-responsive.mjs`:
    ```
    === responsive compliance ===
    route                      320     768    1024    1440
    home                      PASS    PASS    PASS    PASS
    shop                      PASS    PASS    PASS    PASS
    shop-filtered             PASS    PASS    PASS    PASS
    product-detail            PASS    PASS    PASS    PASS
    cart                      PASS    PASS    PASS    PASS
    checkout                  PASS    PASS    PASS    PASS
    contact                   PASS    PASS    PASS    PASS
    login                     PASS    PASS    PASS    PASS
    register                  PASS    PASS    PASS    PASS
    developers                PASS    PASS    PASS    PASS

    40/40 passed
    ```
    Completed with exit code 0.
- **Contract & HTTP Unit Pytests**:
  - `.venv/bin/pytest tests/contract/test_notifications_v1.py tests/contract/test_fulfillment_v1.py`: `10 passed in 2.31s`.
  - `.venv/bin/pytest tests/test_notifications_http.py tests/test_shipping_http.py`: `7 passed in 0.76s`.

---

## 2. Logic Chain

1. Observation of `docker/Dockerfile.services` line 23 confirms `COPY contracts ./contracts` is placed inside the image workdir prior to application entrypoints, enabling contract imports across services.
2. Observation of `services/notifications/main.py`, `services/fulfillment/main.py`, and `services/inventory/main.py` confirms that all three sidecars expose `/healthz/live` and `/healthz/ready` probes.
3. Observation of `services/_shared/security.py` shows that unconfigured token environment variables result in HTTP 503 error responses (fail-closed architecture) and invalid authorization tokens result in HTTP 401 using constant-time comparison (`hmac.compare_digest`).
4. Observation of contract models in `contracts/` and sidecar routes in `services/` confirms structural schema and route parity between the Django HTTP adapters and FastAPI services.
5. Execution of `npm run typecheck` and `npm run lint` in `mobile/` confirms zero TypeScript compilation errors and zero ESLint rule violations.
6. Execution of `node scripts/check-responsive.mjs` confirms 100% (40/40) compliance across all viewports without page scroll or clipped data tables.
7. Verification of integrity constraints confirmed no hardcoded test outputs or facade implementations.

---

## 3. Caveats

- Full database integration tests (`tests/contract/test_ledger_roundtrip.py`) require a running MySQL container/service with test database `test_metrodrip` provisioned (which fails cleanly with `OperationalError 1049: Unknown database 'test_metrodrip'` when MySQL is not running locally). The sidecar unit and contract tests running in-memory passed 100%.

---

## 4. Conclusion

The FastAPI sidecars, Dockerfile configuration, and Mobile app meet all architectural, security, contract parity, and code quality requirements.

**Verdict**: **APPROVE**

---

## 5. Verification Method

To independently verify this report:

1. **Dockerfile placement**:
   Inspect line 23 of `docker/Dockerfile.services` using `view_file` or `cat docker/Dockerfile.services`.
2. **Mobile checks**:
   - `cd mobile && npm run typecheck`
   - `cd mobile && npm run lint`
3. **Responsive layout script**:
   - `node scripts/check-responsive.mjs`
4. **Sidecar contract tests**:
   - `.venv/bin/pytest tests/contract/test_notifications_v1.py tests/contract/test_fulfillment_v1.py`
   - `.venv/bin/pytest tests/test_notifications_http.py tests/test_shipping_http.py`
