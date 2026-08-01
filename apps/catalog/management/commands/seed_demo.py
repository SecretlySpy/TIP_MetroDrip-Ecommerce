"""Seed a deterministic, idempotent catalog for local demos and QA."""

from django.conf import settings
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
from apps.cms.models import HomepageBanner
from apps.inventory.models import MovementReason, StockMovement, StockRecord
from apps.shipping.models import ShippingZone

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
    {
        "code": "S1",
        "name": "Sector Beanie 1",
        "slug": "sector-beanie-1",
        "description": "Essential headwear for the urban environment.",
        "category_name": "Headwear",
        "category_slug": "headwear",
        "base_price": 450000,
        "colors": (("Navy", "NAVY"), ("Black", "BLAC")),
    },
    {
        "code": "D2",
        "name": "District Beanie 2",
        "slug": "district-beanie-2",
        "description": "Essential headwear for the urban environment.",
        "category_name": "Headwear",
        "category_slug": "headwear",
        "base_price": 430000,
        "colors": (("Cobalt", "COBA"), ("Bone", "BONE")),
    },
    {
        "code": "N3",
        "name": "Neon Vest 3",
        "slug": "neon-vest-3",
        "description": "Essential overshirts for the urban environment.",
        "category_name": "Overshirts",
        "category_slug": "overshirts",
        "base_price": 190000,
        "colors": (("Gray", "GRAY"), ("Bone", "BONE")),
    },
    {
        "code": "S4",
        "name": "Sector Sneakers 4",
        "slug": "sector-sneakers-4",
        "description": "Essential footwear for the urban environment.",
        "category_name": "Footwear",
        "category_slug": "footwear",
        "base_price": 100000,
        "colors": (("Slate", "SLAT"), ("Black", "BLAC")),
    },
    {
        "code": "V5",
        "name": "Void Jacket 5",
        "slug": "void-jacket-5",
        "description": "Essential outerwear for the urban environment.",
        "category_name": "Outerwear",
        "category_slug": "outerwear",
        "base_price": 280000,
        "colors": (("Sand", "SAND"), ("Bone", "BONE")),
    },
    {
        "code": "P6",
        "name": "Pulse Windbreaker 6",
        "slug": "pulse-windbreaker-6",
        "description": "Essential outerwear for the urban environment.",
        "category_name": "Outerwear",
        "category_slug": "outerwear",
        "base_price": 230000,
        "colors": (("Neon", "NEON"), ("Rust", "RUST")),
    },
    {
        "code": "D7",
        "name": "District Windbreaker 7",
        "slug": "district-windbreaker-7",
        "description": "Essential outerwear for the urban environment.",
        "category_name": "Outerwear",
        "category_slug": "outerwear",
        "base_price": 420000,
        "colors": (("Crimson", "CRIM"), ("Slate", "SLAT")),
    },
    {
        "code": "U8",
        "name": "Urban Bag 8",
        "slug": "urban-bag-8",
        "description": "Essential accessories for the urban environment.",
        "category_name": "Accessories",
        "category_slug": "accessories",
        "base_price": 130000,
        "colors": (("Sand", "SAND"), ("Slate", "SLAT")),
    },
    {
        "code": "D9",
        "name": "District Vest 9",
        "slug": "district-vest-9",
        "description": "Essential overshirts for the urban environment.",
        "category_name": "Overshirts",
        "category_slug": "overshirts",
        "base_price": 50000,
        "colors": (("Bone", "BONE"), ("Slate", "SLAT")),
    },
    {
        "code": "U10",
        "name": "Urban Windbreaker 10",
        "slug": "urban-windbreaker-10",
        "description": "Essential outerwear for the urban environment.",
        "category_name": "Outerwear",
        "category_slug": "outerwear",
        "base_price": 100000,
        "colors": (("Rust", "RUST"), ("Olive", "OLIV")),
    },
    {
        "code": "V11",
        "name": "Vertex Bag 11",
        "slug": "vertex-bag-11",
        "description": "Essential accessories for the urban environment.",
        "category_name": "Accessories",
        "category_slug": "accessories",
        "base_price": 230000,
        "colors": (("Cobalt", "COBA"), ("Gray", "GRAY")),
    },
    {
        "code": "D12",
        "name": "District Cap 12",
        "slug": "district-cap-12",
        "description": "Essential headwear for the urban environment.",
        "category_name": "Headwear",
        "category_slug": "headwear",
        "base_price": 260000,
        "colors": (("White", "WHIT"), ("Bone", "BONE")),
    },
    {
        "code": "S13",
        "name": "Shift Sneakers 13",
        "slug": "shift-sneakers-13",
        "description": "Essential footwear for the urban environment.",
        "category_name": "Footwear",
        "category_slug": "footwear",
        "base_price": 290000,
        "colors": (("Slate", "SLAT"), ("Navy", "NAVY")),
    },
    {
        "code": "S14",
        "name": "Shift Tee 14",
        "slug": "shift-tee-14",
        "description": "Essential t-shirts for the urban environment.",
        "category_name": "T-Shirts",
        "category_slug": "t-shirts",
        "base_price": 210000,
        "colors": (("Rust", "RUST"), ("Slate", "SLAT")),
    },
    {
        "code": "S15",
        "name": "Shift Cargo 15",
        "slug": "shift-cargo-15",
        "description": "Essential pants for the urban environment.",
        "category_name": "Pants",
        "category_slug": "pants",
        "base_price": 450000,
        "colors": (("White", "WHIT"), ("Navy", "NAVY")),
    },
    {
        "code": "P16",
        "name": "Pulse Tee 16",
        "slug": "pulse-tee-16",
        "description": "Essential t-shirts for the urban environment.",
        "category_name": "T-Shirts",
        "category_slug": "t-shirts",
        "base_price": 100000,
        "colors": (("Black", "BLAC"), ("Crimson", "CRIM")),
    },
    {
        "code": "G17",
        "name": "Grid Vest 17",
        "slug": "grid-vest-17",
        "description": "Essential overshirts for the urban environment.",
        "category_name": "Overshirts",
        "category_slug": "overshirts",
        "base_price": 60000,
        "colors": (("White", "WHIT"), ("Slate", "SLAT")),
    },
    {
        "code": "S18",
        "name": "Sector Sneakers 18",
        "slug": "sector-sneakers-18",
        "description": "Essential footwear for the urban environment.",
        "category_name": "Footwear",
        "category_slug": "footwear",
        "base_price": 220000,
        "colors": (("Sand", "SAND"), ("White", "WHIT")),
    },
    {
        "code": "M19",
        "name": "Metro Tee 19",
        "slug": "metro-tee-19",
        "description": "Essential t-shirts for the urban environment.",
        "category_name": "T-Shirts",
        "category_slug": "t-shirts",
        "base_price": 320000,
        "colors": (("Rust", "RUST"), ("Navy", "NAVY")),
    },
    {
        "code": "S20",
        "name": "Shift Cargo 20",
        "slug": "shift-cargo-20",
        "description": "Essential pants for the urban environment.",
        "category_name": "Pants",
        "category_slug": "pants",
        "base_price": 420000,
        "colors": (("Slate", "SLAT"), ("White", "WHIT")),
    },
    {
        "code": "D21",
        "name": "District Sneakers 21",
        "slug": "district-sneakers-21",
        "description": "Essential footwear for the urban environment.",
        "category_name": "Footwear",
        "category_slug": "footwear",
        "base_price": 370000,
        "colors": (("Cobalt", "COBA"), ("Olive", "OLIV")),
    },
    {
        "code": "V22",
        "name": "Void Cargo 22",
        "slug": "void-cargo-22",
        "description": "Essential pants for the urban environment.",
        "category_name": "Pants",
        "category_slug": "pants",
        "base_price": 280000,
        "colors": (("White", "WHIT"), ("Rust", "RUST")),
    },
    {
        "code": "V23",
        "name": "Vertex Jacket 23",
        "slug": "vertex-jacket-23",
        "description": "Essential outerwear for the urban environment.",
        "category_name": "Outerwear",
        "category_slug": "outerwear",
        "base_price": 310000,
        "colors": (("Black", "BLAC"), ("Navy", "NAVY")),
    },
    {
        "code": "M24",
        "name": "Metro Tee 24",
        "slug": "metro-tee-24",
        "description": "Essential t-shirts for the urban environment.",
        "category_name": "T-Shirts",
        "category_slug": "t-shirts",
        "base_price": 60000,
        "colors": (("Sand", "SAND"), ("Neon", "NEON")),
    },
    {
        "code": "G25",
        "name": "Grid Vest 25",
        "slug": "grid-vest-25",
        "description": "Essential overshirts for the urban environment.",
        "category_name": "Overshirts",
        "category_slug": "overshirts",
        "base_price": 230000,
        "colors": (("Gray", "GRAY"), ("Olive", "OLIV")),
    },
    {
        "code": "G26",
        "name": "Grid Beanie 26",
        "slug": "grid-beanie-26",
        "description": "Essential headwear for the urban environment.",
        "category_name": "Headwear",
        "category_slug": "headwear",
        "base_price": 380000,
        "colors": (("Neon", "NEON"), ("Cobalt", "COBA")),
    },
    {
        "code": "N27",
        "name": "Neon Beanie 27",
        "slug": "neon-beanie-27",
        "description": "Essential headwear for the urban environment.",
        "category_name": "Headwear",
        "category_slug": "headwear",
        "base_price": 90000,
        "colors": (("Neon", "NEON"), ("Bone", "BONE")),
    },
    {
        "code": "U28",
        "name": "Urban Shorts 28",
        "slug": "urban-shorts-28",
        "description": "Essential pants for the urban environment.",
        "category_name": "Pants",
        "category_slug": "pants",
        "base_price": 300000,
        "colors": (("Rust", "RUST"), ("Cobalt", "COBA")),
    },
    {
        "code": "C29",
        "name": "Core Cargo 29",
        "slug": "core-cargo-29",
        "description": "Essential pants for the urban environment.",
        "category_name": "Pants",
        "category_slug": "pants",
        "base_price": 110000,
        "colors": (("White", "WHIT"), ("Olive", "OLIV")),
    },
    {
        "code": "G30",
        "name": "Grid Socks 30",
        "slug": "grid-socks-30",
        "description": "Essential accessories for the urban environment.",
        "category_name": "Accessories",
        "category_slug": "accessories",
        "base_price": 190000,
        "colors": (("White", "WHIT"), ("Bone", "BONE")),
    },
    {
        "code": "N31",
        "name": "Neon Tee 31",
        "slug": "neon-tee-31",
        "description": "Essential t-shirts for the urban environment.",
        "category_name": "T-Shirts",
        "category_slug": "t-shirts",
        "base_price": 400000,
        "colors": (("Slate", "SLAT"), ("Bone", "BONE")),
    },
    {
        "code": "G32",
        "name": "Grid Shorts 32",
        "slug": "grid-shorts-32",
        "description": "Essential pants for the urban environment.",
        "category_name": "Pants",
        "category_slug": "pants",
        "base_price": 120000,
        "colors": (("Slate", "SLAT"), ("Black", "BLAC")),
    },
    {
        "code": "U33",
        "name": "Urban Windbreaker 33",
        "slug": "urban-windbreaker-33",
        "description": "Essential outerwear for the urban environment.",
        "category_name": "Outerwear",
        "category_slug": "outerwear",
        "base_price": 80000,
        "colors": (("Bone", "BONE"), ("Navy", "NAVY")),
    },
    {
        "code": "D34",
        "name": "District Tee 34",
        "slug": "district-tee-34",
        "description": "Essential t-shirts for the urban environment.",
        "category_name": "T-Shirts",
        "category_slug": "t-shirts",
        "base_price": 350000,
        "colors": (("Sand", "SAND"), ("Crimson", "CRIM")),
    },
    {
        "code": "C35",
        "name": "Core Shorts 35",
        "slug": "core-shorts-35",
        "description": "Essential pants for the urban environment.",
        "category_name": "Pants",
        "category_slug": "pants",
        "base_price": 420000,
        "colors": (("Navy", "NAVY"), ("Sand", "SAND")),
    },
    {
        "code": "N36",
        "name": "Neon Socks 36",
        "slug": "neon-socks-36",
        "description": "Essential accessories for the urban environment.",
        "category_name": "Accessories",
        "category_slug": "accessories",
        "base_price": 230000,
        "colors": (("White", "WHIT"), ("Sand", "SAND")),
    },
    {
        "code": "G37",
        "name": "Grid Bag 37",
        "slug": "grid-bag-37",
        "description": "Essential accessories for the urban environment.",
        "category_name": "Accessories",
        "category_slug": "accessories",
        "base_price": 240000,
        "colors": (("Rust", "RUST"), ("Crimson", "CRIM")),
    },
    {
        "code": "D38",
        "name": "District Cap 38",
        "slug": "district-cap-38",
        "description": "Essential headwear for the urban environment.",
        "category_name": "Headwear",
        "category_slug": "headwear",
        "base_price": 70000,
        "colors": (("Rust", "RUST"), ("Neon", "NEON")),
    },
    {
        "code": "C39",
        "name": "Core Vest 39",
        "slug": "core-vest-39",
        "description": "Essential overshirts for the urban environment.",
        "category_name": "Overshirts",
        "category_slug": "overshirts",
        "base_price": 130000,
        "colors": (("Sand", "SAND"), ("Black", "BLAC")),
    },
    {
        "code": "D40",
        "name": "Drift Tee 40",
        "slug": "drift-tee-40",
        "description": "Essential t-shirts for the urban environment.",
        "category_name": "T-Shirts",
        "category_slug": "t-shirts",
        "base_price": 250000,
        "colors": (("Navy", "NAVY"), ("Cobalt", "COBA")),
    },
    {
        "code": "D41",
        "name": "Drift Vest 41",
        "slug": "drift-vest-41",
        "description": "Essential overshirts for the urban environment.",
        "category_name": "Overshirts",
        "category_slug": "overshirts",
        "base_price": 90000,
        "colors": (("Gray", "GRAY"), ("Bone", "BONE")),
    },
    {
        "code": "M42",
        "name": "Metro Sneakers 42",
        "slug": "metro-sneakers-42",
        "description": "Essential footwear for the urban environment.",
        "category_name": "Footwear",
        "category_slug": "footwear",
        "base_price": 170000,
        "colors": (("Sand", "SAND"), ("Olive", "OLIV")),
    },
    {
        "code": "V43",
        "name": "Vertex Jacket 43",
        "slug": "vertex-jacket-43",
        "description": "Essential outerwear for the urban environment.",
        "category_name": "Outerwear",
        "category_slug": "outerwear",
        "base_price": 380000,
        "colors": (("Gray", "GRAY"), ("White", "WHIT")),
    },
    {
        "code": "P44",
        "name": "Pulse Socks 44",
        "slug": "pulse-socks-44",
        "description": "Essential accessories for the urban environment.",
        "category_name": "Accessories",
        "category_slug": "accessories",
        "base_price": 450000,
        "colors": (("Gray", "GRAY"), ("Rust", "RUST")),
    },
    {
        "code": "C45",
        "name": "Core Tee 45",
        "slug": "core-tee-45",
        "description": "Essential t-shirts for the urban environment.",
        "category_name": "T-Shirts",
        "category_slug": "t-shirts",
        "base_price": 60000,
        "colors": (("Navy", "NAVY"), ("Gray", "GRAY")),
    },
)

