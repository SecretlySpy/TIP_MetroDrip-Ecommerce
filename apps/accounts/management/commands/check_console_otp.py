"""Report which console accounts can still sign in without a second factor.

Run this before turning `CONSOLE_REQUIRE_OTP` on (ADR-P3-029). The flag refuses
every account with no confirmed device, so flipping it blind locks out exactly
the people needed to fix it. This answers "who would that be?" beforehand.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django_otp import devices_for_user


class Command(BaseCommand):
    help = "List staff accounts with no confirmed TOTP device (2FA readiness)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero if any staff account is unenrolled, for CI or a deploy gate.",
        )

    def handle(self, *args, **options):
        staff = get_user_model().objects.filter(is_staff=True, is_active=True).order_by("email")
        enrolled, unenrolled = [], []
        for user in staff:
            has_device = any(True for _ in devices_for_user(user, confirmed=True))
            target = enrolled if has_device else unenrolled
            target.append(user)

        self.stdout.write(f"Active staff accounts: {len(staff)}")
        self.stdout.write(self.style.SUCCESS(f"  With a confirmed TOTP device: {len(enrolled)}"))
        self.stdout.write(
            self.style.WARNING(f"  Without a device (2FA bypassable): {len(unenrolled)}")
        )
        for user in unenrolled:
            role = "superuser" if user.is_superuser else getattr(user, "role", "—")
            self.stdout.write(f"    - {user.email} ({role})")

        if not unenrolled:
            self.stdout.write(
                self.style.SUCCESS("\nEvery active staff account is enrolled. ")
                + "CONSOLE_REQUIRE_OTP can be turned on safely."
            )
            return

        self.stdout.write(
            "\nEnroll a device at /admin/otp_totp/totpdevice/add/ before setting "
            "CONSOLE_REQUIRE_OTP=1, or these accounts will be refused at login."
        )
        if options["strict"]:
            raise SystemExit(1)
