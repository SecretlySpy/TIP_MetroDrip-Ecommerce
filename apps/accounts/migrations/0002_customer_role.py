"""Add Customer.role and classify the accounts that already exist.

Before this migration `is_staff` alone opened `/admin/`, which held every model.
Splitting that console in two means each existing staff account has to land on
one side of the new boundary. They are all promoted to ADMINISTRATOR: that is
the console `/admin/` became, so nobody who could sign in yesterday is locked
out today. Merchants are created deliberately afterwards, never inferred.
"""

from django.db import migrations, models


def classify_existing_accounts(apps, schema_editor):
    """Existing staff keep the console they already had; shoppers stay shoppers."""
    Customer = apps.get_model("accounts", "Customer")
    Customer.objects.filter(is_staff=True).update(role="administrator")
    # Non-staff rows already carry the field default ("customer"), so there is
    # nothing to write for them — an UPDATE would only churn the table.


def unclassify(apps, schema_editor):
    """No-op: RemoveField drops the column, so there is nothing to undo."""


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="role",
            field=models.CharField(
                choices=[
                    ("customer", "Customer (storefront only)"),
                    ("merchant", "Merchant / Seller"),
                    ("administrator", "Administrator"),
                ],
                db_index=True,
                default="customer",
                help_text="Which back-office console this account may enter. "
                "Requires staff status to take effect.",
                max_length=16,
            ),
        ),
        migrations.RunPython(classify_existing_accounts, unclassify),
    ]
