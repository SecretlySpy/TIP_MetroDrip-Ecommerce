from django.urls import path
from . import views

app_name = "payments"

urlpatterns = [
    path("webhooks/paymongo/", views.paymongo_webhook, name="paymongo-webhook"),
]
