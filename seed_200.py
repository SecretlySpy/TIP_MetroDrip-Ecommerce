import os
import django
import random
import string

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.catalog.models import Category, Product, ProductVariant, Size, Fit
from apps.inventory.models import StockRecord

def generate_random_slug(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def run():
    roots = Category.objects.filter(parent__isnull=True)
    subcat_names = ["Men", "Women", "Unisex"]
    
    for parent in roots:
        # 1. Ensure subcategories exist
        subcats = []
        for name in subcat_names:
            slug = f"{parent.slug}-{name.lower()}"
            subcat, _ = Category.objects.get_or_create(
                name=name,
                parent=parent,
                defaults={"slug": slug}
            )
            subcats.append(subcat)
        
        # 2. Count existing products (in parent and its children)
        all_cats_for_parent = [parent] + list(parent.children.all())
        current_count = Product.objects.filter(category__in=all_cats_for_parent).count()
        
        needed = 200 - current_count
        if needed <= 0:
            print(f"Parent '{parent.name}' already has {current_count} products.")
            continue
            
        print(f"Generating {needed} products for '{parent.name}'...")
        
        products_to_create = []
        for i in range(needed):
            # assign to subcategories round-robin
            subcat = subcats[i % len(subcats)]
            
            # create product
            base_slug = f"placeholder-{parent.slug}-{generate_random_slug(12)}"
            p = Product(
                name=f"Generated {parent.name} Product {generate_random_slug(4)}",
                slug=base_slug,
                category=subcat,
                description=f"Placeholder product in {subcat.name} {parent.name}.",
                base_price=random.randint(50000, 300000), # 500 to 3000 PHP
                is_active=True
            )
            products_to_create.append(p)
            
        # Create all products
        Product.objects.bulk_create(products_to_create)
        
        # Fetch them back to get IDs for variants
        created_products = Product.objects.filter(slug__startswith=f"placeholder-{parent.slug}-")
        variants = []
        for p in created_products:
            variants.append(ProductVariant(
                product=p,
                sku=f"SKU-{p.slug[-12:].upper()}",
                size=Size.M,
                color="Black",
                fit=Fit.REGULAR
            ))
        ProductVariant.objects.bulk_create(variants)
        
        # Fetch variants to get IDs for stock records
        created_variants = ProductVariant.objects.filter(product__in=created_products)
        stock_records = []
        for v in created_variants:
            stock_records.append(StockRecord(
                variant=v,
                qty_on_hand=10,
                low_stock_threshold=5
            ))
        StockRecord.objects.bulk_create(stock_records)
        
        final_count = Product.objects.filter(category__in=all_cats_for_parent).count()
        print(f"Done for '{parent.name}'. Total products: {final_count}")

if __name__ == "__main__":
    run()
