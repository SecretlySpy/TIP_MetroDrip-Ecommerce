"""Seed a deterministic, idempotent catalog for local demos and QA."""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
from apps.inventory.models import MovementReason, StockMovement, StockRecord

# Each product owns a category and two product-specific colors so the seed data
# exercises the complete three-axis variant model without ambiguous shared data.
PRODUCT_SEEDS = (
    {
        "code": "MTEE",
        "name": "Metro Essential Tee",
        "slug": "metro-essential-tee",
        "description": "A heavyweight everyday tee inspired by the city rail grid.",
        "category_name": "T-Shirts",
        "category_slug": "t-shirts",
        "base_price": 89900,
        "colors": (("Jet Black", "JBLK"), ("Concrete White", "CWHT")),
    },
    {
        "code": "SHOD",
        "name": "Skyline Pullover Hoodie",
        "slug": "skyline-pullover-hoodie",
        "description": "A brushed-fleece hoodie made for cool commutes and late nights.",
        "category_name": "Hoodies",
        "category_slug": "hoodies",
        "base_price": 189900,
        "colors": (("Midnight Navy", "MNAV"), ("Asphalt Gray", "AGRY")),
    },
    {
        "code": "TCAR",
        "name": "Transit Utility Cargo Pants",
        "slug": "transit-utility-cargo-pants",
        "description": "Utility cargo pants with a streetwear silhouette and practical storage.",
        "category_name": "Pants",
        "category_slug": "pants",
        "base_price": 219900,
        "colors": (("Route Olive", "ROLV"), ("Signal Black", "SBLK")),
    },
    {
        "code": "POVR",
        "name": "Platform Twill Overshirt",
        "slug": "platform-twill-overshirt",
        "description": "A structured twill layer designed for year-round city wear.",
        "category_name": "Overshirts",
        "category_slug": "overshirts",
        "base_price": 169900,
        "colors": (("Rust Line", "RUST"), ("Steel Blue", "STBL")),
    },
    {
        "code": "NRJK",
        "name": "Night Route Windbreaker",
        "slug": "night-route-windbreaker",
        "description": "A lightweight windbreaker with high-visibility urban color options.",
        "category_name": "Outerwear",
        "category_slug": "outerwear",
        "base_price": 249900,
        "colors": (("Neon Lime", "NLIM"), ("Carbon Black", "CBLK")),
    },
)

# Compact, explicit fit tokens keep every deterministic SKU readable and well
# below ProductVariant.sku's 64-character database limit.
FIT_SKU_CODES = {
    Fit.SLIM: "SLM",
    Fit.REGULAR: "REG",
    Fit.OVERSIZED: "OVR",
}


class Command(BaseCommand):
    """Create the complete demo variant matrix without rewriting live stock."""

    help = "Seed five demo products with all size/color/fit variants and initial inventory."

    def handle(self, *args, **options):
        """Create deterministic rows and report only rows created by this run."""
        # Separate counters make repeated runs observable: a fully seeded database
        # reports zero for every value instead of concealing accidental duplicates.
        created_counts = {
            "categories": 0,
            "products": 0,
            "variants": 0,
            "stock_records": 0,
            "stock_movements": 0,
        }

        # One transaction prevents a partially seeded catalog or a stock balance
        # without its matching audit entry if any later row fails to persist.
        with transaction.atomic():
            for product_seed in PRODUCT_SEEDS:
                # Stable category slugs make reruns update descriptive seed fields
                # while preserving the same database identity.
                category, category_created = Category.objects.update_or_create(
                    slug=product_seed["category_slug"],
                    defaults={"name": product_seed["category_name"]},
                )
                created_counts["categories"] += int(category_created)

                # Stable product slugs let developers safely refresh demo metadata
                # without creating a second copy of a known seed product.
                product, product_created = Product.objects.update_or_create(
                    slug=product_seed["slug"],
                    defaults={
                        "name": product_seed["name"],
                        "description": product_seed["description"],
                        "category": category,
                        "base_price": product_seed["base_price"],
                        "images": [],
                        "is_active": True,
                    },
                )
                created_counts["products"] += int(product_created)

                # Iterating the model enums guarantees the seed matrix automatically
                # covers every database-supported size and fit value.
                for size in Size.values:
                    for color_name, color_code in product_seed["colors"]:
                        for fit in Fit.values:
                            sku = (
                                f"MD-{product_seed['code']}-{size}-{color_code}-"
                                f"{FIT_SKU_CODES[fit]}"
                            )

                            # The variant axes are the natural key. Updating the SKU
                            # here keeps it stable even if an earlier seed draft differed.
                            variant, variant_created = ProductVariant.objects.update_or_create(
                                product=product,
                                size=size,
                                color=color_name,
                                fit=fit,
                                defaults={"sku": sku, "price_override": None},
                            )
                            created_counts["variants"] += int(variant_created)

                            # Stock is intentionally create-only: a rerun must never
                            # erase sales, reservations, restocks, or manual adjustments.
                            _stock, stock_created = StockRecord.objects.get_or_create(
                                variant=variant,
                                defaults={
                                    "qty_on_hand": 10,
                                    "qty_reserved": 0,
                                    "low_stock_threshold": 5,
                                },
                            )
                            created_counts["stock_records"] += int(stock_created)

                            if stock_created:
                                # The initial +10 is a physical restock and must have
                                # exactly one immutable ledger row for audit parity.
                                StockMovement.objects.create(
                                    variant=variant,
                                    delta=10,
                                    reason=MovementReason.RESTOCK,
                                )
                                created_counts["stock_movements"] += 1

        # A compact result is friendly to both humans and CI log parsers.
        summary = ", ".join(f"{label}={count}" for label, count in created_counts.items())
        self.stdout.write(self.style.SUCCESS(f"Demo seed complete: {summary}"))
