"""Verify actual MySQL metadata against the model ownership contract."""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from config.database_layout import SCHEMA_NAMES, owner


class Command(BaseCommand):
    help = "Verify schemas, tables, columns, local FKs, checks, and no cross-service FKs."

    def handle(self, **options):
        if set(connections) != set(SCHEMA_NAMES):
            raise CommandError("Expected five database aliases.")
        if len({connections[a].settings_dict["NAME"] for a in connections}) != 5:
            raise CommandError("Each owner must have a distinct physical schema.")
        errors = []
        for alias in SCHEMA_NAMES:
            connection = connections[alias]
            with connection.cursor() as cursor:
                tables = set(connection.introspection.table_names(cursor))
                cursor.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema=DATABASE() AND table_type='BASE TABLE' "
                    "AND (engine <> 'InnoDB' OR table_collation NOT LIKE 'utf8mb4%%')"
                )
                errors.extend(
                    f"{alias}: invalid engine/charset on {r[0]}" for r in cursor.fetchall()
                )
                cursor.execute(
                    "SELECT table_name, column_name FROM information_schema.key_column_usage "
                    "WHERE table_schema=DATABASE() AND referenced_table_schema IS NOT NULL "
                    "AND referenced_table_schema <> table_schema"
                )
                errors.extend(f"{alias}: cross-schema FK {r}" for r in cursor.fetchall())
                for model in apps.get_models(include_auto_created=True):
                    if model._meta.proxy or not model._meta.managed:
                        continue
                    belongs = (
                        model._meta.app_label == "core" or owner(model._meta.app_label) == alias
                    )
                    table = model._meta.db_table
                    if (table in tables) != belongs:
                        errors.append(f"{alias}: wrong ownership or missing table {table}")
                    if not belongs or table not in tables:
                        continue
                    constraints = connection.introspection.get_constraints(cursor, table)
                    columns = {
                        c.name
                        for c in connection.introspection.get_table_description(cursor, table)
                    }
                    for field in model._meta.local_fields:
                        if field.column not in columns:
                            errors.append(f"{alias}.{table}: missing column {field.column}")
                        if field.is_relation:
                            has_fk = any(
                                c.get("foreign_key") and field.column in c["columns"]
                                for c in constraints.values()
                            )
                            if has_fk != field.db_constraint:
                                errors.append(f"{alias}.{table}.{field.column}: FK mismatch")
                        if field.unique and not any(
                            c.get("unique") and c["columns"] == [field.column]
                            for c in constraints.values()
                        ):
                            errors.append(f"{alias}.{table}.{field.column}: missing unique key")
                        if field.is_relation and not any(
                            c.get("index") and c["columns"][0] == field.column
                            for c in constraints.values()
                        ):
                            errors.append(f"{alias}.{table}.{field.column}: missing REF/FK index")
                    for constraint in [*model._meta.constraints, *model._meta.indexes]:
                        if constraint.name not in constraints:
                            errors.append(f"{alias}.{table}: missing {constraint.name}")
                expected_triggers = {
                    "catalog": {"stock_movement_no_update", "stock_movement_no_delete"},
                    "default": {"order_item_snapshot_immutable"},
                }.get(alias, set())
                cursor.execute(
                    "SELECT trigger_name FROM information_schema.triggers "
                    "WHERE trigger_schema=DATABASE()"
                )
                missing = expected_triggers - {row[0] for row in cursor.fetchall()}
                errors.extend(f"{alias}: missing SQL guard {name}" for name in missing)
        if errors:
            raise CommandError("\n".join(errors))
        self.stdout.write(
            self.style.SUCCESS("Five-schema ownership and constraint validation passed.")
        )
