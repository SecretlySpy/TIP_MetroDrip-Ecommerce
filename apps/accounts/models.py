"""Customer accounts (§4, FR-14/15/16).

Customer is the project's AUTH_USER_MODEL. Guest checkout deliberately creates
no Customer row: a guest Order has customer=NULL and keeps its contact email in
the shipping-address snapshot. An unusable password therefore means an account
cannot log in yet; it is not used as a guest-identity flag.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .roles import CONSOLE_ROLES, StaffRole

__all__ = ["CONSOLE_ROLES", "Customer", "CustomerManager", "StaffRole", "WishlistItem"]


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
        # A superuser reaches every console regardless of role, but defaulting to
        # ADMINISTRATOR keeps `role` an honest description of the account rather
        # than leaving the project's most privileged login labelled "Customer".
        extra_fields.setdefault("role", StaffRole.ADMINISTRATOR)
        if not password:
            raise ValueError("Superuser requires a non-empty password")
        if not (extra_fields["is_staff"] and extra_fields["is_superuser"]):
            raise ValueError("Superuser must have is_staff=True and is_superuser=True")
        return self._create(email, password, **extra_fields)

    def merchants(self):
        """Accounts that can currently reach the merchant console."""
        return self.filter(is_active=True, is_staff=True).filter(
            models.Q(is_superuser=True) | models.Q(role=StaffRole.MERCHANT)
        )

    def administrators(self):
        """Accounts that can currently reach the administrator console."""
        return self.filter(is_active=True, is_staff=True).filter(
            models.Q(is_superuser=True) | models.Q(role=StaffRole.ADMINISTRATOR)
        )


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
    is_staff = models.BooleanField(default=False)  # console access only, never storefront logic
    # Which back-office console this account belongs to. `is_staff` is the gate;
    # `role` is the routing. Both are checked on every console request — see
    # `config.consoles.ConsoleSite.has_permission`.
    role = models.CharField(
        max_length=16,
        choices=StaffRole.choices,
        default=StaffRole.CUSTOMER,
        db_index=True,
        help_text="Which back-office console this account may enter. "
        "Requires staff status to take effect.",
    )
    date_joined = models.DateTimeField(default=timezone.now)

    objects = CustomerManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    def __str__(self):
        return self.email

    def clean(self):
        """Reject a console role that staff status would silently neutralise.

        Like `Category.clean`, this runs through ModelForms (so the administrator
        console cannot save the contradiction) but not through bulk seeds, which
        are trusted. The runtime check in `console` is the real boundary — this
        only stops an operator from creating an account that looks privileged and
        is not.
        """
        super().clean()
        if self.role in CONSOLE_ROLES and not self.is_staff:
            raise ValidationError(
                {
                    "is_staff": "Staff status is required for the "
                    f"{self.get_role_display()} role to grant console access."
                }
            )

    @property
    def console(self):
        """The console this account may enter right now, or None.

        Superusers answer ADMINISTRATOR because that console owns account and
        role management; `ConsoleSite.has_permission` waves them into the
        merchant console separately rather than forcing a second login.
        """
        if not (self.is_active and self.is_staff):
            return None
        if self.is_superuser:
            return StaffRole.ADMINISTRATOR
        return self.role if self.role in CONSOLE_ROLES else None

    @property
    def is_merchant(self):
        """True when this account may enter the merchant console."""
        return (
            self.is_active
            and self.is_staff
            and (self.is_superuser or self.role == StaffRole.MERCHANT)
        )

    @property
    def is_administrator(self):
        """True when this account may enter the administrator console."""
        return (
            self.is_active
            and self.is_staff
            and (self.is_superuser or self.role == StaffRole.ADMINISTRATOR)
        )


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
