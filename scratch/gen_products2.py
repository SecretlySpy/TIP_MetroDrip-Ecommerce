import random

categories = [
    ("T-Shirts", "t-shirts"),
    ("Hoodies", "hoodies"),
    ("Pants", "pants"),
    ("Overshirts", "overshirts"),
    ("Outerwear", "outerwear"),
    ("Headwear", "headwear"),
    ("Accessories", "accessories"),
    ("Footwear", "footwear"),
]

prefixes = [
    "Urban",
    "Metro",
    "District",
    "Neon",
    "Core",
    "Shift",
    "Grid",
    "Vertex",
    "Pulse",
    "Sector",
    "Void",
    "Drift",
]
nouns = [
    "Tee",
    "Hoodie",
    "Cargo",
    "Jacket",
    "Cap",
    "Beanie",
    "Socks",
    "Sneakers",
    "Bag",
    "Windbreaker",
    "Vest",
    "Shorts",
]
colors = [
    "Black",
    "White",
    "Gray",
    "Navy",
    "Olive",
    "Rust",
    "Sand",
    "Slate",
    "Crimson",
    "Cobalt",
    "Neon",
    "Bone",
]


def gen_code(name):
    # take first letter of first word + first 3 of last word
    words = name.split()
    if len(words) >= 2:
        return (words[0][0] + words[-1][:3]).upper()
    return name[:4].upper()


products = []
for i in range(45):  # Generate 45 products to be safe
    pref = random.choice(prefixes)
    noun = random.choice(nouns)
    name = f"{pref} {noun} {i + 1}"

    if "Tee" in noun:
        cat = categories[0]
    elif "Hoodie" in noun:
        cat = categories[1]
    elif "Cargo" in noun or "Shorts" in noun:
        cat = categories[2]
    elif "Jacket" in noun or "Windbreaker" in noun:
        cat = categories[4]
    elif "Cap" in noun or "Beanie" in noun:
        cat = categories[5]
    elif "Socks" in noun or "Bag" in noun:
        cat = categories[6]
    elif "Sneakers" in noun:
        cat = categories[7]
    else:
        cat = categories[3]

    c1 = random.choice(colors)
    c2 = random.choice([c for c in colors if c != c1])

    c1_code = c1[:4].upper()
    c2_code = c2[:4].upper()

    p = f"""    {{
        "code": "{gen_code(name)}",
        "name": "{name}",
        "slug": "{name.lower().replace(" ", "-")}",
        "description": "Essential {cat[0].lower()} for the urban environment.",
        "category_name": "{cat[0]}",
        "category_slug": "{cat[1]}",
        "base_price": {random.randint(5, 45) * 100}00,
        "colors": (("{c1}", "{c1_code}"), ("{c2}", "{c2_code}")),
    }},"""
    products.append(p)

# Read file, find end of PRODUCT_SEEDS, insert products
filepath = "apps/catalog/management/commands/seed_demo.py"
with open(filepath, encoding="utf-8") as f:
    content = f.read()

target = '        "colors": (("Neon Lime", "NLIM"), ("Carbon Black", "CBLK")),\n    },'
replacement = target + "\n" + "\n".join(products)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content.replace(target, replacement))

print("Successfully injected 45 products")
