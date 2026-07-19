import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.catalog.models import Category, Product, ProductVariant, Size, Fit
from apps.inventory.models import StockRecord
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site

site = Site.objects.get(id=1)

# Flatpages
fp_about, _ = FlatPage.objects.get_or_create(url="/about/", defaults={
    "title": "About Us",
    "content": "<p>MetroDrip is a Metro Manila streetwear brand designed for the city. We don't follow trends, we set them.</p>"
})
fp_about.sites.add(site)

fp_contact, _ = FlatPage.objects.get_or_create(url="/contact/", defaults={
    "title": "Contact Us",
    "content": "<p>Have questions or concerns? Drop us an email at <strong>support@metrodrip.com</strong> or reach out via our socials.</p>"
})
fp_contact.sites.add(site)

fp_privacy, _ = FlatPage.objects.get_or_create(url="/privacy/", defaults={
    "title": "Privacy Policy",
    "content": "<p>We take your privacy seriously. All data collected is solely used for fulfillment and improving your experience in compliance with the Data Privacy Act.</p>"
})
fp_privacy.sites.add(site)

# Categories
cat_tops, _ = Category.objects.get_or_create(name="Tops", slug="tops")
cat_bottoms, _ = Category.objects.get_or_create(name="Bottoms", slug="bottoms")

# Products
p1, _ = Product.objects.get_or_create(slug="neon-nights-tee", defaults={
    "name": "Neon Nights Heavyweight Tee",
    "category": cat_tops,
    "description": "Premium 240gsm cotton. Boxy fit. Features a reflective MetroDrip logo on the chest.",
    "base_price": 95000, # 950 PHP
    "is_active": True
})
p2, _ = Product.objects.get_or_create(slug="concrete-cargo-pants", defaults={
    "name": "Concrete Utility Cargos",
    "category": cat_bottoms,
    "description": "Ripstop fabric with 6 deep pockets. Adjustable cuffs. Built for the daily commute.",
    "base_price": 185000,
    "is_active": True
})
p3, _ = Product.objects.get_or_create(slug="monsoon-windbreaker", defaults={
    "name": "Monsoon Windbreaker",
    "category": cat_tops,
    "description": "Water-resistant, lightweight, packable. Perfect for unpredictable Manila weather.",
    "base_price": 220000,
    "is_active": True
})

# Variants & Stock
def add_variants(product, sizes, colors, fit):
    for size in sizes:
        for color in colors:
            sku = f"{product.slug[:4]}-{size}-{color[:3]}-{fit[:3]}".upper()
            var, created = ProductVariant.objects.get_or_create(
                product=product, sku=sku,
                defaults={"size": size, "color": color, "fit": fit}
            )
            if created:
                StockRecord.objects.create(variant=var, qty_on_hand=50, low_stock_threshold=5)

add_variants(p1, [Size.S, Size.M, Size.L, Size.XL], ["Black", "Volt", "White"], Fit.OVERSIZED)
add_variants(p2, [Size.S, Size.M, Size.L, Size.XL], ["Olive", "Black"], Fit.REGULAR)
add_variants(p3, [Size.M, Size.L], ["Black", "Grey"], Fit.REGULAR)

print("Seed data generated successfully!")
