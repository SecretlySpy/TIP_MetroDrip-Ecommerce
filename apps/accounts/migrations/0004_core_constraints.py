from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('accounts', '0003_service_references')]
    operations = [
        migrations.AddConstraint(model_name='customer', constraint=models.CheckConstraint(condition=models.Q(role__in=['customer', 'merchant', 'administrator']), name='chk_customer_role')),
    ]
