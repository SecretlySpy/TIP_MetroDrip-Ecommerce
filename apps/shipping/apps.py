from django.apps import AppConfig


class ShippingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.shipping"

    def ready(self):
        # Side-effect import: running the modules is what registers the
        # providers. The names are deliberately unused — do not remove.
        from .providers import http, jnt, simulated  # noqa: F401
