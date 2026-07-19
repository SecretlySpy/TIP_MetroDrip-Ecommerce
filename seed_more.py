import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
from apps.inventory.models import StockRecord

# Additional Categories
cat_outerwear, _ = Category.objects.get_or_create(name="Outerwear", slug="outerwear")
cat_headwear, _ = Category.objects.get_or_create(name="Headwear", slug="headwear")
cat_accessories, _ = Category.objects.get_or_create(name="Accessories", slug="accessories")

# Additional Products
p4, _ = Product.objects.get_or_create(
    slug="asphalt-puffer-jacket",
    defaults={
        "name": "Asphalt Puffer Jacket",
        "category": cat_outerwear,
        "description": "Matte black finish. Water repellent outer shell with synthetic down filling. Maximum warmth with a cropped streetwear silhouette.",
        "base_price": 350000,  # 3500 PHP
        "is_active": True,
    },
)

p5, _ = Product.objects.get_or_create(
    slug="drip-logo-beanie",
    defaults={
        "name": "Drip Logo Beanie",
        "category": cat_headwear,
        "description": "Heavy gauge knit beanie with embroidered MetroDrip classic logo.",
        "base_price": 60000,  # 600 PHP
        "is_active": True,
    },
)

p6, _ = Product.objects.get_or_create(
    slug="tactical-crossbody-bag",
    defaults={
        "name": "Tactical Crossbody Bag",
        "category": cat_accessories,
        "description": "Nylon canvas construction with magnetic buckle closures and 3 hidden stash pockets.",
        "base_price": 120000,  # 1200 PHP
        "is_active": True,
    },
)

p7, _ = Product.objects.get_or_create(
    slug="acid-wash-hoodie",
    defaults={
        "name": "Acid Wash Oversized Hoodie",
        "category": Category.objects.get(slug="tops"),
        "description": "Vintage acid wash finish. 400gsm heavy fleece. Dropped shoulders for an exaggerated fit.",
        "base_price": 280000,  # 2800 PHP
        "is_active": True,
    },
)


# Variants & Stock
def add_variants(product, sizes, colors, fit):
    for size in sizes:
        for color in colors:
            sku = f"{product.slug[:4]}-{size}-{color[:3]}-{fit[:3]}".upper()
            var, created = ProductVariant.objects.get_or_create(
                product=product, sku=sku, defaults={"size": size, "color": color, "fit": fit}
            )
            if created:
                StockRecord.objects.create(variant=var, qty_on_hand=30, low_stock_threshold=5)


# Outerwear
add_variants(p4, [Size.S, Size.M, Size.L, Size.XL], ["Black", "Grey"], Fit.REGULAR)

# Headwear / Accessories typically have "One Size" but we'll use "M" as a generic OS representation if "OS" isn't in choices.
# Let's check choices: XS, S, M, L, XL, XXL. We'll use M as OS for now to avoid errors, or add OS to Size model?
# For now just assign 'M' and color variations.
add_variants(p5, [Size.M], ["Black", "Neon", "Olive"], Fit.REGULAR)
add_variants(p6, [Size.M], ["Black"], Fit.REGULAR)

# New Tops
add_variants(p7, [Size.M, Size.L, Size.XL], ["Charcoal", "Blue"], Fit.OVERSIZED)

print("More seed data generated successfully!")
