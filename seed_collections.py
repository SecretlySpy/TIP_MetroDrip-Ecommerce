import os
import random
import string

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.catalog.models import Category, Fit, Product, ProductVariant, Size
from apps.inventory.models import StockRecord


def generate_random_slug(length=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def run():
    # The user mentioned New Arrivals, Best-Sellers, On-Sale, and Pre-Order.
    collections = [
        ("New Arrivals", "new-arrivals"),
        ("Best-Sellers", "best-sellers"),
        ("On-Sale", "on-sale"),
        ("Pre-Order", "pre-order"),
    ]

    for name, base_slug in collections:
        parent, created = Category.objects.get_or_create(slug=base_slug, defaults={"name": name})

        # Ensure we don't over-seed if it already has products
        current_count = Product.objects.filter(category=parent).count()
        needed = 200 - current_count

        if needed <= 0:
            print(f"Parent '{name}' already has {current_count} products.")
            continue

        print(f"Generating {needed} products for '{name}'...")

        products_to_create = []
        for _ in range(needed):
            p_slug = f"placeholder-{base_slug}-{generate_random_slug(12)}"

            # For On-Sale, maybe lower price? For others, standard.
            price = random.randint(50000, 300000)
            if name == "On-Sale":
                price = int(price * 0.7)  # 30% off

            p = Product(
                name=f"Generated {name} Product {generate_random_slug(4)}",
                slug=p_slug,
                category=parent,  # Assign directly to the collection category
                description=f"Placeholder relevant product in {name}.",
                base_price=price,
                is_active=True,
            )
            products_to_create.append(p)

        # Create products in bulk
        Product.objects.bulk_create(products_to_create)

        # Fetch them back to create variants
        created_products = Product.objects.filter(slug__startswith=f"placeholder-{base_slug}-")
        variants = []
        for p in created_products:
            variants.append(
                ProductVariant(
                    product=p,
                    sku=f"SKU-{p.slug[-12:].upper()}",
                    size=Size.M,
                    color="Black",
                    fit=Fit.REGULAR,
                )
            )
        ProductVariant.objects.bulk_create(variants)

        # Fetch variants to get IDs for stock records
        created_variants = ProductVariant.objects.filter(product__in=created_products)
        stock_records = []
        for v in created_variants:
            # Pre-orders might have 0 stock but can be reserved, or we just give them some stock for testing.
            stock = 0 if name == "Pre-Order" else random.randint(10, 50)
            stock_records.append(StockRecord(variant=v, qty_on_hand=stock, low_stock_threshold=5))
        StockRecord.objects.bulk_create(stock_records)

        final_count = Product.objects.filter(category=parent).count()
        print(f"Done for '{name}'. Total products: {final_count}")


if __name__ == "__main__":
    run()
