from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('notifications', '0002_service_references')]
    operations = [
        migrations.AddConstraint(model_name='devicetoken', constraint=models.CheckConstraint(condition=models.Q(platform__in=['ios', 'android']), name='chk_device_platform')),
        migrations.AddConstraint(model_name='notification', constraint=models.CheckConstraint(condition=models.Q(category__in=['order', 'drop', 'stock', 'review']), name='chk_notification_category')),
    ]
