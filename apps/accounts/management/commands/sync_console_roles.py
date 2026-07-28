"""Keep the Merchants and Administrators groups in step with the consoles.

Splitting the back office in two (ADR-F-001) creates a second gate behind the
role check: Django still asks `user.has_perm(...)` per model, so a brand-new
merchant account with the right role but no permissions signs in successfully
and sees a completely empty console. That looks like a bug and gets "fixed" by
someone ticking *superuser*, which erases the separation entirely.

This command closes that gap. It derives each group's permission set from the
console registries themselves rather than from a hand-written list, so moving a
model between consoles — a one-word change in an `admin.register` call — is
picked up on the next run instead of quietly leaving a stale grant behind.

Idempotent. Safe to re-run after every migration and after any registration
change:

    python manage.py sync_console_roles
    python manage.py sync_console_roles --dry-run     # report, change nothing
    python manage.py sync_console_roles --no-assign   # groups only, no membership
"""

from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Customer, StaffRole
from config.consoles import merchant_site

#: Group name per console role. These are the groups the command owns; any other
#: group is left completely alone.
GROUP_NAMES = {
    StaffRole.ADMINISTRATOR: "Administrators",
    StaffRole.MERCHANT: "Merchants",
}


class _PermissiveUser:
    """A user for whom every permission check passes.

    Used only to probe a ModelAdmin. `ModelAdmin.has_add_permission` and friends
    ask `request.user.has_perm(...)`; answering yes means the probe reports what
    the *ModelAdmin* allows, with the permission layer taken out of the picture.
    A read-only admin such as `AuditTrailAdmin` overrides those methods to return
    False unconditionally, so it still probes as view-only — which is exactly the
    distinction the group grants need to respect.
    """

    is_active = True
    is_staff = True
    is_superuser = True
    is_authenticated = True
    is_anonymous = False
    pk = None
    id = None

    def has_perm(self, perm, obj=None):
        return True

    def has_perms(self, perms, obj=None):
        return True

    def has_module_perms(self, app_label):
        return True


class _ProbeRequest:
    """The smallest object a `has_*_permission` hook will accept."""

    def __init__(self):
        self.user = _PermissiveUser()
        self.method = "GET"
        self.GET = {}
        self.POST = {}


def allowed_actions(model_admin):
    """Return the permission verbs a ModelAdmin actually permits.

    `view` is unconditional: registering a model on a console is a statement that
    the console may look at it. The other three are asked of the ModelAdmin, so
    append-only ledgers (`StockMovement`), webhook-owned records (`Payment`), and
    the audit trail all come back view-only without being listed anywhere here.
    """
    probe = _ProbeRequest()
    actions = {"view"}
    if model_admin.has_add_permission(probe):
        actions.add("add")
    if model_admin.has_change_permission(probe):
        actions.add("change")
    if model_admin.has_delete_permission(probe):
        actions.add("delete")
    return actions


def permissions_for_site(site):
    """Resolve one console's registry to a concrete Permission queryset.

    Returns `(permissions, missing_codenames)`. A codename goes missing when the
    `post_migrate` hook that creates model permissions has not run for a freshly
    added model; reporting it beats raising, because the remaining grants are
    still correct and a later `migrate` fixes the rest.
    """
    wanted = []
    # `_registry` is the only mapping of model -> ModelAdmin a site exposes.
    # Deliberate: it is what makes "which console owns this model" a single fact
    # declared at the registration site instead of a duplicated list here.
    for model, model_admin in site._registry.items():
        content_type = ContentType.objects.get_for_model(model)
        for action in allowed_actions(model_admin):
            wanted.append((content_type.pk, f"{action}_{model._meta.model_name}"))

    found = Permission.objects.filter(
        content_type_id__in={ct for ct, _ in wanted},
        codename__in={codename for _, codename in wanted},
    ).select_related("content_type")
    # Filtering the two columns independently can over-match when two models
    # share a codename (e.g. `view_site`), so pair them back up exactly.
    by_pair = {(perm.content_type_id, perm.codename): perm for perm in found}
    permissions = [by_pair[pair] for pair in wanted if pair in by_pair]
    missing = sorted(
        {
            codename
            for content_type_id, codename in wanted
            if (content_type_id, codename) not in by_pair
        }
    )
    return permissions, missing


class Command(BaseCommand):
    help = "Sync the Merchants/Administrators groups with the console registries."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )
        parser.add_argument(
            "--no-assign",
            action="store_true",
            help="Sync group permissions but leave account memberships alone.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        # One transaction so a failure part-way through cannot leave one console
        # granted and the other not.
        with transaction.atomic():
            for role, site in (
                (StaffRole.ADMINISTRATOR, admin.site),
                (StaffRole.MERCHANT, merchant_site),
            ):
                self._sync_group(role, site, dry_run)

            if not options["no_assign"]:
                self._sync_memberships(dry_run)

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Dry run — nothing was written."))

    def _sync_group(self, role, site, dry_run):
        name = GROUP_NAMES[role]
        permissions, missing = permissions_for_site(site)

        group, created = Group.objects.get_or_create(name=name)
        before = set(group.permissions.values_list("pk", flat=True))
        after = {perm.pk for perm in permissions}

        if not dry_run and before != after:
            # `set()` is the whole point: a model that moved to the other console
            # loses its grant here, which a bare `add()` would never do.
            group.permissions.set(permissions)

        verb = "created" if created else "updated"
        self.stdout.write(
            f"{name}: {verb}, {len(after)} permission(s) "
            f"(+{len(after - before)} / -{len(before - after)})"
        )
        if missing:
            self.stdout.write(
                self.style.WARNING(
                    f"  {len(missing)} permission(s) do not exist yet — "
                    f"run migrate, then re-run this command: {', '.join(missing)}"
                )
            )

    def _sync_memberships(self, dry_run):
        """Put every staff account in its console's group, and only that one.

        Roles are mutually exclusive, so a merchant must not keep an
        Administrators membership from a previous role. Non-staff accounts are
        removed from both groups: their role field may still say "merchant", but
        without staff status they open nothing, and a dormant grant is the kind
        of thing that becomes live again by accident.
        """
        groups = {role: Group.objects.get(name=name) for role, name in GROUP_NAMES.items()}
        moved = 0

        for role, group in groups.items():
            should_belong = set(
                Customer.objects.filter(role=role, is_staff=True).values_list("pk", flat=True)
            )
            currently = set(group.user_set.values_list("pk", flat=True))

            to_add, to_remove = should_belong - currently, currently - should_belong
            if not dry_run:
                if to_add:
                    group.user_set.add(*Customer.objects.filter(pk__in=to_add))
                if to_remove:
                    group.user_set.remove(*Customer.objects.filter(pk__in=to_remove))
            moved += len(to_add) + len(to_remove)
            self.stdout.write(
                f"{group.name} membership: {len(should_belong)} account(s) "
                f"(+{len(to_add)} / -{len(to_remove)})"
            )

        if not moved:
            self.stdout.write("Memberships already correct.")
