"""Offline, copy-based transfer from the upgraded legacy schema.

No source rows or tables are deleted. Import refuses populated targets and
verifies hashes before writes. Keep the application stopped until validation
completes; five independent databases cannot provide an atomic bulk import.
"""

import hashlib
import itertools
import json
import os
from pathlib import Path

from django.apps import apps
from django.core import serializers
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from config.database_layout import SCHEMA_NAMES, owner


class Command(BaseCommand):
    help = "Export an upgraded legacy database or import verified fixtures into empty schemas."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["export", "import"])
        parser.add_argument("directory")

    def handle(self, action, directory, **options):
        path = Path(directory).resolve()
        if action == "export":
            self.export(path)
        else:
            self.import_data(path)

    def domain_models(self):
        return [m for m in apps.get_models() if m._meta.managed and not m._meta.proxy]

    def export(self, path):
        if set(connections) != {"default"}:
            raise CommandError("Export requires DATABASE_LAYOUT=legacy and upgraded migrations.")
        if path.exists() and any(path.iterdir()):
            raise CommandError("Export directory must be empty; existing files are never overwritten.")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path, 0o700)
        manifest = {"version": 1, "files": {}, "counts": {}}
        for alias in SCHEMA_NAMES:
            models = [m for m in self.domain_models() if
                      ("default" if m._meta.app_label == "core" else owner(m._meta.app_label)) == alias]
            queries = [m.objects.using("default").order_by("pk") for m in models]
            for model, query in zip(models, queries, strict=True):
                manifest["counts"][model._meta.label_lower] = query.count()
            target = path / f"{alias}.json"
            with target.open("x", encoding="utf-8") as stream:
                os.chmod(target, 0o600)
                serializers.serialize("json", itertools.chain.from_iterable(
                    q.iterator(chunk_size=500) for q in queries), stream=stream)
            manifest["files"][target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
        (path / "manifest.json").write_text(json.dumps(manifest, indent=2))
        os.chmod(path / "manifest.json", 0o600)
        self.stdout.write("Export complete. Preserve this directory as sensitive backup data.")

    def import_data(self, path):
        if set(connections) != set(SCHEMA_NAMES):
            raise CommandError("Import requires DATABASE_LAYOUT=five.")
        manifest = json.loads((path / "manifest.json").read_text())
        if manifest.get("version") != 1 or set(manifest["files"]) != {
            f"{a}.json" for a in SCHEMA_NAMES
        }:
            raise CommandError("Unrecognized transfer manifest.")
        for name, digest in manifest["files"].items():
            if hashlib.sha256((path / name).read_bytes()).hexdigest() != digest:
                raise CommandError(f"Checksum mismatch: {name}")
        bootstrap = {"contenttypes.contenttype", "auth.permission", "sites.site"}
        # Check every target before clearing even bootstrap-only records.
        for model in self.domain_models():
            if model._meta.label_lower in bootstrap:
                continue
            aliases = SCHEMA_NAMES if model._meta.app_label == "core" else [owner(model._meta.app_label)]
            for alias in aliases:
                if model.objects.using(alias).exists():
                    raise CommandError(f"Target is not empty: {alias}.{model._meta.db_table}")
        # Fresh post_migrate defaults have different PKs from the source.
        # Source IDs must win so auth permissions and memberships retain meaning.
        for label in ("auth.permission", "contenttypes.contenttype", "sites.site"):
            model = apps.get_model(label)
            model.objects.using(owner(model._meta.app_label)).all().delete()
        for alias in ("identity", "catalog", "fulfillment", "content", "default"):
            call_command("loaddata", str(path / f"{alias}.json"), database=alias, verbosity=0)
        for label, expected in manifest["counts"].items():
            model = apps.get_model(label)
            alias = "default" if model._meta.app_label == "core" else owner(model._meta.app_label)
            actual = model.objects.using(alias).count()
            if actual != expected:
                raise CommandError(f"Row count mismatch for {label}: {actual} != {expected}")
        call_command("validate_service_schemas")
        self.stdout.write("Import and row-count verification complete. Source remains unchanged.")
