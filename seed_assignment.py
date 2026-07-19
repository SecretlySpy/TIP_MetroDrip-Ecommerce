import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.catalog.models import Category, Product, ProductVariant, Size, Fit
from apps.inventory.models import StockRecord
from django.utils.text import slugify
from decimal import Decimal
import random

# Mapping Sub-Categories from the assignment
SUB_CATEGORIES = {
    # Tops
    "T-Shirts": [
        "Metro Core Box Tee", "Drip District Graphic Tee", "EDSA Nights Oversized Tee",
        "Manila Skyline Pocket Tee", "Barangay Heavyweight Tee", "Tribal"
    ][:5],  # Assignment specifies 5 each, but listed 6. We keep 5.
    "Hoodies & Sweatshirts": [
        "Skyline Pullover Hoodie", "Drip Zip-Up Hoodie", "Metro Fleece Crewneck",
        "Midnight Commute Oversized Hoodie", "Monsoon Tech Hoodie"
    ],
    "Polos & Button-Ups": [
        "Knit Polo from Kalye", "Weekend Cuban Shirt", "Metro Corduroy Overshirt",
        "Work Shirt from Drip", "Plaid Flannel Button-Up"
    ],
    
    # Bottoms
    "Denim": [
        "Metro Straight Cut Jeans", "Drip Baggy Denims", "Faded District Slim Jeans",
        "Carpenter Denim Pants", "Acid Wash Wide Leg Jeans"
    ],
    "Shorts": [
        "Kalye Cargo Shorts", "Metro Mesh Shorts", "Drip Denim Shorts",
        "Boardwalk Nylon Shorts", "Terry Lounge Shorts"
    ],
    "Trousers & Joggers": [
        # The PDF had a typo here ("Metro Snapback"). Fixing to actual trousers.
        "Metro Track Joggers", "Drip Utility Trousers", "Skyline Cargo Pants",
        "Monsoon Waterproof Joggers", "Corduroy Chino Pants"
    ],
    
    # Accessories & Headwear
    "Caps & Beanies": [
        "Metro Snapback", "Drip Dad Cap", "Skyline Trucker Cap",
        "Monsoon Beanie", "Corduroy Bucket Hat"
    ],
    "Bags": [
        "Commuter Sling Bag", "Metro Canvas Tote", "Drip Crossbody Bag",
        "Utility Belt Bag", "Roll Top Backpack"
    ],
    "Socks & Small Goods": [
        "Drip Crew Socks (3-Pair)", "Metro Quarter Socks", "Canvas Card Wallet",
        "Skyline Bandanna", "Drip Key Chain"
    ]
}

# Helper to generate variants
def add_variants(product, sizes, colors, fits):
    for size in sizes:
        for color in colors:
            for fit in fits:
                # SKU generator: MD-[PROD-CODE]-[SIZE]-[COLOR]-[FIT]
                # E.g. MD-TRBL-M-BLK-REG
                pcode = "".join([w[0] for w in product.name.split() if w.isalnum()])[:4].upper()
                if len(pcode) < 3:
                    pcode = product.slug[:4].upper()
                c_code = color[:3].upper()
                f_code = fit[:3].upper()
                
                sku = f"MD-{pcode}-{size}-{c_code}-{f_code}"
                
                var, created = ProductVariant.objects.get_or_create(
                    product=product, sku=sku,
                    defaults={"size": size, "color": color, "fit": fit}
                )
                if created:
                    StockRecord.objects.create(variant=var, qty_on_hand=50, low_stock_threshold=5)

def run_seed():
    print("Generating Assignment 1.2 Product Catalog...")
    
    for subcat_name, products in SUB_CATEGORIES.items():
        # 1. Create or get the sub-category
        category, _ = Category.objects.get_or_create(
            name=subcat_name, 
            defaults={"slug": slugify(subcat_name)}
        )
        
        # Determine attributes based on category
        if subcat_name in ["T-Shirts", "Hoodies & Sweatshirts", "Polos & Button-Ups"]:
            sizes = [Size.S, Size.M, Size.L, Size.XL]
            colors = ["Black", "White", "Navy", "Grey"]
            fits = [Fit.REGULAR, Fit.OVERSIZED]
            base_price_range = (79900, 149900)  # 799 to 1499 PHP
        elif subcat_name in ["Denim", "Shorts", "Trousers & Joggers"]:
            sizes = [Size.S, Size.M, Size.L, Size.XL]
            colors = ["Black", "Indigo", "Olive", "Khaki"]
            fits = [Fit.SLIM, Fit.REGULAR]
            base_price_range = (129900, 249900)
        else: # Accessories
            sizes = [Size.M] # M as One Size
            colors = ["Black", "Olive"]
            fits = [Fit.REGULAR]
            base_price_range = (29900, 99900)

        # 2. Create products
        for p_name in products:
            p_slug = slugify(p_name)
            
            product, created = Product.objects.get_or_create(
                slug=p_slug,
                defaults={
                    "name": p_name,
                    "category": category,
                    "description": f"Assignment 1.2 Sample Product: {p_name}. Authentic Metro Manila Streetwear.",
                    "base_price": random.choice(range(base_price_range[0], base_price_range[1], 10000)),
                    "is_active": True
                }
            )
            
            if created:
                add_variants(product, sizes, colors, fits)

    print("Successfully seeded 9 sub-categories and 45 products!")

if __name__ == "__main__":
    run_seed()
