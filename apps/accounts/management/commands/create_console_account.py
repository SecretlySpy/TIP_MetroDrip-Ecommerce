"""Create or re-role a back-office account.

`createsuperuser` only makes superusers, and a superuser reaches both consoles —
so using it is the fastest way to accidentally prove nothing about the
separation. This command mints a *scoped* account instead: staff, one role, one
console, no superuser flag.

    python manage.py create_console_account --role merchant \
        --email seller@metrodrip.test --name "Demo Seller"

The password is read from `--password`, or from `METRODRIP_CONSOLE_PASSWORD`, or
prompted for. Re-running against an existing email updates the role and staff
status rather than failing, which makes it safe in a setup script; the password
is only ever written when one is supplied.
"""

import getpass
import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Customer, StaffRole

PASSWORD_ENV_VAR = "METRODRIP_CONSOLE_PASSWORD"


class Command(BaseCommand):
    help = "Create or update a merchant / administrator console account."

    def add_arguments(self, parser):
        parser.add_argument(
            "--role",
            required=True,
            choices=[StaffRole.MERCHANT.value, StaffRole.ADMINISTRATOR.value],
            help="Which console this account may enter.",
        )
        parser.add_argument("--email", required=True, help="Login email (the username field).")
        parser.add_argument(
            "--name", default="", help="Display name. Defaults to the email local part."
        )
        parser.add_argument(
            "--password",
            help=f"Password. Falls back to ${PASSWORD_ENV_VAR}, then an interactive prompt.",
        )

    def handle(self, *args, **options):
        email = Customer.objects.normalize_email(options["email"].strip().lower())
        role = StaffRole(options["role"])
        name = options["name"].strip() or email.split("@", 1)[0]

        account = Customer.objects.filter(email=email).first()
        password = self._resolve_password(options["password"], required=account is None)

        if password is not None:
            self._validate_password(password, email, name)

        with transaction.atomic():
            if account is None:
                account = Customer.objects.create_user(
                    email=email, password=password, name=name, role=role, is_staff=True
                )
                action = "Created"
            else:
                if account.is_superuser:
                    # A superuser already reaches both consoles; narrowing its
                    # role would misrepresent that without actually restricting
                    # it. Refuse rather than write a misleading row.
                    raise CommandError(
                        f"{email} is a superuser, which reaches every console. "
                        "Remove superuser status first if you want to scope it."
                    )
                account.role = role
                account.is_staff = True
                account.is_active = True
                if password is not None:
                    account.set_password(password)
                account.save()
                action = "Updated"

        self.stdout.write(
            self.style.SUCCESS(
                f"{action} {email} as {role.label} (staff, not superuser). "
                f"Console: /{'admin' if role == StaffRole.ADMINISTRATOR else 'merchant'}/"
            )
        )
        self.stdout.write(
            "Run `python manage.py sync_console_roles` so the account picks up "
            "its group permissions, or the console will be empty."
        )

    def _resolve_password(self, supplied, required):
        """--password, then the env var, then a prompt. None means 'leave unchanged'."""
        if supplied:
            return supplied
        from_env = os.environ.get(PASSWORD_ENV_VAR)
        if from_env:
            return from_env
        if not required:
            return None
        try:
            password = getpass.getpass("Password: ")
        except (EOFError, KeyboardInterrupt) as exc:
            # Non-interactive run with no password supplied — say which knobs
            # exist instead of dying with a bare traceback.
            raise CommandError(
                "A password is required for a new account. "
                f"Pass --password or set ${PASSWORD_ENV_VAR}."
            ) from exc
        if not password:
            raise CommandError("A password is required for a new account.")
        return password

    def _validate_password(self, password, email, name):
        """Apply AUTH_PASSWORD_VALIDATORS.

        Console accounts are the highest-value credentials in the system, so they
        are held to the same policy as a shopper's rather than being waved
        through because a management command created them.
        """
        probe = Customer(email=email, name=name)
        try:
            validate_password(password, probe)
        except ValidationError as exc:
            raise CommandError("Password rejected:\n  " + "\n  ".join(exc.messages)) from exc
