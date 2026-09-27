"""Cross-service identifiers retain indexes but have no database FK."""
from django.conf import settings
from apps.core.lifecycle import service_cascade, service_set_null, service_protect
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("core", "0001_service_event"), ('inventory', '0003_idempotencyrecord_reservation_checkout_id')]
    operations = [
        migrations.AlterField(model_name='reservation', name='order', field=models.ForeignKey('orders.Order', db_constraint=False, db_column='order_ref', null=True, blank=True, on_delete=service_set_null, related_name='reservations')),
        migrations.AlterField(model_name='stockmovement', name='ref_order', field=models.ForeignKey('orders.Order', db_constraint=False, db_column='ref_order_ref', null=True, blank=True, on_delete=service_protect, related_name='movements')),
    ]
