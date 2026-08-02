"""Root URL configuration.

Public storefront, webhook, and account routes are added by their own epics
(strict build order) — each app will expose an urls.py that gets included here.

The back office is two separate mounts, not one (ADR-F-001):

    /admin/     administrator console — accounts, roles, settings, audit trail
    /merchant/  merchant console      — catalog, stock, orders, content, reviews

`admin.site` is the administrator console (config/admin.py), so it keeps the
`admin:` URL namespace that Django's own templates and every existing
`reverse("admin:...")` call already depend on. The merchant console registers
under the `merchant:` instance namespace.
"""

from django.contrib import admin
from django.urls import include, path

from apps.storefront.views import staging_seed_preview
from config.consoles import merchant_site
from config.views import liveness, readiness

urlpatterns = [
    path("healthz/live/", liveness, name="healthz-live"),
    path("healthz/ready/", readiness, name="healthz-ready"),
    path("staging/seed/", staging_seed_preview, name="staging-seed-preview"),
    path("admin/", admin.site.urls),
    path("merchant/", merchant_site.urls),
    # Storefront routes (Epic C): homepage, shop, product detail, cart.
    # Included last so admin/health/staging paths take precedence.
    # Public mobile API (Epic H, D-12) — separate surface from the internal
    # service endpoints; token-authenticated, throttled, versioned.
    path("api/mobile/v1/", include("apps.mobile_api.urls")),
    path("api/", include("apps.payments.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("reviews/", include("apps.reviews.urls")),
    path("pages/", include("django.contrib.flatpages.urls")),
    path("", include("apps.storefront.urls")),
]
