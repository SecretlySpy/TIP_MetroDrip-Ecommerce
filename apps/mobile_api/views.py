"""Public mobile API views (Epic H, FR-21…FR-29).

Every operation delegates to the same domain services the web storefront uses;
this module never computes prices, decides stock, or transitions order state on
its own (D-13 mirrored server-side: one implementation, many clients).
"""

import logging

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.core.signing import BadSignature, Signer
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.models import Customer, WishlistItem
from apps.catalog.services import get_all_categories, get_catalog_queryset, get_product_detail
from apps.inventory.services import InsufficientStock, get_stock_record
from apps.notifications.models import DeviceToken, Notification
from apps.orders.checkout import CheckoutError, PaymentSessionError, parse_items, place_order
from apps.orders.models import Order, OrderStatus
from apps.orders.money import format_centavos
from apps.payments.services import confirm_order_paid
from apps.reviews.models import Review, ReviewStatus
from apps.shipping.models import ShippingZone

from .errors import error_payload
from .serializers import (
    CategorySerializer,
    DeviceTokenSerializer,
    NotificationSerializer,
    ProductListSerializer,
    ProfileSerializer,
    RegisterSerializer,
)

logger = logging.getLogger(__name__)

_PROGRESS_STEPS = ["pending", "paid", "packed", "shipped", "delivered"]


def _tokens_for(customer):
    refresh = RefreshToken.for_user(customer)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def _auth_payload(customer):
    return {**_tokens_for(customer), "customer": ProfileSerializer(customer).data}


def _claim_guest_orders(customer):
    """FR-15/FR-22 parity with web registration: attach matching guest orders."""
    claimed = 0
    for order in Order.objects.filter(
        customer__isnull=True, shipping_address__email=customer.email
    ):
        order.customer = customer
        order.save(update_fields=["customer"])
        claimed += 1
    return claimed


