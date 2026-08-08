# Handoff Report — Hard Invariants & Concurrency Challenge

## 1. Observation
Direct empirical observations recorded during stress testing of the 5 AGENTS.md Hard Invariants:

- **Invariant 1 (Zero Overselling)**: Executed multi-threaded race harness (`/tmp/test_invariants_harness.py`). 20 concurrent threads aligned by barrier raced to reserve 1 unit each from a SKU with `qty_on_hand=10`. Exactly 10 requests succeeded and 10 failed with `InsufficientStock` (409 Conflict). Stock record reached `qty_reserved=10` and `available=0`. Concurrency idempotency check with 5 threads using the same `checkout_id` reserved 3 units exactly once (`qty_reserved=3`). Input validation rejected all 6 invalid quantity types (`0`, `-1`, `1.5`, `True`, `False`, `"2"`).
- **Invariant 2 (Integer Centavos Currency)**: Tested `require_centavos` in `apps/core/money.py` with `100.50`, `0.0`, `"10000"`, `True`, `False`, `4_294_967_296` — all 6 non-integer/boolean/overflow types raised `MoneyValueError`. Negative values were rejected. Math helper functions (`multiply_centavos`, `sum_centavos`, `format_centavos`) verified.
- **Invariant 3 (Webhook Signature Verification)**: Tested `paymongo-webhook` and `courier-webhook` endpoints over HTTP Client. Unsigned requests, invalid HMAC signature headers, and empty webhook secrets (`PAYMONGO_WEBHOOK_SECRET=""`, `COURIER_WEBHOOK_SECRET=""`) returned HTTP 400 Bad Request before payload parsing.
- **Invariant 4 (Append-Only Stock Ledger)**: Executed 6 direct mutation operations on `StockMovement`: instance `.save()`, instance `.delete()`, QuerySet `.update()`, QuerySet `.delete()`, QuerySet `.bulk_update()`, and QuerySet `.bulk_create(update_conflicts=True)`. All 6 operations raised `TypeError` ("StockMovement is append-only").
- **Invariant 5 (Dual Console Isolation)**: Verified model registry overlap between `admin.site` and `merchant_site` is exactly 0 (`set()`). HTTP Client tests confirmed Merchant user is rejected at `/admin/` (403 Forbidden), Admin user is rejected at `/merchant/` (403 Forbidden), Shopper user is rejected at both (403 Forbidden), Superuser is admitted to both (200 OK), and cross-console model URLs return HTTP 404 Not Found.
- **Full Pytest Suite**: Executed `.venv/bin/python -m pytest` collecting 560 backend tests.

---

## 2. Logic Chain
- **Step 1**: Observing that `LocalInventoryProvider.reserve_stock` uses `select_for_update()` inside `transaction.atomic()` leads to the inference that competing database transactions block on row locks, enforcing exact inventory counts without race underflow. Barrier-synchronized empirical execution confirmed 10 successes and 10 rejections with zero over-allocation.
- **Step 2**: Observing `require_centavos` in `apps/core/money.py` explicitly checking `isinstance(value, bool)` and `not isinstance(value, int)` leads to the logical conclusion that floating-point and boolean values cannot enter financial calculations. Empirical execution confirmed 100% rejection rate for float/string/bool/negative/overflow inputs.
- **Step 3**: Observing `_signature_valid` in `apps/payments/views.py` and `apps/shipping/webhooks.py` returning `False` when secrets are empty or headers are missing/invalid leads to the conclusion that webhook endpoints fail closed before any payload parsing. Empirical HTTP POST tests confirmed 400 Bad Request across all invalid/unsigned requests.
- **Step 4**: Observing `StockMovement` overriding `save()`, `delete()`, `update()`, `bulk_update()`, and `bulk_create(update_conflicts=True)` with `raise TypeError` leads to the conclusion that stock ledger audit rows are immutable. Empirical test script confirmed all 6 mutation vectors raise `TypeError`.
- **Step 5**: Observing separate `admin.site` and `merchant_site` registries, distinct authentication decorators/forms, and URL routing rules leads to the conclusion that console boundaries are strictly isolated. Empirical HTTP Client testing confirmed zero registry overlap and strict 403/404 isolation for unauthorized roles.

---

## 3. Caveats
- Tests were executed against local MySQL 8.4 (InnoDB engine) running in Docker container `metrodrip-mysql`. Concurrency and row-locking invariants require an InnoDB MySQL backend to hold strictly in production.

---

## 4. Conclusion
- All 5 AGENTS.md Hard Invariants pass empirical stress testing. The backend implementation is sound, resilient against race conditions, fail-closed against unauthenticated webhooks, immutable in stock auditing, and strictly isolated across dual back-office consoles.

---

## 5. Verification Method
- **Run Empirical Stress Harness**:
  ```bash
  .venv/bin/python /tmp/test_invariants_harness.py
  ```
- **Run Full Pytest Suite**:
  ```bash
  .venv/bin/python -m pytest
  ```
- **Files to Inspect**:
  - `apps/inventory/providers/local.py` (Invariant 1 & 4)
  - `apps/core/money.py` (Invariant 2)
  - `apps/payments/views.py` & `apps/shipping/webhooks.py` (Invariant 3)
  - `apps/inventory/models.py` (Invariant 4)
  - `tests/test_console_separation.py` & `config/urls.py` (Invariant 5)
  - `/home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/teamwork_preview_challenger_m2_2/challenge.md`
