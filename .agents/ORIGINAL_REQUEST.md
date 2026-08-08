# Original User Request

## Initial Request — 2026-08-09T01:52:56+08:00

<USER_REQUEST>
# Teamwork Project Prompt — Final

Execute a comprehensive QA pass, full system audit across Django web application and Expo React Native mobile application, sidecar integration, and codebase optimization for MetroDrip.

Working directory: `/home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce`
Integrity mode: development

## Requirements

### R1. Full System Audit & Gap Documentation
Scan the web application, mobile app (`mobile/`), and FastAPI sidecars (`services/`). Identify and document all remaining development phases, outstanding bugs, and pending feature requirements in `AI Documentation Notes.md` with explicit PASS/GAP mapping against AGENTS.md guidelines.

### R2. Comprehensive Cross-Platform QA Pass
Execute automated and empirical verification across all system components:
- Web: Pytest test suite (real MySQL), Django system checks, migration drift checks, responsive layout checks (60 routes/widths), dead CSS selector checks.
- Mobile: TypeScript typechecks (`tsc --noEmit`), ESLint compliance, component rendering, API contract alignment.
- Security & Performance: AGENTS.md invariant checks (zero overselling, integer centavos, webhook signature verification, append-only stock ledger, dual console isolation).

### R3. FastAPI Sidecar Integration & Configuration
Wire up and configure the optional strangler sidecars under `services/` (`notifications`, `fulfillment`, `inventory`), ensuring health probes, token authentication, fail-closed handling, and contract parity are fully verified.

### R4. Codebase Refactoring & Performance Optimization
Refactor and optimize identified performance bottlenecks or code smells in the codebase while ensuring zero errors, 100% accuracy, and strict adherence to AGENTS.md hard invariants.

## Acceptance Criteria

### Automated Verification
- [ ] All Python tests pass (`python -m pytest`) with 0 failures.
- [ ] Python linting & formatting checks pass clean (`ruff check .` and `ruff format --check .`).
- [ ] Django system checks pass clean (`python manage.py check` and `makemigrations --check --dry-run`).
- [ ] Mobile TypeScript typecheck passes clean (`cd mobile && npm run typecheck`).
- [ ] Mobile ESLint check passes clean (`cd mobile && npm run lint`).
- [ ] Responsive UI compliance passes 100% (`node scripts/check-responsive.mjs`).
- [ ] Sidecar service smoke script passes (`bash scripts/smoke-services.sh` or equivalent contract verification).

### Audit & System Integrity
- [ ] System audit report and gap analysis documented in `AI Documentation Notes.md`.
- [ ] Zero breaking changes introduced to existing database schema or API contracts.
- [ ] All AGENTS.md non-negotiable hard invariants remain 100% verified and satisfied.

</USER_REQUEST>
