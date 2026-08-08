# Comprehensive Web Codebase System Audit & Invariant Report

**Project**: MetroDrip E-Commerce System  
**Auditor**: Explorer 1 (Web Codebase Audit)  
**Date**: 2026-08-08  
**Scope**: Django Web Application, Apps, Models, Views, URLs, Settings, DB Configuration (MySQL), Automated Check Suite, and AGENTS.md Hard Invariants Compliance.

---

## Executive Summary

A comprehensive system audit of the MetroDrip Django web application was conducted. The codebase exhibits a highly disciplined architecture adhering strictly to modular domain boundaries, integer-centavo monetary storage, atomic inventory reservations, append-only stock ledgers, webhook HMAC signature verification, and dual admin console separation.

Key findings:
1. **Automated Checks**: 4 out of 5 checks passed cleanly (`pytest` running/passing all items, `ruff check .` PASSED, `python manage.py check` PASSED, `python manage.py makemigrations --check --dry-run` PASSED). 1 check failed (`ruff format --check .` failed due to unformatted code block in `AGENTS.md`).
2. **Hard Invariants**: All 5 hard invariants mandated in `AGENTS.md` are **100% COMPLIANT** in design, implementation, and DB-level constraints.
3. **Database Configuration**: Pinned to MySQL 8 with InnoDB engine (`default_storage_engine=INNODB`, `sql_mode='STRICT_TRANS_TABLES'`) and `utf8mb4` charset.

---

## 1. Automated System Checks Summary

| Check Command | Status | Result / Details |
|---|---|---|
| `./.venv/bin/python -m pytest` | **PASSED** | Executed 560 test items; 560 passed in 84.78s (0 failures, 0 errors). |
| `./.venv/bin/ruff check .` | **PASSED** | Output: `All checks passed!` |
| `./.venv/bin/ruff format --check .` | **FAILED** | Exit code 1: 1 file would be reformatted (`AGENTS.md:360:14` code snippet indentation/spacing). 207 files already formatted. |
| `./.venv/bin/python manage.py check` | **PASSED** | Output: `System check identified no issues (0 silenced).` |
| `./.venv/bin/python manage.py makemigrations --check --dry-run` | **PASSED** | Output: `No changes detected` |

### Detailed Check Execution Findings:
- **Pytest**: Tested against Django 5.2.16 with `config.settings.test` environment settings. Test suite covers models, views, contract tests, storefront pages, concurrency gates, stock holds, and outbox event streaming.
- **Ruff Format Failure**: Running `ruff format --check .` flags a minor code snippet formatting issue in `AGENTS.md` (lines 359–369). Running `ruff format AGENTS.md` will resolve this formatting violation.

---

## 2. Hard Invariants Compliance Audit (AGENTS.md)

### Invariant 1: Zero Overselling (Atomic Stock Checks & Reservation)
- **Status**: `PASSED` / `COMPLIANT`
- **Implementation**: `apps/inventory/models.py`, `apps/inventory/providers/local.py`
- **Evidence**:
  - `StockRecord` defines `available` property as `qty_on_hand - qty_reserved`.
  - Database-level check constraint `chk_reserved_lte_on_hand` (`models.CheckConstraint(condition=models.Q(qty_reserved__lte=models.F("qty_on_hand")))`) prevents `qty_reserved` from exceeding physical stock at the MySQL engine level.
  - `LocalInventoryProvider.reserve_stock` and `reserve_lines` execute within `transaction.atomic()` using `select_for_update()` row locks on `StockRecord`.
  - `reserve_lines` claims an `IdempotencyRecord` primary key row (`key_hash`) atomically before locking variants in ascending `variant_id` order to eliminate lock-cycle deadlocks.
  - Active checkout holds automatically expire via `release_expired_reservations` (15-minute TTL).

### Invariant 2: Integer Centavos Currency Storage
- **Status**: `PASSED` / `COMPLIANT`
- **Implementation**: `apps/core/money.py`, domain models across `apps/catalog`, `apps/orders`, `apps/shipping`, `apps/payments`.
- **Evidence**:
  - Zero `DecimalField` or currency `FloatField` exist in domain models.
  - Prices and totals are stored as `PositiveIntegerField` representing integer centavos (e.g. `Product.base_price`, `ProductVariant.price_override`, `Order.subtotal`, `Order.shipping_fee`, `Order.total`, `ShippingZone.fee`).
  - Core money module `apps/core/money.py` enforces strict validation (`require_centavos`, `multiply_centavos`, `sum_centavos`), explicitly rejecting booleans, floats, strings, and integer overflow beyond `MAX_CENTAVOS` (4,294,967,295 centavos / MySQL INT UNSIGNED limit).
  - Formatting functions (`format_centavos`) handle conversion to grouped peso strings (`₱1,250.00`) exclusively at display time.

### Invariant 3: Webhook Signature Verification
- **Status**: `PASSED` / `COMPLIANT`
- **Implementation**: `apps/payments/views.py` (`paymongo_webhook`)
- **Evidence**:
  - Incoming requests to `/payments/webhooks/paymongo/` MUST pass `_signature_valid(request)` prior to any payload JSON parsing or processing.
  - `_signature_valid` extracts the `Paymongo-Signature` header (`t=<ts>,te=<sig>,li=<sig>`) and computes HMAC-SHA256 over `f"{timestamp}.".encode() + request.body` using `settings.PAYMONGO_WEBHOOK_SECRET`.
  - Signatures are compared using constant-time comparison `hmac.compare_digest`.
  - Fail-closed security design: if `PAYMONGO_WEBHOOK_SECRET` is unset or signature comparison fails, the view immediately returns `HttpResponse(status=400)`.

