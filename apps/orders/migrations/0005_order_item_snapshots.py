"""Capture current known catalog data for legacy lines, with explicit provenance.

Historical catalog values cannot be reconstructed; legacy_catalog makes that
limitation visible rather than asserting that this was the purchase-time data.
"""
from django.db import migrations, models

FIELDS = {
    "product_ref": models.BigIntegerField(null=True, db_index=True),
    "sku_snapshot": models.CharField(max_length=64, default=""),
    "product_name_snapshot": models.CharField(max_length=200, default=""),
    "product_slug_snapshot": models.CharField(max_length=220, blank=True, default=""),
    "size_snapshot": models.CharField(max_length=4, default=""),
    "color_snapshot": models.CharField(max_length=40, default=""),
    "fit_snapshot": models.CharField(max_length=10, default=""),
    "image_url_snapshot": models.URLField(max_length=2048, blank=True, default=""),
    "snapshot_source": models.CharField(max_length=16, default="checkout"),
}


def backfill(apps, schema_editor):
    Line = apps.get_model("orders", "OrderItem")
    Variant = apps.get_model("catalog", "ProductVariant")
    db = schema_editor.connection.alias
    from django.conf import settings
    catalog_db = "catalog" if "catalog" in settings.DATABASES else db
    for line in Line.objects.using(db).filter(product_ref__isnull=True).iterator(chunk_size=500):
        variant = Variant.objects.using(catalog_db).select_related("product").get(pk=line.variant_id)
        product = variant.product
        Line.objects.using(db).filter(pk=line.pk).update(
            product_ref=product.pk, sku_snapshot=variant.sku,
            product_name_snapshot=product.name, product_slug_snapshot=product.slug,
            size_snapshot=variant.size, color_snapshot=variant.color, fit_snapshot=variant.fit,
            image_url_snapshot=(product.images or [""])[0], snapshot_source="legacy_catalog",
        )


class Migration(migrations.Migration):
    dependencies = [("orders", "0004_service_references")]
    operations = [
        migrations.AddField(model_name="orderitem", name=name, field=field,
                            preserve_default=(name == "snapshot_source"))
        for name, field in FIELDS.items()
    ] + [
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AlterField(model_name="orderitem", name="product_ref",
                              field=models.BigIntegerField(db_index=True)),
    ]
