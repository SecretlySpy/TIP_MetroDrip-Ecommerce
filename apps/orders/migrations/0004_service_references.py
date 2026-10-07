"""Cross-service identifiers retain indexes but have no database FK."""
from django.conf import settings
from apps.core.lifecycle import service_cascade, service_set_null, service_protect
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("core", "0001_service_event"), ('orders', '0003_outboxmessage')]
    operations = [
        migrations.AlterField(model_name='order', name='customer', field=models.ForeignKey(settings.AUTH_USER_MODEL, db_constraint=False, db_column='customer_ref', null=True, blank=True, on_delete=service_set_null, related_name='orders')),
        migrations.AlterField(model_name='orderitem', name='variant', field=models.ForeignKey('catalog.ProductVariant', db_constraint=False, db_column='variant_ref', on_delete=service_protect, related_name='order_items')),
    ]
