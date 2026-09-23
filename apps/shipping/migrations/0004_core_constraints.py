from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('shipping', '0003_service_references')]
    operations = [
        migrations.AddConstraint(model_name='shipment', constraint=models.CheckConstraint(condition=models.Q(status__in=['pending', 'booked', 'in_transit', 'out_for_delivery', 'delivered', 'failed']), name='chk_shipment_status')),
    ]
