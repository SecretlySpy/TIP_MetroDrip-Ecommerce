from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('inventory', '0004_service_references')]
    operations = [
        migrations.AddConstraint(model_name='reservation', constraint=models.CheckConstraint(condition=models.Q(status__in=['active', 'committed', 'released', 'expired']), name='chk_reservation_status')),
    ]
