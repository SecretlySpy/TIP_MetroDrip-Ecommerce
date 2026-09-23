"""Cross-service identifiers retain indexes but have no database FK."""
from django.conf import settings
from apps.core.lifecycle import service_cascade, service_set_null, service_protect
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("core", "0001_service_event"), ('accounts', '0002_customer_role')]
    operations = [
        migrations.AlterField(model_name='wishlistitem', name='product', field=models.ForeignKey('catalog.Product', db_constraint=False, db_column='product_ref', on_delete=service_cascade, related_name='wishlisted_by')),
    ]
