"""Customer accounts (§4, FR-14/15/16).

Customer is the project's AUTH_USER_MODEL. Guest checkout deliberately creates
no Customer row: a guest Order has customer=NULL and keeps its contact email in
the shipping-address snapshot. An unusable password therefore means an account
cannot log in yet; it is not used as a guest-identity flag.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class CustomerManager(BaseUserManager):
    """Email-as-username manager; no separate username field exists."""

    use_in_migrations = True

    def _create(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Customer requires an email address")
        customer = self.model(email=self.normalize_email(email), **extra_fields)
        if password is not None:
            customer.set_password(password)
        else:
            # Django's auth schema requires a string password column. Its
            # built-in unusable marker safely represents passwordless accounts.
            customer.set_unusable_password()
        customer.save(using=self._db)
        return customer

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not password:
            raise ValueError("Superuser requires a non-empty password")
        if not (extra_fields["is_staff"] and extra_fields["is_superuser"]):
            raise ValueError("Superuser must have is_staff=True and is_superuser=True")
        return self._create(email, password, **extra_fields)


class Customer(AbstractBaseUser, PermissionsMixin):
    """Registered shopper identity used by Django authentication."""

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=32, blank=True)
    # Saved shipping addresses (FR-14): list of {label, line1, city, province,
    # postal_code, zone, contact_phone} dicts. JSON because addresses are
    # display/prefill data, never queried relationally in v1.
    addresses = models.JSONField(default=list, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # admin-site access only, never storefront logic
    date_joined = models.DateTimeField(default=timezone.now)

    objects = CustomerManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    def __str__(self):
        return self.email


class WishlistItem(models.Model):
    """FR-16: product saved by a logged-in customer. Product-level, not variant-level."""

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="wishlisted_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # §4: unique together — saving twice is a no-op, not a duplicate.
            models.UniqueConstraint(fields=["customer", "product"], name="uniq_wishlist_entry"),
        ]

    def __str__(self):
        return f"{self.customer} ♥ {self.product}"
