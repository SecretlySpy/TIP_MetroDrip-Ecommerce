## 2026-08-09T01:56:16Z
You are Worker 1 (Sidecar Integration & Code Refactoring Worker).
Working directory: /home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/teamwork_preview_worker_m2_1
Project Scope document: /home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/orchestrator/PROJECT.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Tasks for Milestone 2 & Milestone 3:
1. **Fix Dockerfile for Sidecars**:
   - Inspect `docker/Dockerfile.services`.
   - Ensure `COPY contracts ./contracts` is present before package installation/startup so that `contracts` can be imported inside containers without `ModuleNotFoundError`.
2. **Format Code**:
   - Run `ruff format .` to resolve any ruff formatting failures.
3. **Verify FastAPI Sidecars (R3)**:
   - Verify health probes (`/healthz/live`, `/healthz/ready`), Bearer token authentication, fail-closed handling (return 503 auth_not_configured when auth token is unconfigured), and contract parity for `notifications`, `fulfillment`, and `inventory`.
   - Run test scripts / pytest suite covering services to ensure 100% pass rate.
4. **Refactoring & Hard Invariants (R4 & R2)**:
   - Ensure all 5 AGENTS.md hard invariants remain 100% intact:
     1. Zero overselling (`select_for_update()`, atomic transactions).
     2. Integer centavos currency storage (positive integer amounts).
     3. Webhook signature verification (`Paymongo-Signature` HMAC-SHA256).
     4. Append-only stock ledger (TypeError on update/delete of `StockMovement`).
     5. Dual console isolation (`/admin/` vs `/merchant/`).
5. **Run Verification Commands**:
   - `python -m pytest`
   - `ruff check .`
   - `ruff format --check .`
   - `python manage.py check`
   - `python manage.py makemigrations --check --dry-run`
   - `cd mobile && npm run typecheck`
   - `cd mobile && npm run lint`
   - `node scripts/check-responsive.mjs`
6. Write your work report in `/home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/teamwork_preview_worker_m2_1/changes.md` and handoff report in `/home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/teamwork_preview_worker_m2_1/handoff.md`.
7. Send a message to parent with your verification results and report path.
