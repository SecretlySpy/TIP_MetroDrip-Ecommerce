from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [migrations.CreateModel(
        name="ServiceEvent",
        fields=[
            ("id", models.BigAutoField(primary_key=True, auto_created=True, serialize=False, verbose_name="ID")),
            ("target_model", models.CharField(max_length=100)),
            ("target_field", models.CharField(max_length=100)),
            ("reference_id", models.BigIntegerField()),
            ("operation", models.CharField(max_length=8)),
            ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
            ("completed_at", models.DateTimeField(null=True)),
            ("attempts", models.PositiveIntegerField(default=0)),
            ("last_error", models.TextField(blank=True)),
        ],
        options={"indexes": [models.Index(fields=["completed_at", "id"], name="idx_service_event_pending")]},
    )]