# ---------------------------------------------------------------------------
# H-3: Auth
# ---------------------------------------------------------------------------


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth-burst"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        customer = Customer.objects.create_user(
            email=data["email"], password=data["password"], name=data["name"], phone=data["phone"]
        )
        _claim_guest_orders(customer)
        return Response(_auth_payload(customer), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth-burst"

    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        password = request.data.get("password", "")
        customer = authenticate(request, username=email, password=password)
        if customer is None:
            return Response(
                error_payload("invalid_credentials", "Invalid email or password."),
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(_auth_payload(customer))


class RefreshView(TokenRefreshView):
    """SimpleJWT refresh with the credential-endpoint throttle budget."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth-burst"


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            RefreshToken(request.data.get("refresh", "")).blacklist()
        except TokenError:
            # An already-dead token means the goal state is reached.
            pass
        return Response(status=status.HTTP_205_RESET_CONTENT)


class PasswordResetRequestView(APIView):
    """FR-22 password reset, fully in-app via a deep link.

    Always answers 202: whether the email exists is never disclosed.
    """

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth-burst"

    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        customer = Customer.objects.filter(email=email, is_active=True).first()
        if customer and customer.has_usable_password():
            uid = urlsafe_base64_encode(force_bytes(customer.pk))
            token = default_token_generator.make_token(customer)
            deep_link = f"{settings.MOBILE_APP_SCHEME}://reset-password?uid={uid}&token={token}"
            send_mail(
                subject="Reset your MetroDrip password",
                message=(
                    "Tap the link on your phone to choose a new password:\n"
                    f"{deep_link}\n\nIf you didn't ask for this, ignore this email."
                ),
                from_email=None,
                recipient_list=[customer.email],
            )
        return Response({"status": "accepted"}, status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth-burst"

    def post(self, request):
        try:
            customer = Customer.objects.get(
                pk=force_str(urlsafe_base64_decode(str(request.data.get("uid", ""))))
            )
        except (Customer.DoesNotExist, ValueError, TypeError, OverflowError):
            customer = None
        if customer is None or not default_token_generator.check_token(
            customer, str(request.data.get("token", ""))
        ):
            return Response(
                error_payload("invalid_reset_token", "This reset link is invalid or expired."),
                status=status.HTTP_400_BAD_REQUEST,
            )
        password = str(request.data.get("new_password", ""))
        try:
            validate_password(password, customer)
        except Exception as exc:
            # Django's validators raise ValidationError with `.messages`; surface
            # them as DRF field errors so the app can map them onto the input.
            raise DRFValidationError(
                {"new_password": list(getattr(exc, "messages", [str(exc)]))}
            ) from exc
        customer.set_password(password)
        customer.save(update_fields=["password"])
        return Response({"status": "password_changed"})


# ---------------------------------------------------------------------------
# H-2: Catalog
# ---------------------------------------------------------------------------


class ProductListView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductListSerializer

    def get_queryset(self):
        params = self.request.query_params
        filters = {
            key: params.get(key, "")
            for key in ("category", "size", "color", "fit", "price_min", "price_max")
        }
        return get_catalog_queryset(
            filters={k: v for k, v in filters.items() if v},
            sort=params.get("sort", "newest"),
            search=params.get("q", "").strip() or None,
        )


class CategoryListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"results": CategorySerializer(get_all_categories(), many=True).data})


class ProductDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        product = get_product_detail(slug)
        if product is None:
            return Response(
                error_payload("not_found", "Product not found."), status=status.HTTP_404_NOT_FOUND
            )

        variants = []
        for variant in product.variants.all():
            variants.append(
                {
                    "id": variant.pk,
                    "sku": variant.sku,
                    "size": variant.size,
                    "color": variant.color,
                    "fit": variant.fit,
                    "price": variant.price,
                    "price_display": format_centavos(variant.price),
                    "available": get_stock_record(variant.pk).available,
                }
            )

        wishlisted = False
        if request.user.is_authenticated:
            wishlisted = WishlistItem.objects.filter(
                customer=request.user, product=product
            ).exists()

        return Response(
            {
                "id": product.pk,
                "name": product.name,
                "slug": product.slug,
                "description": product.description,
                "category": {"name": product.category.name, "slug": product.category.slug},
                "price": product.base_price,
                "price_display": format_centavos(product.base_price),
                "images": product.images,
                "review_avg": product.review_avg,
                "review_count": product.review_count,
                "reviews": [
                    {
                        "author": review.customer.name,
                        "rating": review.rating,
                        "body": review.body,
                        "created_at": review.created_at,
                    }
                    for review in product.approved_reviews
                ],
                "variants": variants,
                "is_wishlisted": wishlisted,
            }
        )


# ---------------------------------------------------------------------------
# H-4: Cart validation + checkout
# ---------------------------------------------------------------------------


class CartValidateView(APIView):
    """Server-authoritative cart snapshot: prices and availability (D-13)."""

    permission_classes = [AllowAny]

    def post(self, request):
        try:
            quantities = parse_items(request.data.get("items"))
        except CheckoutError as error:
            return Response(
                error_payload("invalid_request", str(error)), status=status.HTTP_400_BAD_REQUEST
            )

        from apps.catalog.models import ProductVariant

        variants = {
            v.pk: v
            for v in ProductVariant.objects.select_related("product").filter(pk__in=quantities)
        }
        lines, subtotal, all_available = [], 0, True
        for variant_id, qty in quantities.items():
            variant = variants.get(variant_id)
            if variant is None:
                lines.append({"variant_id": variant_id, "removed": True})
                all_available = False
                continue
            available = get_stock_record(variant_id).available
            line_total = variant.price * qty
            subtotal += line_total
            if available < qty:
                all_available = False
            lines.append(
                {
                    "variant_id": variant_id,
                    "sku": variant.sku,
                    "product_name": variant.product.name,
                    "qty": qty,
                    "available": available,
                    "unit_price": variant.price,
                    "unit_price_display": format_centavos(variant.price),
                    "line_total": line_total,
                    "line_total_display": format_centavos(line_total),
                }
            )
        payload = {
            "lines": lines,
            "subtotal": subtotal,
            "subtotal_display": format_centavos(subtotal),
            "all_available": all_available,
        }

        # M05's summary card shows shipping + grand total. The app may pass a
        # zone so BOTH stay server-computed (D-13: no arithmetic on-device).
        zone_id = request.data.get("zone_id")
        if zone_id is not None:
            zone = ShippingZone.objects.filter(id=zone_id, is_active=True).first()
            if zone is not None:
                payload.update(
                    {
                        "zone_name": zone.name,
                        "shipping_fee": zone.fee,
                        "shipping_fee_display": format_centavos(zone.fee),
                        "total": subtotal + zone.fee,
                        "total_display": format_centavos(subtotal + zone.fee),
                    }
                )
        return Response(payload)


class CheckoutView(APIView):
    """Guest-capable checkout (FR-22/FR-25): reserve → order → payment session."""

    permission_classes = [AllowAny]

    def post(self, request):
        scheme = settings.MOBILE_APP_SCHEME
        try:
            order, checkout_url = place_order(
                items=request.data.get("items"),
                zone_id=request.data.get("zone_id"),
                contact={
                    "name": request.data.get("customer_name", ""),
                    "email": request.data.get("email", ""),
                    "phone": request.data.get("phone", ""),
                    "address_line1": request.data.get("address_line1", ""),
                    "city": request.data.get("city", ""),
                },
                customer=request.user if request.user.is_authenticated else None,
                session_key=f"mobile:{request.META.get('REMOTE_ADDR', '')}",
                success_url=f"{scheme}://checkout/success?token=__TOKEN__",
                cancel_url=f"{scheme}://checkout/cancel",
            )
        except CheckoutError as error:
            return Response(
                error_payload("invalid_request", str(error)), status=status.HTTP_400_BAD_REQUEST
            )
        except InsufficientStock:
            return Response(
                error_payload(
                    "insufficient_stock",
                    "Some items just sold out. Review your cart and try again.",
                ),
                status=status.HTTP_409_CONFLICT,
            )
        except PaymentSessionError:
            return Response(
                error_payload(
                    "provider_unavailable",
                    "Payment provider is unavailable right now — please try again.",
                ),
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                "order_no": order.order_no,
                "status_token": Signer().sign(str(order.pk)),
                "checkout_url": checkout_url,
                "payment_provider": settings.PAYMENT_PROVIDER,
                "total": order.total,
                "total_display": format_centavos(order.total),
            },
            status=status.HTTP_201_CREATED,
        )


class SimulatedPaymentConfirmView(APIView):
    """Simulated-provider completion for the mobile flow (D-08 parity).

    Exists ONLY while PAYMENT_PROVIDER == "simulated"; under the real provider
    the route answers 404 and the signature-verified webhook remains the sole
    payment truth (Invariant 3).
    """

    permission_classes = [AllowAny]

    def post(self, request):
        if settings.PAYMENT_PROVIDER != "simulated":
            return Response(
                error_payload("not_found", "Not found."), status=status.HTTP_404_NOT_FOUND
            )
        try:
            order_id = Signer().unsign(str(request.data.get("status_token", "")))
            order = Order.objects.get(pk=order_id)
        except (BadSignature, Order.DoesNotExist):
            return Response(
                error_payload("not_found", "Unknown order token."),
                status=status.HTTP_404_NOT_FOUND,
            )

        newly_confirmed = confirm_order_paid(order=order)
        if newly_confirmed:
            try:
                from apps.notifications.services import send_order_confirmation

                token = Signer().sign(str(order.pk))
                status_url = request.build_absolute_uri(
                    reverse("storefront:order-status", args=[token])
                )
                send_order_confirmation(order, status_url)
            except Exception:
                logger.exception("Confirmation email failed for %s", order.order_no)
        order.refresh_from_db()
        return Response({"order_no": order.order_no, "status": order.status})


# ---------------------------------------------------------------------------
# H-5: Orders + tracking timeline
# ---------------------------------------------------------------------------


def _timeline(order):
    """FR-26: mirror the server-side state machine exactly — never recompute
    client-side."""
    if order.status not in _PROGRESS_STEPS:
        return None
    current = _PROGRESS_STEPS.index(order.status)
    return [
        {
            "key": step,
            "label": step.title(),
            "state": "done" if i < current else "current" if i == current else "todo",
        }
        for i, step in enumerate(_PROGRESS_STEPS)
    ]


def _order_payload(order, *, include_items=True):
    payload = {
        "order_no": order.order_no,
        "status": order.status,
        "status_display": order.get_status_display(),
        "created_at": order.created_at,
        "subtotal": order.subtotal,
        "subtotal_display": format_centavos(order.subtotal),
        "shipping_fee": order.shipping_fee,
        "shipping_fee_display": format_centavos(order.shipping_fee),
        "total": order.total,
        "total_display": format_centavos(order.total),
        "shipping_address": order.shipping_address,
        "status_token": Signer().sign(str(order.pk)),
        "timeline": _timeline(order),
        "item_count": sum(item.qty for item in order.items.all()),
    }
    shipment = getattr(order, "shipment", None)
    payload["shipment"] = (
        {
            "courier": shipment.courier,
            "waybill_no": shipment.waybill_no,
            "tracking_url": shipment.tracking_url,
            "status": shipment.status,
        }
        if shipment
        else None
    )
    if include_items:
        payload["items"] = [
            {
                "product_name": item.variant.product.name,
                "product_slug": item.variant.product.slug,
                "sku": item.variant.sku,
                "size": item.variant.size,
                "color": item.variant.color,
                "fit": item.variant.fit,
                "qty": item.qty,
                "unit_price": item.unit_price_snapshot,
                "unit_price_display": format_centavos(item.unit_price_snapshot),
            }
            for item in order.items.select_related("variant__product")
        ]
    return payload


class OrderListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        orders = (
            Order.objects.filter(customer=request.user)
            .prefetch_related("items__variant__product")
            .select_related("shipment")
            .order_by("-created_at")[:50]
        )
        return Response({"results": [_order_payload(o, include_items=False) for o in orders]})


class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, order_no):
        try:
            order = Order.objects.prefetch_related("items__variant__product").get(
                order_no=order_no, customer=request.user
            )
        except Order.DoesNotExist:
            return Response(
                error_payload("not_found", "Order not found."), status=status.HTTP_404_NOT_FOUND
            )
        return Response(_order_payload(order))


class OrderTrackView(APIView):
    """Tokenized guest tracking — the mobile twin of the web status page."""

    permission_classes = [AllowAny]

    def get(self, request, token):
        try:
            order = Order.objects.prefetch_related("items__variant__product").get(
                pk=Signer().unsign(token)
            )
        except (BadSignature, Order.DoesNotExist):
            return Response(
                error_payload("not_found", "Order not found."), status=status.HTTP_404_NOT_FOUND
            )
        return Response(_order_payload(order))


# ---------------------------------------------------------------------------
# H-6: Account, wishlist, reviews · shipping zones
# ---------------------------------------------------------------------------


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(ProfileSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ZoneListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                "results": [
                    {
                        "id": zone.pk,
                        "name": zone.name,
                        "fee": zone.fee,
                        "fee_display": format_centavos(zone.fee),
                    }
                    for zone in ShippingZone.objects.filter(is_active=True).order_by("name")
                ]
            }
        )


class WishlistView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = WishlistItem.objects.filter(customer=request.user).select_related(
            "product__category"
        )
        results = []
        for item in items:
            product = item.product
            in_stock = any(
                get_stock_record(variant_id).available > 0
                for variant_id in product.variants.values_list("pk", flat=True)
            )
            results.append(
                {
                    "product": ProductListSerializer(
                        get_catalog_queryset().get(pk=product.pk)
                    ).data,
                    "in_stock": in_stock,
                    "saved_at": item.created_at,
                }
            )
        return Response({"results": results})

    def post(self, request):
        from apps.catalog.models import Product

        try:
            product = Product.objects.get(pk=request.data.get("product_id"))
        except (Product.DoesNotExist, ValueError, TypeError):
            return Response(
                error_payload("not_found", "Unknown product."), status=status.HTTP_404_NOT_FOUND
            )
        item, created = WishlistItem.objects.get_or_create(customer=request.user, product=product)
        if not created:
            item.delete()
        return Response({"added": created})


class ReviewCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.catalog.models import Product

        try:
            order = Order.objects.get(
                order_no=str(request.data.get("order_no", "")), customer=request.user
            )
            product = Product.objects.get(pk=request.data.get("product_id"))
        except (Order.DoesNotExist, Product.DoesNotExist, ValueError, TypeError):
            return Response(
                error_payload("not_found", "Order or product not found."),
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            rating = int(request.data.get("rating", ""))
        except (TypeError, ValueError):
            rating = 0

        # FR-17 verified-purchase rule, enforced server-side only (H-6 gate).
        if order.status != OrderStatus.DELIVERED:
            message = "You can only review items from delivered orders."
        elif not 1 <= rating <= 5:
            message = "Pick a rating from 1 to 5 stars."
        elif not order.items.filter(variant__product=product).exists():
            message = "That product is not part of this order."
        else:
            Review.objects.update_or_create(
                customer=request.user,
                product=product,
                defaults={
                    "order": order,
                    "rating": rating,
                    "body": str(request.data.get("body", "")).strip(),
                    "status": ReviewStatus.PENDING,
                },
            )
            return Response({"status": "pending_moderation"}, status=status.HTTP_201_CREATED)
        return Response(
            error_payload("invalid_request", message), status=status.HTTP_400_BAD_REQUEST
        )


# ---------------------------------------------------------------------------
# H-10: Devices + notification centre
# ---------------------------------------------------------------------------


class DeviceRegisterView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # A token follows whoever is signed in on the device.
        DeviceToken.objects.update_or_create(
            token=serializer.validated_data["token"],
            defaults={
                "customer": request.user,
                "platform": serializer.validated_data["platform"],
            },
        )
        return Response({"status": "registered"}, status=status.HTTP_201_CREATED)


class NotificationListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(customer=self.request.user).select_related("order")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        # FR-28: the badge shows total unread, not just this page's.
        response.data["unread_count"] = Notification.objects.filter(
            customer=request.user, is_read=False
        ).count()
        return response


class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        updated = Notification.objects.filter(pk=pk, customer=request.user).update(is_read=True)
        if not updated:
            return Response(
                error_payload("not_found", "Notification not found."),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"status": "read"})


class NotificationReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(customer=request.user, is_read=False).update(is_read=True)
        return Response({"status": "all_read"})
