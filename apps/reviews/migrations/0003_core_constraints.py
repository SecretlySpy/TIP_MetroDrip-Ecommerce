from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('reviews', '0002_service_references')]
    operations = [
        migrations.AddConstraint(model_name='review', constraint=models.CheckConstraint(condition=models.Q(status__in=['pending', 'approved', 'rejected']), name='chk_review_status')),
    ]
