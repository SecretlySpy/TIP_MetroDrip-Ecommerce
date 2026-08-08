## 2026-08-08T18:00:31Z
<USER_REQUEST>
You are Reviewer 1 (Backend & Hard Invariants Reviewer).
Working directory: /home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/teamwork_preview_reviewer_m2_1
Project Scope document: /home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/orchestrator/PROJECT.md

Task:
Perform code review of the web application, backend models, views, and test suite.
1. Inspect recent changes and overall codebase quality.
2. Run and verify automated backend checks:
   - `python -m pytest`
   - `ruff check .`
   - `ruff format --check .`
   - `python manage.py check`
   - `python manage.py makemigrations --check --dry-run`
3. Verify compliance with the 5 AGENTS.md hard invariants:
   - Zero overselling (`select_for_update()`)
   - Integer centavos currency storage
   - Webhook signature verification
   - Append-only stock ledger (`StockMovement`)
   - Dual console isolation (`/admin/` vs `/merchant/`)
4. Write your review report in `/home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/teamwork_preview_reviewer_m2_1/review.md` and handoff report in `/home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/teamwork_preview_reviewer_m2_1/handoff.md`.
5. Send a message to parent with your verdict (APPROVE / VETO) and rationale.
</USER_REQUEST>
