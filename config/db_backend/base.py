"""MySQL backend that respects ownership in historical migrations.

Initial migrations predate the split. On a fresh five-schema installation they
must not create a temporary FK into a table belonging to another schema.
Existing installations run the explicit reference migrations before export.
"""

from contextlib import contextmanager

from django.db.backends.mysql.base import DatabaseWrapper as MySQLDatabaseWrapper
from django.db.backends.mysql.schema import DatabaseSchemaEditor as MySQLSchemaEditor

from config.database_layout import owner


class DatabaseSchemaEditor(MySQLSchemaEditor):
    @contextmanager
    def _local_constraints(self, model, fields):
        changed = []
        for field in fields:
            target = getattr(getattr(field, "remote_field", None), "model", None)
            if (
                hasattr(target, "_meta")
                and owner(model._meta.app_label) != owner(target._meta.app_label)
                and getattr(field, "db_constraint", False)
            ):
                changed.append(field)
                field.db_constraint = False
        try:
            yield
        finally:
            for field in changed:
                field.db_constraint = True

    def create_model(self, model):
        with self._local_constraints(model, model._meta.local_fields):
            return super().create_model(model)

    def add_field(self, model, field):
        with self._local_constraints(model, [field]):
            return super().add_field(model, field)

    def alter_field(self, model, old_field, new_field, strict=False):
        with self._local_constraints(model, [old_field, new_field]):
            return super().alter_field(model, old_field, new_field, strict=strict)


class DatabaseWrapper(MySQLDatabaseWrapper):
    SchemaEditorClass = DatabaseSchemaEditor
