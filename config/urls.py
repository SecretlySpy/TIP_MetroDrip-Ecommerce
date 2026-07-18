"""Root URL configuration.

Public storefront, webhook, and account routes are added by their own epics
(strict build order) — each app will expose an urls.py that gets included here.
"""

from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
]
