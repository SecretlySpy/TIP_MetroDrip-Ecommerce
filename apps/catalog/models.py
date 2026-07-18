"""Catalog domain (§4, FR-1): Product → ProductVariant, 3-axis variants.

Every Size × Color × Fit combination is exactly one SKU with its own stock
(FR-1); stock itself lives in apps.inventory, keeping catalog free of any
quantity math.
"""

from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Size(models.TextChoices):
    XS = "XS", "Extra Small"
    S = "S", "Small"
    M = "M", "Medium"
    L = "L", "Large"
    XL = "XL", "Extra Large"
    XXL = "XXL", "2X Large"


class Fit(models.TextChoices):
    SLIM = "slim", "Slim"
    REGULAR = "regular", "Regular"
    OVERSIZED = "oversized", "Oversized"


class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField(blank=True)
    # FK per §4's key-field table (category_id); the diagram's *──* was resolved
    # to the simpler single-category design — see DECISIONS.md.
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    # Hard Invariant 2: money is integer centavos, formatted only at display time.
    base_price = models.PositiveIntegerField(help_text="Price in centavos (integer).")
    # Ordered list of CDN image URLs; object storage per §2, so no ImageField/disk.
    images = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=64, unique=True)
    size = models.CharField(max_length=4, choices=Size.choices)
    color = models.CharField(max_length=40)
    fit = models.CharField(max_length=10, choices=Fit.choices)
    # NULL = variant sells at product.base_price; set only for surcharge sizes etc.
    price_override = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            # One SKU per axis combination (§1: Size × Color × Fit = one SKU).
            models.UniqueConstraint(
                fields=["product", "size", "color", "fit"], name="uniq_variant_axes"
            ),
        ]

    def __str__(self):
        return self.sku

    @property
    def price(self):
        """Effective unit price in centavos — the only place override logic lives."""
        return self.price_override if self.price_override is not None else self.product.base_price
