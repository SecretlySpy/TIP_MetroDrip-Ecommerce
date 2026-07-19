from django.contrib import admin
from .models import HomepageBanner, ContactMessage

@admin.register(HomepageBanner)
class HomepageBannerAdmin(admin.ModelAdmin):
    list_display = ("title", "order", "is_active")
    list_editable = ("order", "is_active")

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "created_at", "is_resolved")
    list_filter = ("is_resolved", "created_at")
    search_fields = ("name", "email", "message")
    list_editable = ("is_resolved",)
    readonly_fields = ("name", "email", "message", "created_at")
