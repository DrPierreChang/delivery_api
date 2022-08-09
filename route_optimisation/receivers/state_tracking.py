from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.dispatch import receiver

from merchant.models import Merchant
from reporting.models import Event
from route_optimisation.celery_tasks import track_state_change
from route_optimisation.models import OptimisationTask, RouteOptimisation
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order
from webhooks.celery_tasks import send_external_optimisation_event


@receiver(post_save, sender=Event)
def track_optimisation_route_state(sender, instance, *args, **kwargs):
    statuses = (OrderStatus.PICK_UP, OrderStatus.PICKED_UP,
                OrderStatus.IN_PROGRESS, OrderStatus.WAY_BACK,
                OrderStatus.DELIVERED, OrderStatus.FAILED, )
    if instance.event != Event.CHANGED \
            or instance.field != 'status' \
            or instance.new_value not in statuses \
            or not type(instance.object) == Order:
        return
    if instance.merchant.route_optimization == Merchant.ROUTE_OPTIMIZATION_DISABLED:
        return
    track_state_change.delay(instance.object_id)


@receiver(post_save, sender=OptimisationTask)
def track_optimisation_task_status_change(instance, created, update_fields, *args, **kwargs):
    if created:
        return

    if 'status' in update_fields and instance.status == OptimisationTask.COMPLETED:
        send_external_optimisation_event.delay(optimisation_id=instance.optimisation_id,
                                               updated_at=instance.modified,
                                               topic='optimisation.completed')


@receiver(post_save, sender=Event)
def track_optimisation_delete(sender, instance, *args, **kwargs):
    ro_ct = ContentType.objects.get_for_model(RouteOptimisation, for_concrete_model=False)
    is_ro_deleted = (instance.content_type == ro_ct) and (instance.event == Event.DELETED)
    if not is_ro_deleted:
        return

    send_external_optimisation_event.delay(optimisation_id=instance.obj_dump['id'],
                                           updated_at=instance.happened_at,
                                           topic='optimisation.deleted')
