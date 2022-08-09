import copy
from datetime import timedelta

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

import dateutil

from merchant_extension.models import ResultChecklist
from reporting.models import Event
from reporting.signals import event_created, trigger_object_correlated_operations
from tasks.push_notification.push_messages.event_composers import OrderCargoesChangedMessage, OrderChangedMessage

from ..models import ConcatenatedOrder, Order
from ..push_notification.push_messages.order_change_status_composers import AvailableMessage, NotAvailableMessage
from .concatenated_order import co_auto_processing


def remove_insignificant_differences(new_dict, old_dict):
    """
    Removes fields with meaningless changes

    Example:
    old_dict = {
        "completion_comment":null,
        "deliver_before":"2020-09-21T22:25:26.298000+10:00",
    },
    new_dict= {
        "completion_comment":"",
        "deliver_before":"2020-09-21T22:25:26+10:00",
    }

    Such a field change occurs if a job created via api is saved in the admin page.
    """
    empty_values = ('', None)
    delta = timedelta(seconds=1)

    keys = set(new_dict.keys()) & set(old_dict.keys())
    for key in keys:
        if new_dict[key] in empty_values and old_dict[key] in empty_values:
            del new_dict[key]
            del old_dict[key]
        elif isinstance(new_dict[key], str) and isinstance(old_dict[key], str):
            try:
                new_datetime = dateutil.parser.parse(new_dict[key])
                old_datetime = dateutil.parser.parse(old_dict[key])
                if abs(new_datetime - old_datetime) < delta:
                    del new_dict[key]
                    del old_dict[key]
            except ValueError:
                pass


@receiver(event_created)
def check_order_update(sender, event, *args, **kwargs):
    untracked_fields = {'deadline_passed', 'status', 'driver', 'cargoes'}

    if sender == co_auto_processing:
        return

    if not (type(event.object) == Order
            and event.event == Event.MODEL_CHANGED
            and event.object.status == Order.ASSIGNED):
        return

    order = event.object
    driver = order.driver

    if driver is None:
        return
    if event.initiator and event.initiator.id == driver.id:
        return

    dump = copy.deepcopy(event.obj_dump)
    if 'new_values' in dump and 'old_values' in dump:
        remove_insignificant_differences(dump['new_values'], dump['old_values'])

    new_values = dump.get('new_values', [])
    if (set(new_values) & untracked_fields) or new_values.get('deadline_notified', False):
        return

    if not new_values:
        return

    driver.send_versioned_push(OrderChangedMessage(order=order))


def notify_drivers_of_availability(order, initiator, exclude_driver_ids=None):
    exclude_driver_ids = exclude_driver_ids or []
    if initiator and initiator.is_driver:
        exclude_driver_ids.append(initiator.id)

    drivers = order.get_available_drivers().exclude(id__in=exclude_driver_ids)

    for driver in drivers:
        msg = AvailableMessage(driver=driver, order=order, initiator=initiator)
        driver.send_versioned_push(msg)


@receiver(trigger_object_correlated_operations)
def check_order_available_for_driver(event, **kwargs):
    if type(event.object) != Order:
        return

    exclude_driver_ids = []

    if event.event == Event.CREATED:
        if event.object.status != Order.NOT_ASSIGNED:
            return
    elif event.event == Event.MODEL_CHANGED:
        if event.obj_dump['new_values'].get('status') != Order.NOT_ASSIGNED:
            return
        else:
            driver_id = event.obj_dump['old_values'].get('driver')
            if driver_id:
                exclude_driver_ids.append(driver_id)
    else:
        return

    order = event.object

    if order.deliver_before > timezone.now() + timedelta(days=7):
        return
    if not order.merchant.notify_of_not_assigned_orders:
        return

    if not order.skill_sets.exists():
        return
    required_skill_sets_ids = order.merchant.required_skill_sets_for_notify_orders.values_list('id', flat=True)
    if required_skill_sets_ids.exists() and not order.skill_sets.filter(id__in=required_skill_sets_ids).exists():
        return

    notify_drivers_of_availability(order, event.initiator, exclude_driver_ids)


def notify_drivers_of_unavailability(order, initiator, exclude_driver_ids=None):
    exclude_driver_ids = exclude_driver_ids or []
    if initiator and initiator.is_driver:
        exclude_driver_ids.append(initiator.id)

    drivers = order.get_available_drivers().exclude(id__in=exclude_driver_ids)

    for driver in drivers:
        msg = NotAvailableMessage(driver=driver, order=order, initiator=initiator)
        driver.send_versioned_push(msg, background=True)


@receiver(trigger_object_correlated_operations)
def check_order_unavailable_for_driver(event, **kwargs):
    if type(event.object) != Order:
        return

    if event.event != Event.MODEL_CHANGED:
        return
    if event.obj_dump['old_values'].get('status') != Order.NOT_ASSIGNED:
        return

    order = event.object
    if not order.merchant.in_app_jobs_assignment:
        return
    if not (order.deliver_before < timezone.now() + timedelta(days=settings.UNALLOCATED_ORDER_INTERVAL)):
        return

    notify_drivers_of_unavailability(order, event.initiator)


@receiver(post_save, sender=Event)
def check_order_skids_update(sender, instance, created, *args, **kwargs):
    if not type(instance.object) == Order:
        return
    if not (instance.event == Event.MODEL_CHANGED and instance.object.status in (Order.ASSIGNED, Order.IN_PROGRESS)):
        return

    order = instance.object
    driver = order.driver

    if driver is None:
        return
    if instance.initiator and instance.initiator.id == driver.id:
        return

    new_values = instance.obj_dump.get('new_values', [])
    if 'cargoes' not in new_values:
        return

    driver.send_versioned_push(OrderCargoesChangedMessage(order=order))


def create_driver_checklist(sender, instance, created, *args, **kwargs):
    checklist_id = instance.merchant.checklist_id
    if created and checklist_id:
        driver_checklist = ResultChecklist.objects.create(checklist_id=checklist_id)
        instance.driver_checklist = driver_checklist
        instance.save(update_fields=('driver_checklist',))


post_save.connect(create_driver_checklist, sender=Order)
post_save.connect(create_driver_checklist, sender=ConcatenatedOrder)

__all__ = ['check_order_update', 'check_order_available_for_driver', 'check_order_unavailable_for_driver',
           'check_order_skids_update', 'create_driver_checklist']
