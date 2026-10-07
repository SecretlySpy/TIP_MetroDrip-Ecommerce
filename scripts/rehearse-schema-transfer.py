"""Exercise legacy backfill and data transfer using disposable CI schemas only."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pymysql

if os.environ.get("GITHUB_ACTIONS") != "true":
    raise SystemExit("This disposable rehearsal runs only in GitHub Actions.")

root = Path(__file__).resolve().parents[1]
env = os.environ.copy()
env["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
legacy = "metrodrip_transfer_ci_legacy"
aliases = ("identity", "catalog", "default", "fulfillment", "content")
targets = {a: f"metrodrip_transfer_ci_{a}" for a in aliases}
connection = pymysql.connect(
    host=env["MYSQL_HOST"],
    port=int(env.get("MYSQL_PORT", "3306")),
    user=env["MYSQL_USER"],
    password=env["MYSQL_PASSWORD"],
    autocommit=True,
)
created = []


def manage(*args, settings_env):
    subprocess.run([sys.executable, "manage.py", *args], cwd=root, env=settings_env, check=True)


try:
    with connection.cursor() as cursor:
        for schema in [legacy, *targets.values()]:
            cursor.execute(f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4")
            created.append(schema)
    old = dict(env, DATABASE_LAYOUT="legacy", MYSQL_DATABASE=legacy)
    manage("migrate", "--noinput", settings_env=old)
    seed = """
from apps.accounts.models import Customer, WishlistItem
from apps.catalog.models import Category, Product, ProductVariant
from apps.inventory.models import StockRecord
from apps.orders.models import Order, OrderItem
from django.contrib.auth.models import Group
u=Customer.objects.create_user(email="transfer@example.test",name="Transfer",password="test")
u.groups.add(Group.objects.create(name="Transfer role"))
c=Category.objects.create(name="Transfer",slug="transfer")
p=Product.objects.create(name="Historic tee",slug="historic-tee",category=c,base_price=12500)
v=ProductVariant.objects.create(product=p,sku="TRANSFER-M",size="M",color="Black",fit="regular")
StockRecord.objects.create(variant=v,qty_on_hand=8)
o=Order.objects.create(order_no="MD-2026-00001",customer=u,subtotal=12500,total=12500)
OrderItem.objects.create(order=o,variant=v,qty=1,unit_price_snapshot=12500)
WishlistItem.objects.create(customer=u,product=p)
"""
    manage("shell", "-c", seed, settings_env=old)
    # Rewind only the snapshot additions, then prove real legacy rows backfill.
    manage("migrate", "orders", "0004", "--noinput", settings_env=old)
    manage("migrate", "--noinput", settings_env=old)
    with tempfile.TemporaryDirectory() as directory:
        manage("transfer_service_data", "export", directory, settings_env=old)
        new = dict(env, DATABASE_LAYOUT="five")
        for alias, schema in targets.items():
            new[f"MYSQL_SCHEMA_{alias.upper()}"] = schema
        manage("migrate_service_schemas", settings_env=new)
        manage("transfer_service_data", "import", directory, settings_env=new)
        verify = """
from apps.accounts.models import Customer, WishlistItem
from apps.orders.models import OrderItem
u=Customer.objects.get(email="transfer@example.test")
assert u.groups.get().name == "Transfer role"
line=OrderItem.objects.get()
assert line.order.customer_id == u.pk
assert line.sku_snapshot == "TRANSFER-M"
assert line.unit_price_snapshot == 12500
assert line.snapshot_source == "legacy_catalog"
assert WishlistItem.objects.get().product_id == line.product_ref
assert line.variant.stock.qty_on_hand == 8
print("Legacy snapshot, primary keys, membership and cross-service references verified")
"""
        manage("shell", "-c", verify, settings_env=new)
finally:
    with connection.cursor() as cursor:
        for schema in reversed(created):
            cursor.execute(f"DROP DATABASE `{schema}`")
    connection.close()
