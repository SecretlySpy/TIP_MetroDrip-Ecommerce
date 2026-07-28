"""Shared admin helpers used by both consoles."""

import csv

from django.http import HttpResponse


class ExportCsvMixin:
    """Add an "Export Selected as CSV" action to a ModelAdmin.

    Set `csv_export_exclude` to keep a column out of the file. It defaults to
    excluding `password`: the mixin walks `_meta.fields`, and on the Customer
    admin that would otherwise write every selected account's password hash into
    a downloadable file — offline-crackable, and a category of personal data the
    export has no reason to carry (NFR Privacy-11).
    """

    #: Field names never written to the CSV, whatever the model.
    csv_export_exclude: tuple[str, ...] = ("password",)

    def export_as_csv(self, request, queryset):
        meta = self.model._meta
        excluded = set(self.csv_export_exclude)
        field_names = [field.name for field in meta.fields if field.name not in excluded]

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f"attachment; filename={meta}.csv"
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            writer.writerow([getattr(obj, field) for field in field_names])

        return response

    export_as_csv.short_description = "Export Selected as CSV"
