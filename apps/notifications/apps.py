from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"

    def ready(self):
        import apps.notifications.providers.console  # noqa: F401
        import apps.notifications.providers.email_sms  # noqa: F401
        import apps.notifications.providers.http  # noqa: F401
