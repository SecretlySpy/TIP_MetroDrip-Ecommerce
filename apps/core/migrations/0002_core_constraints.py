from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('core', '0001_service_event')]
    operations = [
        migrations.AddConstraint(model_name='serviceevent', constraint=models.CheckConstraint(condition=models.Q(operation__in=['delete', 'set_null']), name='chk_service_event_operation')),
    ]
