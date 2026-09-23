"""Cross-service identifiers retain indexes but have no database FK."""
from django.conf import settings
from apps.core.lifecycle import service_cascade, service_set_null, service_protect
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("core", "0001_service_event"), ('notifications', '0001_initial')]
    operations = [
        migrations.AlterField(model_name='devicetoken', name='customer', field=models.ForeignKey(settings.AUTH_USER_MODEL, db_constraint=False, db_column='customer_ref', on_delete=service_cascade, related_name='device_tokens')),
        migrations.AlterField(model_name='notification', name='customer', field=models.ForeignKey(settings.AUTH_USER_MODEL, db_constraint=False, db_column='customer_ref', on_delete=service_cascade, related_name='notifications')),
        migrations.AlterField(model_name='notification', name='order', field=models.ForeignKey('orders.Order', db_constraint=False, db_column='order_ref', null=True, blank=True, on_delete=service_set_null, related_name='+')),
    ]
