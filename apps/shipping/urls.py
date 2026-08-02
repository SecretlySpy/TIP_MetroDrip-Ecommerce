"""Shipping URLs — the inbound courier webhook (§7)."""

from django.urls import path

from . import webhooks

app_name = "shipping"

urlpatterns = [
    path("webhooks/courier/", webhooks.courier_webhook, name="courier-webhook"),
]
