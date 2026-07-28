"""Site content — **merchant console** (FR Merchant-07).

Banners, promotions, and the About / Contact / FAQ / Privacy flat pages are
merchandising copy, so the seller owns them. Customers only ever read this
content (FR Customer-19), and the administrator console does not carry a second
copy of these screens (ADR-F-001).
"""

from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.contrib.flatpages.admin import FlatPageAdmin
from django.contrib.flatpages.models import FlatPage

from config.consoles import merchant_site

from .models import ContactMessage, HomepageBanner


@admin.register(HomepageBanner, site=merchant_site)
class HomepageBannerAdmin(admin.ModelAdmin):
    list_display = ("title", "order", "is_active")
    list_editable = ("order", "is_active")


@admin.register(ContactMessage, site=merchant_site)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "created_at", "is_resolved")
    list_filter = ("is_resolved", "created_at")
    search_fields = ("name", "email", "message")
    list_editable = ("is_resolved",)
    readonly_fields = ("name", "email", "message", "created_at")


# django.contrib.flatpages registers itself on the default site — which is now
# the administrator console — when its admin module is autodiscovered. It sorts
# before apps.cms in INSTALLED_APPS, so by the time this module runs the
# registration exists and can be moved. NotRegistered is tolerated so the import
# stays safe if that ordering ever changes.
try:
    admin.site.unregister(FlatPage)
except NotRegistered:  # pragma: no cover - depends on INSTALLED_APPS ordering
    pass
merchant_site.register(FlatPage, FlatPageAdmin)
