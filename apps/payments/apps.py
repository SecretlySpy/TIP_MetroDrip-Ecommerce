from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payments"

    def ready(self):
        # Importing the concrete providers is what runs their
        # @register_provider decorators and fills the registry — without this,
        # get_payment_provider() raises "Unknown payment provider". The names
        # are deliberately unused; do not "clean up" this import.
        from .providers import paymongo, simulated  # noqa: F401
