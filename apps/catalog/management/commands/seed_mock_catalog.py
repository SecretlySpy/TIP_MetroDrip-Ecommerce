"""Top the catalog up with deterministic placeholder products (Epic B, B-3).

Deliberately separate from `seed_demo`: that command's five-product /
180-variant output is a contract relied on by the staging preview and several
tests, so bulk placeholder data gets its own command rather than inflating it.

Idempotency comes from natural keys, not from counting. Every placeholder slot
is derived from (category, audience, sequence), so a rerun resolves to the same
slugs, `get_or_create` finds them, and nothing is written. Existing stock,
reservations, thresholds, and ledger rows are never touched.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Category, Product, ProductVariant
from apps.catalog.seed_catalog import (
    AUDIENCES,
    MOCK_STOCK_QTY,
    allocate_round_robin,
    mock_price,
    mock_product_name,
    mock_product_slug,
    mock_sku,
    mock_variant_axes,
)
from apps.inventory.models import MovementReason, StockMovement, StockRecord

DEFAULT_COUNT = 100


class Command(BaseCommand):
    help = (
        "Create deterministic placeholder products spread evenly across every "
        "audience subcategory. Safe to rerun: existing rows are left untouched."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=DEFAULT_COUNT,
            help=(
                f"How many placeholder products the catalog should hold "
                f"(default {DEFAULT_COUNT}). This counts placeholders only, not "
                f"the hand-authored catalog, so a database with 12 real products "
                f"ends up with {DEFAULT_COUNT} + 12."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be created without writing anything.",
        )

    def handle(self, *args, **options):
        count = options["count"]
        dry_run = options["dry_run"]

        if count < 0:
            self.stderr.write(self.style.ERROR("--count cannot be negative."))
            return

        if not Category.objects.filter(parent__isnull=True).exists():
            self.stderr.write(
                self.style.ERROR(
                    "No main categories exist, so there is nothing to nest placeholders "
                    "under. Run `manage.py seed_demo` first."
                )
            )
            return

        leaves, categories_created = self._ensure_audience_categories(dry_run)

        existing_mock = Product.objects.filter(is_mock=True).count()
        if existing_mock > count:
            self.stdout.write(
                self.style.WARNING(
                    f"{existing_mock} placeholder products already exist, which is more "
                    f"than the requested {count}. Nothing was created or removed — this "
                    f"command never deletes catalog rows."
                )
            )

        plan = self._build_plan(count, leaves)
        stats = self._apply_plan(plan, dry_run)
        stats["categories_created"] = categories_created

        self._report(stats, count, leaves, dry_run)

    # ------------------------------------------------------------------ setup

    def _ensure_audience_categories(self, dry_run):
        """Make sure every main category has its audience children.

        Migration 0003 back-fills these, but only for categories that existed
        when it ran. A database migrated before being seeded has no categories
        at that point, and new main categories can be added later, so the
        command re-establishes the invariant instead of assuming it.
        """
        roots = list(Category.objects.filter(parent__isnull=True).order_by("slug"))
        leaves = []
        created = 0

        for root in roots:
            for audience in AUDIENCES:
                slug = f"{root.slug}-{audience['slug_suffix']}"
                child = Category.objects.filter(slug=slug).first()
                if child is None:
                    created += 1
                    # A dry run still needs the slot so the distribution can be
                    # planned and reported; only the write is skipped.
                    if not dry_run:
                        child = Category.objects.create(
                            slug=slug, name=audience["name"], parent=root
                        )
                leaves.append((root, audience, child))

        return leaves, created

    def _build_plan(self, count, leaves):
        """Assign each placeholder slot to a leaf category, evenly and in order."""
        per_leaf = allocate_round_robin(count, len(leaves))

        plan = []
        index = 0
        for (root, audience, child), quota in zip(leaves, per_leaf, strict=True):
            for sequence in range(1, quota + 1):
                plan.append(
                    {
                        "root": root,
                        "audience": audience,
                        "category": child,
                        "sequence": sequence,
                        "index": index,
                    }
                )
                index += 1
        return plan

    # ------------------------------------------------------------------ write

    def _apply_plan(self, plan, dry_run):
        stats = {
            "products_created": 0,
            "products_existing": 0,
            "variants_created": 0,
            "stock_records_created": 0,
            "movements_created": 0,
        }

        for slot in plan:
            slug = mock_product_slug(
                slot["root"].slug, slot["audience"]["slug_suffix"], slot["sequence"]
            )

            existing = Product.objects.filter(slug=slug).first()
            if existing is not None:
                stats["products_existing"] += 1
                if not dry_run:
                    self._heal_product_graph(existing, slot, stats)
                continue

            if dry_run:
                stats["products_created"] += 1
                stats["variants_created"] += 1
                stats["stock_records_created"] += 1
                stats["movements_created"] += 1
                continue

            self._create_product_graph(slug, slot, stats)

        return stats

    @transaction.atomic
    def _heal_product_graph(self, product, slot, stats):
        """Restore inventory rows that a placeholder is missing.

        The atomic create below means a healthy database never needs this. It
        exists for the case where the catalog tables outlived the inventory
        ones — a partially reversed migration, a restore from a partial dump —
        which would otherwise leave an unbuyable listing that a rerun silently
        skipped over.

        Strictly additive: an existing StockRecord is never read back or
        rewritten, so operational quantities, reservations, and thresholds
        survive untouched.
        """
        root, audience, index = slot["root"], slot["audience"], slot["index"]

        variant = product.variants.first()
        if variant is None:
            variant = ProductVariant.objects.create(
                product=product,
                sku=mock_sku(root.slug, audience["code"], slot["sequence"]),
                **mock_variant_axes(index),
            )
            stats["variants_created"] += 1

        if not StockRecord.objects.filter(variant=variant).exists():
            StockRecord.objects.create(variant=variant, qty_on_hand=MOCK_STOCK_QTY)
            stats["stock_records_created"] += 1

            # Open the ledger only when it is genuinely empty. If the movements
            # outlived the stock row, a second +25 would make the ledger total
            # disagree with qty_on_hand — and being append-only, it could never
            # be corrected afterwards.
            if not StockMovement.objects.filter(variant=variant).exists():
                StockMovement.objects.create(
                    variant=variant, delta=MOCK_STOCK_QTY, reason=MovementReason.RESTOCK
                )
                stats["movements_created"] += 1

    @transaction.atomic
    def _create_product_graph(self, slug, slot, stats):
        """Create one placeholder and its inventory rows, all-or-nothing.

        A product without its variant, stock record, and opening ledger entry
        would be an unbuyable listing and a hole in the audit trail, so the
        whole graph shares one transaction.
        """
        root, audience, index = slot["root"], slot["audience"], slot["index"]

        product = Product.objects.create(
            slug=slug,
            name=mock_product_name(root.name, audience["name"], slot["sequence"]),
            description=(
                f"Placeholder {audience['name'].lower()}'s {root.name.lower()} used to "
                f"exercise category browsing at realistic catalog scale."
            ),
            category=slot["category"],
            base_price=mock_price(index),
            images=[],
            is_active=True,
            is_mock=True,
        )
        stats["products_created"] += 1

        variant = ProductVariant.objects.create(
            product=product,
            sku=mock_sku(root.slug, audience["code"], slot["sequence"]),
            **mock_variant_axes(index),
        )
        stats["variants_created"] += 1

        StockRecord.objects.create(variant=variant, qty_on_hand=MOCK_STOCK_QTY)
        stats["stock_records_created"] += 1

        # Opening balance, so qty_on_hand always reconciles against the ledger.
        StockMovement.objects.create(
            variant=variant, delta=MOCK_STOCK_QTY, reason=MovementReason.RESTOCK
        )
        stats["movements_created"] += 1

    # ----------------------------------------------------------------- report

    def _report(self, stats, count, leaves, dry_run):
        prefix = "DRY RUN — would create" if dry_run else "Created"

        self.stdout.write(
            f"{prefix}: categories={stats['categories_created']}, "
            f"products={stats['products_created']}, "
            f"variants={stats['variants_created']}, "
            f"stock_records={stats['stock_records_created']}, "
            f"movements={stats['movements_created']}"
        )
        self.stdout.write(f"Existing placeholders left untouched: {stats['products_existing']}")

        active = Product.objects.filter(is_active=True).count()
        mock = Product.objects.filter(is_mock=True).count()
        self.stdout.write(
            f"Catalog now holds {active} active products "
            f"({mock} placeholders across {len(leaves)} subcategories, target {count})."
        )

        if not dry_run and stats["products_created"]:
            self.stdout.write(self.style.SUCCESS("Mock catalog seed complete."))
