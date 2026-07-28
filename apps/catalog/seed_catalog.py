"""Deterministic definitions shared by the catalog seeding commands (Epic B).

Everything here is a pure function of its inputs — no randomness, no clock — so
local, CI, and staging databases converge on byte-identical placeholder data.
That is what makes `seed_mock_catalog` safe to rerun.
"""

from apps.catalog.models import Fit, Size

#: Audience subcategories created beneath every main category.
#: `slug_suffix` is appended to the parent slug, keeping child slugs globally
#: unique (`hoodies-men`) while allowing the display name to repeat.
AUDIENCES = (
    {"name": "Men", "slug_suffix": "men", "code": "M"},
    {"name": "Women", "slug_suffix": "women", "code": "W"},
)

#: Cycled through so placeholders vary without needing a random source.
MOCK_COLORS = ("Carbon Black", "Bone White", "Slate Grey", "Volt Green", "Rust Clay")
MOCK_SIZES = (Size.S, Size.M, Size.L, Size.XL)
MOCK_FITS = (Fit.REGULAR, Fit.SLIM, Fit.OVERSIZED)

#: Price ladder in centavos (Hard Invariant 2: money is integer centavos).
MOCK_PRICE_FLOOR = 49900
MOCK_PRICE_STEP = 5000
MOCK_PRICE_STEPS = 20

#: Opening stock for every generated variant, plus its matching ledger entry.
MOCK_STOCK_QTY = 25


def category_code(slug):
    """Compress a category slug into an uppercase SKU fragment.

    ``"t-shirts" -> "TSHIRTS"``. Truncated so a SKU stays comfortably inside
    ProductVariant.sku's 64 characters even for long category names.
    """
    return slug.replace("-", "").upper()[:10]


def mock_product_slug(parent_slug, audience_suffix, sequence):
    """Natural key for a placeholder product — the basis of idempotency."""
    return f"mock-{parent_slug}-{audience_suffix}-{sequence:03d}"


def mock_product_name(parent_name, audience_name, sequence):
    return f"{parent_name} {audience_name} Placeholder {sequence:02d}"


def mock_sku(parent_slug, audience_code, sequence):
    return f"MD-MOCK-{category_code(parent_slug)}-{audience_code}-{sequence:03d}"


def mock_price(index):
    """Walk a fixed price ladder so placeholders exercise price sorting."""
    return MOCK_PRICE_FLOOR + (index % MOCK_PRICE_STEPS) * MOCK_PRICE_STEP


def mock_variant_axes(index):
    """Pick one Size/Color/Fit triple per placeholder.

    Co-prime-ish cycling over three different-length sequences keeps the axes
    from moving in lockstep, so filters have varied data to match against.
    """
    return {
        "size": MOCK_SIZES[index % len(MOCK_SIZES)],
        "color": MOCK_COLORS[index % len(MOCK_COLORS)],
        "fit": MOCK_FITS[index % len(MOCK_FITS)],
    }


def allocate_round_robin(count, buckets):
    """Spread `count` items across `buckets` as evenly as possible.

    Returns a list of per-bucket counts. With 100 items over 18 buckets the
    first 10 buckets take 6 and the remainder take 5.
    """
    if buckets <= 0:
        return []
    base, extra = divmod(count, buckets)
    return [base + (1 if i < extra else 0) for i in range(buckets)]
