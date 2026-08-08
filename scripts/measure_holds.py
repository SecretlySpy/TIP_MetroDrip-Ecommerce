import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
# Force service provider
os.environ['INVENTORY_PROVIDER'] = 'service'

import django
django.setup()

from apps.orders.models import Order, StockHold, StockHoldState
from apps.payments.holds import consume_order_holds
from apps.inventory.providers import get_inventory_provider
from django.db import transaction

def run():
    print(f'Inventory provider: {get_inventory_provider().__class__.__name__}')
    
    with transaction.atomic():
        order = Order.objects.create(order_no='TEST-MEASURE-2', total=1000)
        checkout_id = 'checkout-test-measure-2'
        for i in range(10):
            StockHold.objects.create(
                order=order,
                checkout_id=checkout_id,
                variant_id=i+1,
                qty=1,
                state=StockHoldState.ACTIVE
            )
            
        start = time.perf_counter()
        # Note: since service provider hits HTTP, it might fail if the service is not running.
        # But we'll try it. If it fails, we know it's a network call.
        try:
            consume_order_holds(order)
            end = time.perf_counter()
            print(f'Latency for 10 holds: {(end - start) * 1000:.2f} ms')
        except Exception as e:
            print(f'Exception: {e}')
            
        transaction.set_rollback(True)

run()
