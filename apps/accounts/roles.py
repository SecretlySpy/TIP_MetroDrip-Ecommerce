"""Back-office role vocabulary.

Deliberately model-free. `config.consoles` needs these values to decide who may
enter which console, and it is imported while the admin app is still starting —
importing `apps.accounts.models` there would raise AppRegistryNotReady. A
`TextChoices` subclass registers nothing with the app registry, so this module is
safe to import at any point.

`is_staff` answers "may this account reach a back-office console at all"; `role`
answers "which one". Both are required — see `Customer.console` — so clearing
`is_staff` revokes access without having to rewrite the role.
"""

from django.db import models


class StaffRole(models.TextChoices):
    """Which console, if any, an account belongs to."""

    CUSTOMER = "customer", "Customer (storefront only)"
    MERCHANT = "merchant", "Merchant / Seller"
    ADMINISTRATOR = "administrator", "Administrator"


#: Roles that grant a back-office console. A role outside this set means the
#: account is a shopper, whatever `is_staff` says.
CONSOLE_ROLES = frozenset({StaffRole.MERCHANT, StaffRole.ADMINISTRATOR})
