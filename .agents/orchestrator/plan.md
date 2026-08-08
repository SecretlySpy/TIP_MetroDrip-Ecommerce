# Detailed Implementation Plan — MetroDrip Project

## Milestones & Work Breakdown

### Milestone 1: System Audit & Cross-Platform Baseline QA
- [ ] Dispatch 3 Explorers to perform read-only analysis:
  - Explorer 1 (`teamwork_preview_explorer_m1_1`): Web codebase audit (Django apps, models, views, pytest suite, ruff, migration dry-run).
  - Explorer 2 (`teamwork_preview_explorer_m1_2`): Mobile app audit (`mobile/` TypeScript compilation, ESLint, React Native components, API contracts).
  - Explorer 3 (`teamwork_preview_explorer_m1_3`): FastAPI sidecars audit (`services/notifications`, `services/fulfillment`, `services/inventory`) & scripts (`scripts/check-responsive.mjs`, `scripts/smoke-services.sh`).
- [ ] Aggregate findings and establish baseline pass/fail matrix for all tests & checks.
- [ ] Produce initial PASS/GAP assessment.

### Milestone 2: FastAPI Sidecar Integration & Configuration (R3)
- [ ] Worker fixes & configures sidecars (`notifications`, `fulfillment`, `inventory`).
- [ ] Implement health probes, token auth, fail-closed handling, and contract parity.
- [ ] Verify using `scripts/smoke-services.sh` or service verification tests.
- [ ] Reviewers & Challengers test sidecar resiliency.

### Milestone 3: Codebase Refactoring & Performance Optimization (R4 + Hard Invariants)
- [ ] Identify and resolve performance bottlenecks (N+1 queries, unindexed DB columns, inefficient loops).
- [ ] Verify strict adherence to 5 hard invariants:
  1. Zero overselling.
  2. Integer centavos currency.
  3. Webhook signature verification.
  4. Append-only stock ledger.
  5. Dual console isolation.
- [ ] Worker applies minimal refactorings; Reviewers & Challengers verify.

### Milestone 4: Comprehensive Cross-Platform QA Pass & Documentation (R1, R2, Docs)
- [ ] Run full automated verification suite:
  - Pytest (`python -m pytest`)
  - Ruff linting & formatting (`ruff check .`, `ruff format --check .`)
  - Django system checks & migration checks (`python manage.py check`, `makemigrations --check --dry-run`)
  - Mobile TypeScript (`cd mobile && npm run typecheck`)
  - Mobile ESLint (`cd mobile && npm run lint`)
  - Responsive UI script (`node scripts/check-responsive.mjs`)
  - Sidecar smoke script (`bash scripts/smoke-services.sh`)
- [ ] Dispatch Forensic Auditor for integrity check.
- [ ] Worker creates `AI Documentation Notes.md` and `Tech Stack Setup Guide.md` at root.
- [ ] Final victory report to Sentinel.
