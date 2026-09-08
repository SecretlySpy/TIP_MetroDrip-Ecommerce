"""Protect purchase-time identity even against direct SQL updates."""
from django.db import migrations

COLUMNS = (
    "order_id", "variant_ref", "qty", "unit_price_snapshot", "product_ref",
    "sku_snapshot", "product_name_snapshot", "product_slug_snapshot",
    "size_snapshot", "color_snapshot", "fit_snapshot", "image_url_snapshot",
    "snapshot_source",
)


def install(apps, editor):
    if editor.connection.vendor != "mysql":
        return
    comparisons = " OR ".join(
        f"NOT (BINARY NEW.`{column}` <=> BINARY OLD.`{column}`)" for column in COLUMNS
    )
    editor.execute(
        "CREATE TRIGGER order_item_snapshot_immutable BEFORE UPDATE ON orders_orderitem "
        f"FOR EACH ROW BEGIN IF {comparisons} THEN "
        "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Purchased order lines are immutable'; "
        "END IF; END"
    )


def remove(apps, editor):
    if editor.connection.vendor == "mysql":
        editor.execute("DROP TRIGGER IF EXISTS order_item_snapshot_immutable")


class Migration(migrations.Migration):
    dependencies = [("orders", "0006_core_constraints")]
    operations = [migrations.RunPython(install, remove)]
