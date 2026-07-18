"""Root URL configuration.

Public storefront, webhook, and account routes are added by their own epics
(strict build order) — each app will expose an urls.py that gets included here.
"""

from django.contrib import admin
from django.urls import path

from apps.storefront.views import staging_seed_preview
from config.views import liveness, readiness

urlpatterns = [
    path("healthz/live/", liveness, name="healthz-live"),
    path("healthz/ready/", readiness, name="healthz-ready"),
    path("staging/seed/", staging_seed_preview, name="staging-seed-preview"),
    path("admin/", admin.site.urls),
]
