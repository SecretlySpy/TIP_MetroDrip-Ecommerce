from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('catalog', '0003_category_hierarchy')]
    operations = [
        migrations.AddConstraint(model_name='productvariant', constraint=models.CheckConstraint(condition=models.Q(size__in=['XS', 'S', 'M', 'L', 'XL', 'XXL']), name='chk_variant_size')),
        migrations.AddConstraint(model_name='productvariant', constraint=models.CheckConstraint(condition=models.Q(fit__in=['slim', 'regular', 'oversized']), name='chk_variant_fit')),
    ]
