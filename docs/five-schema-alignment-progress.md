# Five-schema alignment implementation progress

Authorized scope: five logical schemas, Figma reference semantics, immutable order
history, full ERD and core constraints. Branch: `codex/align-five-schema-erd`.
PR: https://github.com/SecretlySpy/TIP_MetroDrip-Ecommerce/pull/4
Figma: https://www.figma.com/design/SmJIlTZ9ZVRxQ5eKucmrd0/MetroDrip?node-id=333-2
Runbook: [five-schema-alignment.md](five-schema-alignment.md).

## Completed implementation

- Five owner connections; local FKs and indexed physical cross-owner REF names.
- Durable source-owned lifecycle queues, application protection and orphan detection.
- Purchase-time identity/options/image/quantity/price snapshots with legacy provenance.
- MySQL enum/money/quantity/uniqueness checks and immutable snapshot/ledger triggers.
- Post-commit payment/refund stock intent, idempotent replay and sold-unit refund cap.
- Correct Django/SQLAlchemy inventory mapping; Django-only DDL ownership.
- Copy-based legacy transfer with hashes, original IDs/M2M and count/reference checks.
- Figma: 23 model classes, all 27 physical application/queue cards, framework
  ownership, nullability and constraint notes. Detail and overview screenshots reviewed.
- ADR-DB-001, setup guide and implementation documentation updated.

## Executed evidence so far

- Syntax compilation and `git diff --check`: passed locally.
- Earlier MySQL 8.4 / Python 3.14 regression reached 659 passed / 4 failed.
  Fixes for those failures are committed. This was not a final release pass.
- Staging deployment job 101945544647 (run 34189867845): PASSED, including disposable
  HTTPS startup, static files, demo seed and persistence after container recreation.
- Current commit under verification: 6b973d2eaa371a6b03996dfc09e5296079d60598.
  Schema tests, legacy transfer and full regression run: 34189867755.
- All 9 focused schema/transaction tests PASSED. Legacy transfer/backfill PASSED,
  verifying hashes, model counts, original PK/M2M links and 11 live REF fields.
- Full regression in run 34189867755: 666 PASSED (165.38 seconds).
- Formatting corrections are applied. A final run adds explicit SQL audit mutation
  rejection and REST/local refund reference/replay tests.
- Mobile Expo dependency alignment also fails on main: run 34033418208, job
  101487057080. No mobile dependency files are changed by this PR.

No production database was migrated, no deployment was requested, and the PR remains
unmerged. Runtime verification uses disposable GitHub Actions databases because local
Python does not have the required packages. Latest final results will replace this
in-progress verification record before handoff.
