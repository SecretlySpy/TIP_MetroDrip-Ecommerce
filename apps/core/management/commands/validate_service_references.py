"""Detect orphaned cross-service references without a cross-schema SQL join."""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import router


class Command(BaseCommand):
    help = "Check every live REF against its owner in bounded batches; report orphan counts."

    def handle(self, **options):
        errors = []
        checked = 0
        for model in apps.get_models():
            for field in model._meta.local_fields:
                if not field.is_relation or getattr(field, "db_constraint", True):
                    continue
                target = field.remote_field.model
                rows = (
                    model.objects.using(router.db_for_read(model))
                    .exclude(**{field.attname: None})
                    .values_list(field.attname, flat=True)
                    .iterator(chunk_size=500)
                )
                batch = set()
                missing = 0
                for reference in rows:
                    batch.add(reference)
                    if len(batch) == 500:
                        missing += self.missing(target, batch)
                        batch.clear()
                missing += self.missing(target, batch)
                checked += 1
                if missing:
                    errors.append(f"{model._meta.label}.{field.column}: {missing} orphan(s)")
        if errors:
            raise CommandError("\n".join(errors))
        self.stdout.write(self.style.SUCCESS(f"{checked} cross-service REF fields verified."))

    @staticmethod
    def missing(target, references):
        found = set(
            target.objects.using(router.db_for_read(target))
            .filter(pk__in=references)
            .values_list("pk", flat=True)
        )
        return len(references - found)
