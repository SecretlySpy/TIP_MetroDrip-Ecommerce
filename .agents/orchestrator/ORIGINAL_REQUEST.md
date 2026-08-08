# Original User Request

## Initial Request — 2026-08-09T01:52:56+08:00

<USER_REQUEST>
You are the Project Orchestrator for the MetroDrip project.

Working directory: `/home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/orchestrator`
User request file: `/home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/.agents/ORIGINAL_REQUEST.md`

Your objective is to drive and complete all requirements specified in the user request:

### Requirements Summary:
1. **R1. Full System Audit & Gap Documentation**: Scan web app, mobile app (`mobile/`), and FastAPI sidecars (`services/`). Identify and document all remaining development phases, outstanding bugs, and pending feature requirements in `AI Documentation Notes.md` with explicit PASS/GAP mapping against `AGENTS.md` guidelines.
2. **R2. Comprehensive Cross-Platform QA Pass**:
   - Web: Pytest test suite (real MySQL), Django system checks, migration drift checks, responsive layout checks (60 routes/widths), dead CSS selector checks.
   - Mobile: TypeScript typechecks (`tsc --noEmit`), ESLint compliance, component rendering, API contract alignment.
   - Security & Performance: AGENTS.md invariant checks (zero overselling, integer centavos, webhook signature verification, append-only stock ledger, dual console isolation).
3. **R3. FastAPI Sidecar Integration & Configuration**: Wire up and configure optional strangler sidecars under `services/` (`notifications`, `fulfillment`, `inventory`), ensuring health probes, token authentication, fail-closed handling, and contract parity are fully verified.
4. **R4. Codebase Refactoring & Performance Optimization**: Refactor and optimize identified performance bottlenecks or code smells in the codebase while ensuring zero errors, 100% accuracy, and strict adherence to AGENTS.md hard invariants.

### Protocols & Operating Guidelines:
- Strict adherence to `/home/kakashi70-0/Documents/GitHub/TIP_MetroDrip-Ecommerce/AGENTS.md` and `GEMINI.md`.
- Maintain `plan.md` and `progress.md` in your working directory (`.agents/orchestrator/`).
- Maintain `AI Documentation Notes.md` and `Tech Stack Setup Guide.md` at the project root.
- Spawn specialist subagents (explorers, implementers, reviewers, challengers) as needed to execute subtasks.
- When all requirements and acceptance criteria are 100% satisfied and verified, report completion to the Sentinel so a Victory Audit can be initiated.
</USER_REQUEST>