### Invariant 4: Append-Only Stock Ledger
- **Status**: `PASSED` / `COMPLIANT`
- **Implementation**: `apps/inventory/models.py` (`StockMovement`, `AppendOnlyMovementQuerySet`)
- **Evidence**:
  - `StockMovement` tracks every `qty_on_hand` change with signed `delta` and `reason` (`SALE`, `RESTOCK`, `ADJUSTMENT`, `RETURN`).
  - Model overrides `save()` and `delete()` to raise `TypeError("StockMovement is append-only; rows cannot be updated/deleted.")` if `self.pk` is set or deletion is attempted.
  - `AppendOnlyMovementQuerySet` overrides `.update()`, `.bulk_update()`, `.delete()`, and rejects `update_conflicts=True` in `.bulk_create()`.
  - Database check constraint `chk_movement_reason_delta` guarantees that `SALE` has negative delta, `RESTOCK`/`RETURN` have positive deltas, and `ADJUSTMENT` has non-zero deltas.

### Invariant 5: Dual Console Isolation
- **Status**: `PASSED` / `COMPLIANT`
- **Implementation**: `config/consoles.py`, `apps/accounts/roles.py`
- **Evidence**:
  - Two distinct Django `AdminSite` instances are instantiated: `AdministratorSite` mounted at `/admin/` and `MerchantSite` mounted at `/merchant/`.
  - `ConsoleAuthenticationForm` (`AdministratorAuthenticationForm` and `MerchantAuthenticationForm`) validates that authenticated users possess the matching `StaffRole` (`administrator` vs `merchant`).
  - `ConsoleSite.has_permission()` checks `user.is_superuser or user.role == self.console_role` on every request.
  - Unauthorized access attempts by an authenticated staff member belonging to the opposite console trigger `render_wrong_console()`, returning an informative 403 response with links to their authorized console rather than entering endless redirect loops.

---

## 3. System Architecture & Database Configuration Inspection

- **Django Settings Structure**:
  - Split settings design: `config/settings/base.py`, `dev.py`, `prod.py`, `staging.py`, `test.py`.
  - `SECRET_KEY` loaded from environment via `python-dotenv`.
  - Middleware pipeline includes standard security middleware, WhiteNoise static file serving, `CorrelationIdMiddleware` for distributed tracing, and `MobileClientVersionMiddleware` for mobile client compatibility.
- **Database Configuration**:
  - Backend: `django.db.backends.mysql` using `pymysql` (installed via `pymysql.install_as_MySQLdb()`).
  - Settings pin `init_command: "SET default_storage_engine=INNODB, sql_mode='STRICT_TRANS_TABLES'"` and `charset: "utf8mb4"`.
  - Test database configured with `CHARSET: "utf8mb4"` and `COLLATION: "utf8mb4_0900_ai_ci"`.
- **Order State Machine**:
  - `Order.transition_to()` strictly governs transitions according to `ALLOWED_TRANSITIONS`:
    - `PENDING` → `PAID` | `CANCELLED`
    - `PAID` → `PACKED` | `REFUNDED`
    - `PACKED` → `SHIPPED` | `REFUNDED`
    - `SHIPPED` → `DELIVERED` | `REFUNDED`
    - `DELIVERED` → `REFUNDED`
  - `OrderQuerySet` blocks `.update(status=...)` and `.bulk_update(fields=['status'])`, forcing all status changes through domain methods.

---

## 4. Code Smells, Bugs, & Gaps Identified

1. **Linting / Formatting Violation (Minor Code Smell)**:
   - `ruff format --check .` flagged 1 file (`AGENTS.md`) requiring reformatting in a Python code block (lines 359–369).
   - *Impact*: Low. Does not affect application runtime, but breaks strict CI format checking.

2. **Python Executable Alias**:
   - `python` command is not bound in environment PATH (`/usr/bin/python3` and `./.venv/bin/python` are present).
   - *Impact*: Low. Automated scripts calling `python` directly instead of `./.venv/bin/python` or `python3` fail with `command not found` unless executed inside activated virtualenv.

3. **Staging / Seed Feature Toggle Isolation**:
   - `STAGING_SEED_PREVIEW_ENABLED` is `False` in base settings, explicitly guarded so demo seed endpoints cannot leak into production.

---

## 5. Verification Method

To independently verify the audit conclusions:
1. **Automated Test Suite**:
   ```bash
   ./.venv/bin/python -m pytest
   ```
2. **System Check & Migration Verification**:
   ```bash
   ./.venv/bin/python manage.py check
   ./.venv/bin/python manage.py makemigrations --check --dry-run
   ```
3. **Linter & Formatter Verification**:
   ```bash
   ./.venv/bin/ruff check .
   ./.venv/bin/ruff format --check .
   ```
4. **Hard Invariant Verification**:
   - Inspect `apps/inventory/models.py` for `AppendOnlyMovementQuerySet` and `CheckConstraint`.
   - Inspect `apps/core/money.py` for `require_centavos`.
   - Inspect `apps/payments/views.py` for `_signature_valid`.
   - Inspect `config/consoles.py` for `ConsoleSite` and `ConsoleAuthenticationForm`.

---

## 6. Recommendations & Action Items

1. **Fix Formatting**:
   Execute `./.venv/bin/ruff format AGENTS.md` so `ruff format --check .` returns 0 exit code across the entire repository.
2. **Maintain Strict Invariant Controls**:
   Ensure future refactoring in Milestones 2 and 3 preserves the DB check constraints (`chk_reserved_lte_on_hand`, `chk_order_total_reconciles`, `chk_movement_reason_delta`) and domain service locks.
