from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('payments', '0001_initial')]
    operations = [
        migrations.AddConstraint(model_name='payment', constraint=models.CheckConstraint(condition=models.Q(method__in=['card', 'gcash', 'maya']), name='chk_payment_method')),
        migrations.AddConstraint(model_name='payment', constraint=models.CheckConstraint(condition=models.Q(status__in=['pending', 'paid', 'failed', 'refunded']), name='chk_payment_status')),
    ]
