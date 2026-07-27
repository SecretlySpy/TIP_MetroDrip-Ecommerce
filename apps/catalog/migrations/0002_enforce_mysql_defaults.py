"""Repair and verify the MySQL storage invariants for existing installations."""

from django.db import migrations


def enforce_mysql_defaults(apps, schema_editor):
    """Normalize database defaults and any pre-existing noncompliant tables."""
    # Migrations intentionally reject substitute databases because row-locking behavior is required.
    connection = schema_editor.connection
    if connection.vendor != "mysql":
        raise RuntimeError("MetroDrip migrations require MySQL 8.")

    # The configured database name is quoted as an identifier before it reaches SQL.
    database_name = connection.settings_dict["NAME"]
    quoted_database = connection.ops.quote_name(database_name)

    with connection.cursor() as cursor:
        # Future tables inherit the required Unicode charset and deterministic collation.
        cursor.execute(
            f"ALTER DATABASE {quoted_database} "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
        )
        # The active migration connection must create every later table with InnoDB.
        cursor.execute("SET SESSION default_storage_engine = InnoDB")

        # Locate only legacy tables that actually need repair to avoid unnecessary rebuilds.
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_type = 'BASE TABLE'
              AND (
                engine <> 'InnoDB'
                OR table_collation <> 'utf8mb4_0900_ai_ci'
              )
            ORDER BY table_name
            """
        )
        noncompliant_tables = [row[0] for row in cursor.fetchall()]

        # Each metadata-derived table name is quoted before the one-time normalization.
        for table_name in noncompliant_tables:
            quoted_table = connection.ops.quote_name(table_name)
            cursor.execute(
                f"ALTER TABLE {quoted_table} ENGINE=InnoDB, "
                "CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )

        # Verify the database defaults rather than assuming ALTER DATABASE succeeded.
        cursor.execute(
            """
            SELECT default_character_set_name, default_collation_name
            FROM information_schema.schemata
            WHERE schema_name = DATABASE()
            """
        )
        database_defaults = cursor.fetchone()
        # Verify the session engine because subsequent migrations share this connection.
        cursor.execute("SELECT @@SESSION.default_storage_engine")
        storage_engine = cursor.fetchone()[0]
        # A second metadata query proves that the repair left no table behind.
        cursor.execute(
            """
            SELECT table_name, engine, table_collation
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_type = 'BASE TABLE'
              AND (
                engine <> 'InnoDB'
                OR table_collation <> 'utf8mb4_0900_ai_ci'
              )
            ORDER BY table_name
            """
        )
        remaining_violations = cursor.fetchall()

    # One explicit failure keeps a partially normalized installation from booting unnoticed.
    expected_defaults = ("utf8mb4", "utf8mb4_0900_ai_ci")
    if (
        database_defaults != expected_defaults
        or storage_engine.lower() != "innodb"
        or remaining_violations
    ):
        raise RuntimeError(
            "MySQL did not apply the required InnoDB/utf8mb4 defaults "
            f"or table normalization: {remaining_violations!r}"
        )


class Migration(migrations.Migration):
    """Apply the invariant repair once without pretending MySQL DDL is transactional."""

    # MySQL commits DDL statements implicitly, so rerunnable operations are safer than atomic wrapping.
    atomic = False

    # The repair follows the original catalog schema and also covers databases already in production.
    dependencies = [
        ("catalog", "0001_initial"),
    ]

    # Reversal keeps data and server defaults intact because downgrading either would be unsafe.
    operations = [
        migrations.RunPython(enforce_mysql_defaults, migrations.RunPython.noop),
    ]
