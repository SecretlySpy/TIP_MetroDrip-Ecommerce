# Five-schema alignment implementation progress

Authorized scope: five logical schemas, Figma reference semantics, immutable order
history, complete ERD and core constraints. Working branch: codex/align-five-schema-erd.
Draft PR: https://github.com/SecretlySpy/TIP_MetroDrip-Ecommerce/pull/4

First implementation commit: fa8e11b2f96cc24199d5fdf9771d3d3770797710.
MySQL 8.4 / Python 3.14 CI run 34188199754 passed Django system checks,
migration drift and all six new schema integration tests. Full regression stopped
with 264 passes, 7 failures and 8 fixture setup errors. This is not a release gate pass.

Active work: fix owning-connection transactions (refund, OTP and role sync),
fixture database access, post-commit tests, idempotent stock replay, staging schema
bootstrap, formatting, deployment and reversible migration gates. Then rehearse
legacy data transfer, update Figma page 31:2 (file SmJIlTZ9ZVRxQ5eKucmrd0),
publish documentation and final verification evidence. No production database
has been migrated, and the PR remains draft.

Local dependency installation unavailable; actual runtime verification uses
disposable GitHub Actions MySQL databases. Local syntax compilation also passes.
