"""Apply the migration graph to each owning database, then validate ownership."""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = "Migrate all five pre-created MySQL schemas in dependency order."

    def handle(self, **options):
        aliases = ("identity", "catalog", "fulfillment", "content", "default")
        if set(connections) != set(aliases):
            raise CommandError("This command requires DATABASE_LAYOUT=five.")
        for alias in aliases:
            self.stdout.write(f"Migrating {alias}")
            call_command(
                "migrate", database=alias, interactive=False, verbosity=options["verbosity"]
            )
        call_command("validate_service_schemas")
