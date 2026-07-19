"""Django admin configuration for the catalog domain (C-1).

Registers Category, Product, and ProductVariant with a variant-matrix generator
action that creates all Size × Color × Fit combinations for a product.
"""

from django.contrib import admin
from django.db import IntegrityError, transaction

from apps.orders.money import format_centavos

from .models import Category, Fit, Product, ProductVariant, Size


class ProductVariantInline(admin.TabularInline):
    """Inline editor for a product's SKU variants."""

    model = ProductVariant
    extra = 0
    fields = ("sku", "size", "color", "fit", "price_override", "effective_price_display")
    readonly_fields = ("effective_price_display",)

    @admin.display(description="Effective Price")
    def effective_price_display(self, obj):
        """Show the resolved price (override or base) formatted as pesos."""
        if obj.pk is None:
            return "—"
        return format_centavos(obj.price)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "product_count")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="Products")
    def product_count(self, obj):
        return obj.products.count()


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "base_price_display", "variant_count", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductVariantInline]
    actions = ["generate_variant_matrix"]

    @admin.display(description="Base Price")
    def base_price_display(self, obj):
        return format_centavos(obj.base_price)

    @admin.display(description="Variants")
    def variant_count(self, obj):
        return obj.variants.count()

    @admin.action(description="Generate full variant matrix (Size × Color × Fit)")
    def generate_variant_matrix(self, request, queryset):
        """Create all missing Size × Color × Fit variants for selected products.

        For each product, discovers its existing color values (or uses a default
        placeholder), then generates every combination of Size × Color × Fit.
        Existing variants are skipped via get_or_create on the unique axes.
        SKU format: MD-{SLUG_PREFIX}-{SIZE}-{COLOR_CODE}-{FIT_CODE}.
        """
        # Fit codes matching the seed convention (DECISIONS.md ADR-A-012).
        fit_codes = {"slim": "SLM", "regular": "REG", "oversized": "OVR"}

        total_created = 0
        for product in queryset:
            # Discover existing colors from this product's variants; if none
            # exist yet, use a single placeholder so the matrix isn't empty.
            existing_colors = list(
                product.variants.values_list("color", flat=True).distinct()
            )
            if not existing_colors:
                existing_colors = ["Default"]

            for size in Size.values:
                for color in existing_colors:
                    for fit in Fit.values:
                        # Build a deterministic color code: first 4 chars uppercased.
                        color_code = color[:4].upper().replace(" ", "")
                        fit_code = fit_codes.get(fit, fit[:3].upper())
                        sku = f"MD-{product.slug[:8].upper()}-{size}-{color_code}-{fit_code}"

                        try:
                            with transaction.atomic():
                                _, created = ProductVariant.objects.get_or_create(
                                    product=product,
                                    size=size,
                                    color=color,
                                    fit=fit,
                                    defaults={"sku": sku},
                                )
                                if created:
                                    total_created += 1
                        except IntegrityError:
                            # SKU collision with another product — skip gracefully.
                            pass

        self.message_user(
            request,
            f"Generated {total_created} new variant(s) across {queryset.count()} product(s).",
        )
