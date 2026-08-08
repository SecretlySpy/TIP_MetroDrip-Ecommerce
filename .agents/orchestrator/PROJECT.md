# Project: MetroDrip E-Commerce System

## Architecture
- Web Application: Django web application with MySQL backend.
- Mobile Application: Expo React Native app under `mobile/`.
- Microservices / Sidecars: FastAPI sidecars under `services/` (`notifications`, `fulfillment`, `inventory`).
- Scripts & Tooling: UI layout check (`scripts/check-responsive.mjs`), Sidecar smoke test (`scripts/smoke-services.sh`), pytest suite, ruff linter/formatter.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | System Audit & Cross-Platform Baseline QA | Scan web, mobile, sidecars; run baseline pytest, ruff, django check, mobile tsc/eslint, responsive script, smoke-services.sh | None | DONE |
| 2 | FastAPI Sidecar Integration & Configuration | Wire up sidecars (notifications, fulfillment, inventory), auth token, fail-closed, health probes, contract parity | M1 | IN_PROGRESS |
| 3 | Refactoring, Performance & Invariant Hardening | Refactor bottlenecks/code smells, enforce 5 AGENTS.md hard invariants | M1, M2 | PLANNED |
| 4 | Comprehensive Final QA, Verification & Documentation | Re-run full test matrix, Forensic Auditor check, generate AI Documentation Notes.md & Tech Stack Setup Guide.md | M1, M2, M3 | PLANNED |

## Interface Contracts
### Web App (Django) ↔ Mobile App (React Native)
- REST APIs & Auth Tokens
- Inventory & Order endpoints

### Web App / Mobile ↔ Sidecars (FastAPI `services/`)
- Token auth header validation
- Service health endpoints (`/healthz/live`, `/healthz/ready`)
- Fail-closed fallback logic

## Hard Invariants (AGENTS.md)
1. Zero overselling (atomic stock checks/reservation).
2. Integer centavos currency storage (never floating point for money).
3. Webhook signature verification (X-Signature header check).
4. Append-only stock ledger (audit trail for inventory movements).
5. Dual console isolation (separate admin/staff access controls).
