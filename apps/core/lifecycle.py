"""Cross-schema deletion policies use guards and a transactional event queue.

Collection has no remote side effects. Guards run before deletion; cleanup
intent commits in the same schema/transaction as the source deletion. Cleanup
is replay-safe and retried by the scheduler. No distributed atomicity is claimed.
"""

import logging

from django.apps import apps
from django.db import models, router, transaction
from django.db.models.deletion import ProtectedError
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)


def _collect(collector, field, sub_objs, using, operation):
    target_db = router.db_for_write(field.model)
    query = sub_objs.using(target_db)
    if operation == "protect":
        if query.exists():
            raise ProtectedError("Referenced audit/history records prevent deletion.", query)
        return
    for source in collector.data.get(field.remote_field.model, ()):
        action = (field.model._meta.label_lower, field.name, source.pk, operation)
        actions = getattr(source, "_service_delete_actions", [])
        if action not in actions:
            actions.append(action)
        source._service_delete_actions = actions


def service_cascade(collector, field, sub_objs, using):
    _collect(collector, field, sub_objs, using, "delete")


def service_set_null(collector, field, sub_objs, using):
    _collect(collector, field, sub_objs, using, "set_null")


def service_protect(collector, field, sub_objs, using):
    _collect(collector, field, sub_objs, using, "protect")


# Prevent Django from evaluating sub_objs on the source database first.
service_cascade.lazy_sub_objs = True
service_set_null.lazy_sub_objs = True
service_protect.lazy_sub_objs = True


@receiver(pre_delete, dispatch_uid="metrodrip.service_delete_intent")
def record_cleanup(sender, instance, using, **kwargs):
    from .models import ServiceEvent

    actions = getattr(instance, "_service_delete_actions", ())
    for model, field, pk, operation in actions:
        ServiceEvent.objects.using(using).create(
            target_model=model, target_field=field, reference_id=pk, operation=operation
        )
    if actions:
        transaction.on_commit(lambda: drain_service_events(using), using=using, robust=True)


def drain_service_events(using, limit=100):
    from .models import ServiceEvent

    count = 0
    # The source event row remains locked until its idempotent target action
    # has completed. A process crash after target commit simply replays it.
    for event_id in list(ServiceEvent.objects.using(using).filter(completed_at=None)
                         .values_list("pk", flat=True)[:limit]):
        with transaction.atomic(using=using):
            event = ServiceEvent.objects.using(using).select_for_update().get(pk=event_id)
            if event.completed_at:
                continue
            try:
                target = apps.get_model(event.target_model)
                field = target._meta.get_field(event.target_field)
                if field.remote_field.on_delete not in (service_cascade, service_set_null):
                    raise ValueError("Unsupported service lifecycle target")
                target_db = router.db_for_write(target)
                query = target.objects.using(target_db).filter(
                    **{field.attname: event.reference_id}
                )
                if event.operation == "delete":
                    query.delete()
                elif event.operation == "set_null" and field.null:
                    query.update(**{field.attname: None})
                else:
                    raise ValueError("Unsupported service lifecycle operation")
            except Exception as error:
                event.last_error = type(error).__name__
                logger.exception("Service cleanup event %s/%s failed", using, event.pk)
            else:
                event.completed_at = timezone.now()
                event.last_error = ""
                count += 1
            event.attempts += 1
            event.save(using=using)
    return count
