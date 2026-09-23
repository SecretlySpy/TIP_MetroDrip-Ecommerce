"""Cross-service identifiers retain indexes but have no database FK."""
from django.conf import settings
from apps.core.lifecycle import service_cascade, service_set_null, service_protect
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("core", "0001_service_event"), ('shipping', '0002_shippingzone')]
    operations = [
        migrations.AlterField(model_name='shipment', name='order', field=models.OneToOneField('orders.Order', db_constraint=False, db_column='order_ref', on_delete=service_cascade, related_name='shipment')),
    ]
