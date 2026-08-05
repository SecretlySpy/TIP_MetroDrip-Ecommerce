"""Mobile API serializers (H-2/H-3/H-5/H-6).

Money is always serialized twice: the integer centavo value (the app never
computes with it — D-13) plus a server-formatted display string.
"""

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.accounts.models import Customer
from apps.core.money import format_centavos
from apps.notifications.models import DevicePlatform, DeviceToken, Notification


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")

    def validate_email(self, value):
        value = value.strip().lower()
        if Customer.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already in use.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "email", "name", "phone", "addresses"]
        read_only_fields = ["id", "email", "addresses"]


class CategorySerializer(serializers.Serializer):
    name = serializers.CharField()
    slug = serializers.SlugField()
    product_count = serializers.IntegerField(default=0)


class ProductListSerializer(serializers.Serializer):
    """Card payload for grids (M02/M03/M11); one object per product."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    slug = serializers.SlugField()
    category = serializers.SerializerMethodField()
    price = serializers.IntegerField(source="base_price")
    price_display = serializers.SerializerMethodField()
    images = serializers.ListField(child=serializers.CharField(), default=list)
    review_avg = serializers.FloatField(allow_null=True, required=False)
    review_count = serializers.IntegerField(default=0, required=False)

    def get_category(self, obj):
        return {"name": obj.category.name, "slug": obj.category.slug}

    def get_price_display(self, obj):
        return format_centavos(obj.base_price)


class VariantSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sku = serializers.CharField()
    size = serializers.CharField()
    color = serializers.CharField()
    fit = serializers.CharField()
    price = serializers.IntegerField()
    price_display = serializers.CharField()
    available = serializers.IntegerField()


class DeviceTokenSerializer(serializers.ModelSerializer):
    platform = serializers.ChoiceField(choices=DevicePlatform.choices)

    class Meta:
        model = DeviceToken
        fields = ["token", "platform"]


class NotificationSerializer(serializers.ModelSerializer):
    order_no = serializers.CharField(source="order.order_no", default=None)

    class Meta:
        model = Notification
        fields = ["id", "title", "body", "category", "order_no", "is_read", "created_at"]
