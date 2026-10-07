"""Shared admin helpers used by both consoles."""

import csv

from django.http import HttpResponse


class ServiceReferenceAdminMixin:
    """Search remote IDs separately; never ask MySQL for a cross-schema JOIN."""

    list_select_related = ()

    def get_queryset(self, request):
        from config.database_layout import owner

        query = super().get_queryset(request)
        references = [
            field.name
            for field in self.model._meta.fields
            if field.is_relation
            and owner(field.related_model._meta.app_label) != owner(self.model._meta.app_label)
        ]
        return query.prefetch_related(*references)

    def get_search_results(self, request, queryset, search_term):
        from django.db.models import Q

        from config.database_layout import owner

        if not search_term:
            return queryset, False
        criteria = Q()
        for name in self.get_search_fields(request):
            first, _, rest = name.partition("__")
            field = self.model._meta.get_field(first)
            if (
                rest
                and field.is_relation
                and owner(field.related_model._meta.app_label) != owner(self.model._meta.app_label)
            ):
                ids = list(
                    field.related_model.objects.filter(
                        **{rest + "__icontains": search_term}
                    ).values_list("pk", flat=True)
                )
                criteria |= Q(**{field.attname + "__in": ids})
            else:
                criteria |= Q(**{name + "__icontains": search_term})
        return queryset.filter(criteria).distinct(), True


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
