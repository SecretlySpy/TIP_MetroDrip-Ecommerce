"""Ownership of MetroDrip's five logical MySQL schemas.

Aliases are stable application identifiers; names may be prefixed for staging
and tests. Orders owns `default` so payment/order/outbox transactions share one
connection. Cross-owner relations are indexed IDs, never database foreign keys.
"""

APP_DATABASE = {
    "accounts": "identity",
    "auth": "identity",
    "contenttypes": "identity",
    "admin": "identity",
    "sessions": "identity",
    "otp_totp": "identity",
    "otp_static": "identity",
    "token_blacklist": "identity",
    "catalog": "catalog",
    "inventory": "catalog",
    "orders": "default",
    "payments": "default",
    "reviews": "default",
    "shipping": "fulfillment",
    "notifications": "fulfillment",
    "cms": "content",
    "flatpages": "content",
    "sites": "content",
}
SCHEMA_NAMES = {
    "identity": "db_identity",
    "catalog": "db_catalog",
    "default": "db_orders",
    "fulfillment": "db_fulfillment",
    "content": "db_content",
}


def owner(app_label):
    return APP_DATABASE.get(app_label, "content")


class ServiceDatabaseRouter:
    def db_for_read(self, model, **hints):
        return owner(model._meta.app_label)

    db_for_write = db_for_read

    def allow_relation(self, obj1, obj2, **hints):
        # Django's object assignment/prefetch machinery may associate an ID
        # reference across aliases. This does not authorize a SQL JOIN or FK.
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == "core":
            return db in SCHEMA_NAMES
        return db == owner(app_label)


def configure_databases(base):
    """Build aliases from validated connection options, without sharing dicts."""
    import copy
    import os
    import re

    if os.environ.get("DATABASE_LAYOUT", "five") == "legacy":
        return {"default": base}, []
    databases = {}
    for alias, name in SCHEMA_NAMES.items():
        db = copy.deepcopy(base)
        db["ENGINE"] = "config.db_backend"
        db["NAME"] = os.environ.get(f"MYSQL_SCHEMA_{alias.upper()}", name)
        if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", db["NAME"]):
            raise ValueError("Schema names must contain 1–64 letters, digits, or underscores")
        for key in ("USER", "PASSWORD", "HOST", "PORT"):
            db[key] = os.environ.get(f"MYSQL_{alias.upper()}_{key}", db[key])
        db.setdefault("TEST", {})["DEPENDENCIES"] = []
        databases[alias] = db
    return databases, ["config.database_layout.ServiceDatabaseRouter"]
