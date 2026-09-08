"""The stock audit trail cannot be rewritten through SQL or a second ORM."""
from django.db import migrations


def install(apps, editor):
    if editor.connection.vendor != "mysql":
        return
    for operation in ("UPDATE", "DELETE"):
        editor.execute(
            f"CREATE TRIGGER stock_movement_no_{operation.lower()} "
            f"BEFORE {operation} ON inventory_stockmovement FOR EACH ROW "
            "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='StockMovement is append-only'"
        )


def remove(apps, editor):
    if editor.connection.vendor == "mysql":
        for operation in ("update", "delete"):
            editor.execute(f"DROP TRIGGER IF EXISTS stock_movement_no_{operation}")


class Migration(migrations.Migration):
    dependencies = [("inventory", "0005_core_constraints")]
    operations = [migrations.RunPython(install, remove)]
