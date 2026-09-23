# MetroDrip five-schema database contract

Implemented for the explicitly requested Figma alignment in PR #4. This supersedes
ADR-P3-013's decision to defer the logical split. It does not merge or deploy the PR.

- [Implementation PR](https://github.com/SecretlySpy/TIP_MetroDrip-Ecommerce/pull/4)
- [Updated editable ERD](https://www.figma.com/design/SmJIlTZ9ZVRxQ5eKucmrd0/MetroDrip?node-id=333-2)
- [Original ERD reference](https://www.figma.com/design/SmJIlTZ9ZVRxQ5eKucmrd0/MetroDrip?node-id=34-41)

## Ownership

| Logical schema | Django alias | Application tables | Framework tables |
|---|---|---|---|
| db_identity | identity | Customer, WishlistItem | Auth, groups, permissions, content types, admin log, sessions, OTP, JWT blacklist, auth M2M |
| db_catalog | catalog | Category, Product, ProductVariant, StockRecord, Reservation, StockMovement, IdempotencyRecord | — |
| db_orders | default | Order, OrderItem, OrderNumberSequence, StockHold, OutboxMessage, Payment, Review | — |
| db_fulfillment | fulfillment | ShippingZone, Shipment, DeviceToken, Notification | — |
| db_content | content | HomepageBanner, ContactMessage | Sites, flatpages, flatpage/sites M2M |

Each schema additionally owns a `core_serviceevent` queue and its own migration
history. There are 23 application model classes, including the replicated queue
model: 22 ordinary business/operational tables plus five physical queue tables.
All tables use InnoDB and utf8mb4. Django migrations are the sole DDL authority;
SQLAlchemy no longer creates a competing inventory schema.

These are five logical databases on one MySQL server. Django continues to host the
application modules and route their owner-specific queries. This is not a claim
that five independently deployed REST services now exist. The existing REST
inventory, shipping and notification providers remain selectable. Network-only
access for every domain would be a further application/service extraction.

## Relationship contract

Within one owner, real FKs, unique keys, cascades and PROTECT remain. Cross-owner
fields retain Python relationship access for compatibility but physically store
indexed BIGINT REF columns with `db_constraint=False`. No cross-schema FK or SQL
join is required by application pages. Catalog review/sales metrics use owner
read APIs; history uses frozen fields. The aggregate storefront/back-office can
prefetch owner-routed objects using separate queries.

| Referring table.column | Owner target | Deletion policy |
|---|---|---|
| accounts_wishlistitem.product_ref | Catalog.Product | Owner lifecycle CASCADE |
| orders_order.customer_ref | Identity.Customer | Owner lifecycle SET_NULL |
| orders_orderitem.variant_ref | Catalog.ProductVariant | Application PROTECT |
| inventory_reservation.order_ref | Orders.Order | Owner lifecycle SET_NULL |
| inventory_stockmovement.ref_order_ref | Orders.Order | Application PROTECT |
| reviews_review.customer_ref | Identity.Customer | Owner lifecycle CASCADE |
| reviews_review.product_ref | Catalog.Product | Owner lifecycle CASCADE |
| shipping_shipment.order_ref | Orders.Order | Unique REF; owner lifecycle CASCADE |
| notifications_devicetoken.customer_ref | Identity.Customer | Owner lifecycle CASCADE |
| notifications_notification.customer_ref | Identity.Customer | Owner lifecycle CASCADE |
| notifications_notification.order_ref | Orders.Order | Owner lifecycle SET_NULL |

`OrderItem.product_ref` is a separate immutable historical identity, not a live
Django relationship. It has no cascade or live lookup requirement.

A source deletion writes its cleanup events in the source transaction. After
commit, the owning module deletes or clears dependent references; the scheduler
retries incomplete events. An application PROTECT check prevents ordinary deletion
when audit/history references exist. This is deliberately not distributed FK
integrity: direct SQL and racing external writers must not bypass the lifecycle.
`validate_service_references` detects live orphaned references without joining
schemas. Soft references do not authorize destructive deletion of audit rows.

## Complete order-history snapshot

OrderItem captures product ID, SKU, product name, product slug, size, color, fit,
image URL, quantity and unit price (integer centavos). `variant_ref` and `order_id`
are frozen with them. ORM save/update/bulk-update/conflict-update guards and a
MySQL UPDATE trigger prevent rewriting purchased lines. Order shipping-address
JSON already captures the recipient/address. Invoices, packing slips, storefront
history, mobile order responses, payment descriptions and notification text read
snapshot values instead of current Catalog names/options.

Legacy rows are backfilled before export. `snapshot_source=legacy_catalog`
explicitly means current known catalog values were copied during migration;
original purchase-time names/images cannot be recovered from data never saved.
New orders use `snapshot_source=checkout`. The existing unit-price snapshot is
preserved during backfill. Missing legacy variants fail migration for repair.

## Core constraints and transaction boundaries

- Integer unsigned centavos for monetary columns; `total = subtotal + shipping_fee`.
- Unique SKU and product/size/color/fit tuple; database checks on variant axes.
- Positive order/reservation quantity and `0 <= reserved <= on_hand`.
- Ledger reason/sign checks, append-only ORM guards and SQL UPDATE/DELETE triggers.
- Unique payment provider reference; only verified provider events confirm payment.
- Database checks on order, payment, review, reservation, shipment, hold, outbox,
  customer-role, device-platform, notification-category and snapshot-source values.
- Review rating 1..5 and unique customer/product; delivered-purchase
  verification remains application logic. Category depth/root uniqueness remain
  application validation; MySQL enforces sibling-name uniqueness.
- Order transitions and number allocation lock Orders rows. Catalog stock mutations
  lock Catalog rows. Identity role synchronization and OTP use Identity transactions.

A transaction cannot atomically commit two databases. Payment and its durable
`order.fulfill_stock` outbox instruction commit together in Orders; Catalog is
contacted after commit. Fulfillment retries return the original committed totals,
so they cannot create a second sale. Expired-hold replacements use stable keys.
Uncertain or insufficient stock stays retryable rather than silently retiring work.

A full refund commits its stock-restoration instruction with the order transition.
The Catalog provider restores at most units actually sold for that order, releases
unconsumed holds, and deduplicates retries. Local multi-line restoration is atomic
in Catalog. The optional REST provider applies lines idempotently; temporary
partial delivery is resolved by retry. A paid order whose stock was never consumed
must not create inventory when refunded.

`OutboxMessage` dead letters and unfinished `ServiceEvent` rows require operational
visibility and retry. Neither queue makes a distributed transaction claim.

## Fresh setup

1. Create the five schemas with `scripts/bootstrap-service-schemas.sql` using a
   bootstrap account, and grant the application account the needed schema rights.
   Fresh Docker volumes use `docker/mysql-init.sql` (development) or
   `deploy/init-service-schemas.sh` (staging). The MySQL server enables
   `log_bin_trust_function_creators` so the schema migration account can create
   deterministic guard triggers without global SUPER privileges. Keep DDL
   privileges limited to trusted migration operators.
2. Set `DATABASE_LAYOUT=five` (the new default), configure MySQL credentials, then run:

   ```sh
   python manage.py migrate_service_schemas
   python manage.py validate_service_schemas
   python manage.py validate_service_references
   python manage.py sync_console_roles
   ```

3. Run the app and exactly one scheduler using the existing deployment instructions.
   Normal boot does not copy legacy data; migration and data transfer are separate.

Schema overrides are `MYSQL_SCHEMA_IDENTITY`, `MYSQL_SCHEMA_CATALOG`,
`MYSQL_SCHEMA_DEFAULT` (Orders), `MYSQL_SCHEMA_FULFILLMENT`, `MYSQL_SCHEMA_CONTENT`.
Per-owner credentials use `MYSQL_<ALIAS>_USER/PASSWORD/HOST/PORT`. Deployment
bootstrap scripts create the five standard names; create/grant custom names
explicitly and pass the same names to all app/scheduler processes. The inventory
sidecar must use Catalog's database and `order_ref`/`ref_order_ref` columns.

## Existing data: maintenance-window cutover

Do not point a running legacy installation at empty schemas and assume its data
will move. Take and verify a full backup. Rehearse on a restored copy first.

1. Stop web writes, workers, schedulers and sidecars. Keep the maintenance window
   open until all schemas and data checks pass.
2. With `DATABASE_LAYOUT=legacy` and `MYSQL_DATABASE` naming the old database, run
   the new migrations. They drop only cross-owner FKs, rename REF columns, add
   checks/SQL guards and backfill item snapshots. Existing source rows remain.
3. Export with `python manage.py transfer_service_data export /secure/export/path`.
   This writes five JSON files and a count/hash manifest; protect them as customer
   and authentication data. Nothing is uploaded or sent by the command.
4. Create fresh target schemas/grants, set `DATABASE_LAYOUT=five`, and run
   `python manage.py migrate_service_schemas`.
5. Import with `python manage.py transfer_service_data import /secure/export/path`.
   It checks file hashes, refuses nonempty business targets, preserves original
   PKs/M2M links and verifies per-model counts, physical ownership and live REFs.
   Only fresh framework defaults are replaced with source IDs.
6. Verify sign-in, order history, pending-payment fulfillment and ledger counts.
   Start the app/scheduler/selected providers only after acceptance.

Import is not atomic across five schemas. On failure, keep writes stopped, retain
the source and export, inspect the error, and rebuild only the disposable/fresh
targets before retry. Never delete a source database as part of this process.

Before any writes reach the new schemas, rollback can use the upgraded legacy
schema with this new code and `DATABASE_LAYOUT=legacy`. Once new writes start,
rollback requires a planned restore/reconciliation; an environment flip alone
would lose those writes. Reverting old migrations can restore database shape but
cannot reconstruct removed snapshot columns or unknown historical values.

## Verification

Actual MySQL 8.4 / Python 3.14 GitHub Actions tests, migration reversal and legacy
transfer rehearsal are tracked in `five-schema-alignment-progress.md`. Local
syntax checks are supplementary. Do not treat PR status alone as a passing release
gate; consult the latest PR checks before merge or deployment.
