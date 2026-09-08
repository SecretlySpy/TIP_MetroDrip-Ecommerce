# Project handover — MetroDrip five-schema alignment

Generated: 2026-09-08. Audience: repository maintainer or subsequent engineering session.

## 1. Outcome

The requested five logical schemas, Figma reference semantics, complete order-history
snapshot, additional ERD models and core constraints are implemented and verified.
The implementation is available in [PR #4](https://github.com/SecretlySpy/TIP_MetroDrip-Ecommerce/pull/4)
on `codex/align-five-schema-erd`. No production database has been migrated; the PR
is unmerged. The only remaining red CI job is the pre-existing Expo dependency check.

## 2. Scope

Implemented: five owner connections; local FKs and indexed cross-owner REF names;
durable lifecycle cleanup; purchase identity/options/image/quantity/price snapshots;
MySQL checks and immutable snapshot/ledger triggers; idempotent post-commit stock
fulfillment/refunds; Django/SQLAlchemy mapping alignment; legacy transfer tooling.

The [editable Figma ERD](https://www.figma.com/design/SmJIlTZ9ZVRxQ5eKucmrd0/MetroDrip?node-id=333-2)
contains 23 application model classes across 27 physical application/queue cards,
plus framework ownership, nullable columns and constraint notes. Structural validation
found no missing cards or clipped text. Detail and overview screenshots were reviewed.
The original board remains as a reference on the same ERD page.

## 3. Architecture and operations

| Django alias | MySQL schema | Owner |
|---|---|---|
| identity | db_identity | Accounts and authentication |
| catalog | db_catalog | Catalog and stock ledger |
| default | db_orders | Orders, payments and reviews |
| fulfillment | db_fulfillment | Shipping and notifications |
| content | db_content | CMS, flatpages and sites |

Each schema owns a physical `core_serviceevent` queue and migration history.
This is five logical databases in the existing application deployment, not five
new independently deployed REST services. Existing provider seams remain selectable.

The [contract and maintenance-window cutover guide](five-schema-alignment.md) covers
bootstrap/grants, schema overrides, sensitive exports, import recovery and rollback.
Payment/refund work uses Orders' outbox; stock writes lock Catalog rows. Cross-owner
delete intent commits in the source owner and cleanup is replayed through its queue.

## 4. Decisions

ADR-DB-001 supersedes ADR-P3-013's deferral because the repository owner explicitly
requested the logical split. Physical FKs remain owner-local; cross-service protection
is application policy plus a live-reference detector. No distributed atomicity is
claimed. Legacy history is marked `legacy_catalog`, since unstored purchase-time
labels cannot be reconstructed. No source tables are deleted during transfer.

## 5. Module status

All implementation work is complete. Principal entry points:

- `config/database_layout.py`: owner routing and connection configuration.
- `config/db_backend/base.py`: owner-aware historical migration DDL.
- `apps/core/lifecycle.py`: durable cross-owner cleanup and application protection.
- `apps/core/management/commands/`: migrate/validate/transfer management commands.
- `apps/orders/models.py`: immutable snapshots and Orders-owned durable records.
- `apps/payments/holds.py`, `apps/orders/refunds.py`: post-commit stock intent.
- `apps/inventory/providers/` and `services/inventory/`: owner stock and REST parity.
- `scripts/rehearse-schema-transfer.py`: isolated CI backfill/transfer rehearsal.

## 6. Executed verification

Tested code commit: `072db6303c55e6be84e22062458899fa8957617a`.
Subsequent handover changes are documentation only.

| Gate | Result | Evidence |
|---|---|---|
| Focused MySQL schema/transaction/SQL guard tests | 10 passed | [Run 34190300445](https://github.com/SecretlySpy/TIP_MetroDrip-Ecommerce/actions/runs/34190300445) |
| Full regression, including local/REST refund parity | 669 passed, 154.65 seconds | Same run; MySQL 8.4, Python 3.14 |
| Legacy snapshot backfill and data transfer | Passed | Same run; hashes, counts, PKs, auth M2M and all 11 live REF fields verified |
| Standard QA | Passed | [Job 101946815185](https://github.com/SecretlySpy/TIP_MetroDrip-Ecommerce/actions/runs/34190300448/job/101946815185) |
| Lint, format, Django check and migration drift | Passed | Standard QA |
| Staging security settings and reversible migrations | Passed | Standard QA, including Catalog reversal and migration of all five schemas |
| Disposable staging HTTPS/persistence | Passed | [Job 101946814945](https://github.com/SecretlySpy/TIP_MetroDrip-Ecommerce/actions/runs/34190300448/job/101946814945) |
| Local compile and whitespace checks | Passed | Python compileall and git diff --check |
| Mobile Expo dependency alignment | Pre-existing failure | [Main baseline](https://github.com/SecretlySpy/TIP_MetroDrip-Ecommerce/actions/runs/34033418208/job/101487057080), also fails in PR |

Mobile dependency files are unchanged. The failing job requests newer compatible
Expo package patch versions and stops before later mobile build steps. This PR does
not claim those later build steps passed. The regression suite reports existing
static-directory, JWT test-key and upstream deprecation warnings.

## 7. Next operational steps

1. Review PR #4, its Figma board and the cutover guide.
2. Resolve the independent Expo dependency update before requiring an entirely green
   repository-wide CI run; it is not a schema implementation defect.
3. Before production cutover, rehearse against a restored copy of real data, verify
   backup restoration, then schedule the documented write-free maintenance window.
4. Monitor dead Orders outbox records and unfinished lifecycle queue rows after cutover.

## 8. Critical context and limits

- An Orders transaction cannot roll back Catalog or Identity. Preserve owner aliases
  and post-commit durable intent in future changes.
- Refunds restore only audited sold units. Already-restored or never-consumed stock
  cannot be added again. The optional REST provider can temporarily deliver a refund
  partly across lines; idempotent retry completes it.
- A historical experimental REST ledger that omitted order references requires
  explicit audit reconciliation; never invent missing sale relationships.
- Category depth/root uniqueness are application validation. Live REF protection
  is not a database FK and must not be bypassed with direct cross-owner SQL writes.
- Snapshot and stock movement SQL guards stay active in tests. Test teardown uses
  TRUNCATE only on disposable databases because normal DELETE correctly fails.
- Trigger creation uses a trusted DDL account; Compose configures MySQL's
  log_bin_trust_function_creators to avoid granting global SUPER to the app user.
- Import is not atomic across databases. Before target writes, the upgraded source
  remains usable in legacy mode. After target writes, rollback needs reconciliation.
- Local runtime packages were unavailable. Runtime claims above are from actual
  disposable GitHub Actions databases, not inferred from syntax compilation.

## 9. Open decisions

No unanswered product decision blocks this implementation. Deployment timing,
production backup verification and the independent Expo dependency update remain
with the repository maintainer. Neither production deployment nor merge was performed.
