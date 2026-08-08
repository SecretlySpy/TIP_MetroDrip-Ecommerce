# Adversarial Challenge Report — Hard Invariants & Concurrency

## Challenge Summary
**Overall risk assessment**: LOW

Empirical stress testing was conducted against all 5 AGENTS.md Hard Invariants across concurrency, type boundaries, edge cases, attack vectors, and authorization boundaries. All 5 Hard Invariants held strictly under adversarial stress.

---

## 1. Hard Invariants Stress Test Results

### Invariant 1: Zero Overselling (Atomic Stock Checks & Reservations)
- **Mechanism Tested**: `select_for_update()` row locking, `transaction.atomic()`, `available = qty_on_hand - qty_reserved` state machine, and idempotency key locks (`IdempotencyRecord`) in `LocalInventoryProvider`.
- **Attack Vector / Harness**: 20 concurrent worker threads aligned by a barrier competing to reserve 1 unit each from a SKU with `qty_on_hand=10`.
- **Result**: **PASS**. Exactly 10 worker threads succeeded (200 OK / Reservation created), and exactly 10 worker threads were rejected with `InsufficientStock` (409 Conflict). `qty_reserved` reached exactly 10, and `available` dropped to exactly 0. Zero overselling occurred.
- **Idempotency Guard Harness**: 5 concurrent worker threads sending duplicate `reserve_lines` requests under the same `checkout_id`.
- **Result**: **PASS**. Exactly 3 units reserved once (`qty_reserved=3`). Primary key constraint on `IdempotencyRecord` serialized the parallel retries without double-reserving.
- **Type Validation Harness**: Invalid quantity inputs (`0`, `-1`, `1.5`, `True`, `False`, `"2"`).
- **Result**: **PASS**. All 6 invalid input types were rejected with `ValueError` / `TypeError` (explicit `isinstance(value, bool)` check prevents `True` being treated as `1`).

### Invariant 2: Integer Centavos Currency Storage
- **Mechanism Tested**: `require_centavos` strict type validation, `multiply_centavos`, `sum_centavos`, `format_centavos`, and `MAX_CENTAVOS` (4,294,967,295) unsigned INT cap in `apps/core/money.py`.
- **Attack Vector / Harness**: Floating-point values (`10.50`, `0.0`), string amounts (`"10000"`), boolean flags (`True`, `False`), negative values (`-100`), and values overflowing MySQL INT (`4_294_967_296`).
- **Result**: **PASS**. All non-integer, boolean, negative, and overflow amounts raised `MoneyValueError`. Integer centavo multiplication, summation, and Philippine Peso formatting (`₱1,234.56`) functioned without floating-point drift.

### Invariant 3: Webhook Signature Verification
- **Mechanism Tested**: Fail-closed HMAC-SHA256 signature checking for PayMongo (`Paymongo-Signature` header) and Courier (`X-Courier-Signature` header) webhooks.
- **Attack Vector / Harness**: Unsigned requests (missing header), mis-signed requests (invalid hash), tampered payload bodies, and unconfigured webhook secrets (`PAYMONGO_WEBHOOK_SECRET = ""`, `COURIER_WEBHOOK_SECRET = ""`).
- **Result**: **PASS**. Unsigned, invalidly signed, or secret-unset requests returned HTTP 400 Bad Request immediately without parsing payloads or executing state transitions. Fail-closed posture verified.

### Invariant 4: Append-Only Stock Ledger (`StockMovement`)
- **Mechanism Tested**: `StockMovement` model override of `save()` and `delete()`, and `AppendOnlyMovementQuerySet` override of `update()`, `bulk_update()`, `delete()`, and `bulk_create(update_conflicts=True)`.
- **Attack Vector / Harness**: 6 direct mutation attempts on `StockMovement` rows:
  1. Instance `.save()` on existing row
  2. Instance `.delete()`
  3. QuerySet `.update()`
  4. QuerySet `.delete()`
  5. QuerySet `.bulk_update()`
  6. QuerySet `.bulk_create(update_conflicts=True)`
- **Result**: **PASS**. All 6 mutation attempts raised `TypeError` ("StockMovement is append-only"). Ledger rows are strictly immutable.

### Invariant 5: Dual Console Isolation (`/admin/` vs `/merchant/`)
- **Mechanism Tested**: Model registry separation (`admin.site` vs `merchant_site`), role-based view permissions (`StaffRole`), and login form credentials gating.
- **Attack Vector / Harness**:
  1. Registry Overlap: `labels(admin.site) & labels(merchant_site)` check. -> **0 overlapping models**.
  2. Merchant access: Signed in as Merchant (`role=MERCHANT, is_staff=True`), accessed `/merchant/` (HTTP 200 OK), attempted `/admin/` (HTTP 403 Forbidden with "wrong console" message), attempted `/admin/login/` (form error "does not have access"), attempted direct model URL `/merchant/accounts/customer/` (HTTP 404 Not Found).
  3. Administrator access: Signed in as Administrator (`role=ADMINISTRATOR, is_staff=True`), accessed `/admin/` (HTTP 200 OK), attempted `/merchant/` (HTTP 403 Forbidden), attempted `/merchant/login/` (form error), attempted direct model URL `/admin/catalog/product/` (HTTP 404 Not Found).
  4. Shopper access: Signed in as Shopper (`role=CUSTOMER, is_staff=False`), attempted `/admin/` (HTTP 403) and `/merchant/` (HTTP 403).
  5. Superuser access: Signed in as Superuser (`is_superuser=True`), admitted to both `/admin/` (HTTP 200) and `/merchant/` (HTTP 200).
- **Result**: **PASS**. Dual console boundary is fully enforced at registry, HTTP, login, and model URL routing levels.

---

## 2. Stress Test Harness Execution Summary

- **Harness Script**: Executed `/tmp/test_invariants_harness.py` against live Django & MySQL setup.
- **Results Breakdown**:
  - Invariant 1 (Zero Overselling): PASS
  - Invariant 2 (Integer Centavos): PASS
  - Invariant 3 (Webhook Signatures): PASS
  - Invariant 4 (Append-Only Ledger): PASS
  - Invariant 5 (Dual Console Isolation): PASS

---

## 3. Unchallenged / Residual Risk Areas

- **FastAPI Sidecar Inventory Provider (`INVENTORY_PROVIDER=service`)**: Tested primary in-process `local` provider; service provider depends on M2 sidecar lifecycle.
- **Database Engine Dependencies**: InnoDB row locks (`SELECT FOR UPDATE`) are mandatory; SQLite or engines without row-level locking fake concurrency.