# Compact, explicit fit tokens keep every deterministic SKU readable and well
# below ProductVariant.sku's 64-character database limit.
FIT_SKU_CODES = {
    Fit.SLIM: "SLM",
    Fit.REGULAR: "REG",
    Fit.OVERSIZED: "OVR",
}

# D-02: zone-based flat rates in integer centavos. Create-only so admin edits
# to live rates survive a reseed.
ZONE_SEEDS = (
    ("NCR", 9900),
    ("Luzon", 15900),
    ("VisMin", 19900),
)

# FR-20 CMS-lite starter pages. Content is intentionally minimal placeholder
# copy the brand replaces in the admin; URLs match the footer links.
FLATPAGE_SEEDS = (
    ("/about/", "About MetroDrip", "MetroDrip is a Metro Manila streetwear brand."),
    (
        "/faq/",
        "Frequently Asked Questions",
        "Q: How long does delivery take?\nA: 1-3 days within NCR, 3-7 days elsewhere.",
    ),
    (
        "/privacy/",
        "Privacy Policy",
        "We collect only the personal data needed to fulfill your order, "
        "per the Data Privacy Act of 2012 (RA 10173).",
    ),
)


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
            "shipping_zones": 0,
            "flatpages": 0,
            "banners": 0,
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

            # --- Storefront operating data: zones, CMS pages, homepage banner ---

            for zone_name, zone_fee in ZONE_SEEDS:
                _zone, zone_created = ShippingZone.objects.get_or_create(
                    name=zone_name, defaults={"fee": zone_fee, "is_active": True}
                )
                created_counts["shipping_zones"] += int(zone_created)

            site = Site.objects.get(pk=settings.SITE_ID)
            for url, title, content in FLATPAGE_SEEDS:
                page, page_created = FlatPage.objects.get_or_create(
                    url=url, defaults={"title": title, "content": content}
                )
                # Attaching to the site is idempotent and required for rendering.
                page.sites.add(site)
                created_counts["flatpages"] += int(page_created)

            _banner, banner_created = HomepageBanner.objects.get_or_create(
                title="New Season Drop",
                defaults={
                    "image_url": "https://placehold.co/1200x480/141414/C8F031?text=METRODRIP",
                    "link_url": "/shop/",
                    "is_active": True,
                    "order": 0,
                },
            )
            created_counts["banners"] += int(banner_created)

        # A compact result is friendly to both humans and CI log parsers.
        summary = ", ".join(f"{label}={count}" for label, count in created_counts.items())
        self.stdout.write(self.style.SUCCESS(f"Demo seed complete: {summary}"))
