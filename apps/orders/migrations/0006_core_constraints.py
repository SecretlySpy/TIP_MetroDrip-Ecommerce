from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('orders', '0005_order_item_snapshots')]
    operations = [
        migrations.AddConstraint(model_name='order', constraint=models.CheckConstraint(condition=models.Q(status__in=['pending', 'paid', 'packed', 'shipped', 'delivered', 'cancelled', 'refunded']), name='chk_order_status')),
        migrations.AddConstraint(model_name='orderitem', constraint=models.CheckConstraint(condition=models.Q(snapshot_source__in=['checkout', 'legacy_catalog']), name='chk_snapshot_source')),
        migrations.AddConstraint(model_name='stockhold', constraint=models.CheckConstraint(condition=models.Q(state__in=['active', 'committed', 'released', 'unknown']), name='chk_hold_state')),
        migrations.AddConstraint(model_name='outboxmessage', constraint=models.CheckConstraint(condition=models.Q(state__in=['pending', 'sent', 'dead']), name='chk_outbox_state')),
    ]
