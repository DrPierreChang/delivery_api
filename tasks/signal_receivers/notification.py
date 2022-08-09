from __future__ import absolute_import, unicode_literals

from datetime import timedelta
from operator import itemgetter
from typing import List

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from rest_framework.fields import DateTimeField

from base.models import Member
from base.signals import post_bulk_create
from merchant.models import Merchant
from notification.push_messages.event_composers import EventMessage
from reporting.models import Event
from reporting.signals import trigger_object_correlated_operations
from tasks.mixins.order_status import OrderStatus
from tasks.models import ConcatenatedOrder, Order
from tasks.push_notification.push_messages.event_composers import OrderDeletedMessage
from tasks.push_notification.utils import (
    BulkAssignEventsHandler,
    BulkReassignEventsHandler,
    BulkUnassignEventsHandler,
    create_and_send_job_status_notification,
)


@receiver(trigger_object_correlated_operations)
def send_job_status_notification(event, *args, **kwargs):
    order = event.object
    if event.event == Event.MODEL_CHANGED and isinstance(order, Order):
        if order.concatenated_order_id and order.merchant.enable_concatenated_orders:
            return

        old_values, new_values = itemgetter('old_values', 'new_values')(event.obj_dump)
        create_and_send_job_status_notification(order, new_values, old_values, event)


@receiver(post_bulk_create, sender=Event)
def send_job_status_notification_for_created_with_bulk(sender, instances, *args, **kwargs):
    orders = Order.aggregated_objects.filter(deleted=False, status=OrderStatus.ASSIGNED)
    ctypes = ContentType.objects.get_for_models(Order, ConcatenatedOrder, for_concrete_models=False).values()
    events = Event.objects.filter(
        id__in=[it.id for it in instances],
        content_type__in=ctypes,
        event=Event.CREATED,
        object_id__in=orders
    ).prefetch_related('object__driver')
    BulkAssignEventsHandler().send_notifications(events)


@receiver(post_bulk_create, sender=Event)
def send_job_status_notification_for_bulk_status_change(sender, instances: List[Event], *args, **kwargs):
    object_ids = []
    for it in instances:
        if not it.obj_dump:
            continue
        old_val = it.obj_dump.get('old_values', {}).get('status')
        new_val = it.obj_dump.get('new_values', {}).get('status')
        if old_val in (OrderStatus.NOT_ASSIGNED, OrderStatus.ASSIGNED) \
                and new_val in (OrderStatus.NOT_ASSIGNED, OrderStatus.ASSIGNED) \
                and old_val != new_val:
            object_ids.append(it.object_id)

    base_orders_qs = Order.aggregated_objects.all().exclude_nested_orders()
    base_orders_qs = base_orders_qs.filter(id__in=object_ids).values_list('id', flat=True)
    assigned_orders = base_orders_qs.filter(status=OrderStatus.ASSIGNED)
    unassigned_orders = base_orders_qs.filter(status=OrderStatus.NOT_ASSIGNED)

    ctypes = ContentType.objects.get_for_models(Order, ConcatenatedOrder, for_concrete_models=False).values()
    base_events_qs = Event.objects.filter(
        id__in=[it.id for it in instances], event=Event.MODEL_CHANGED, content_type__in=ctypes
    ).prefetch_related('object__driver')
    assigned_events = base_events_qs.filter(object_id__in=assigned_orders)
    unassigned_events = base_events_qs.filter(object_id__in=unassigned_orders)

    background_notification = kwargs.get('background_notification', False)

    BulkAssignEventsHandler(background_notification).send_notifications(assigned_events)
    BulkUnassignEventsHandler(background_notification).send_notifications(unassigned_events)


@receiver(post_bulk_create, sender=Event)
def send_job_status_notification_for_bulk_reassign(sender, instances, *args, **kwargs):
    object_ids = []
    for it in instances:
        if not it.obj_dump:
            continue
        old_val, new_val = it.obj_dump.get('old_values', {}).get('driver'), \
            it.obj_dump.get('new_values', {}).get('driver')
        if old_val is not None and new_val is not None and old_val != new_val:
            object_ids.append(it.object_id)
    orders_qs = Order.aggregated_objects.filter(id__in=object_ids).values_list('id', flat=True)
    ctypes = ContentType.objects.get_for_models(Order, ConcatenatedOrder, for_concrete_models=False).values()
    events_qs = Event.objects.filter(
        id__in=[it.id for it in instances], event=Event.MODEL_CHANGED, content_type__in=ctypes
    ).prefetch_related('object__driver')
    events = events_qs.filter(object_id__in=orders_qs)

    background_notification = kwargs.get('background_notification', False)

    BulkReassignEventsHandler(background_notification).send_notifications(events)


@receiver(post_save, sender=Event)
def notification_on_order_deletion(sender, instance, *args, **kwargs):
    deleted_through_api = instance.event == Event.DELETED \
                          and instance.content_type == ContentType.objects.get_for_model(Order)
    if not deleted_through_api:
        return

    if instance.obj_dump.get('driver'):
        driver = Member.objects.filter(id=instance.obj_dump['driver']).first()
        msg = OrderDeletedMessage(order=instance.obj_dump, driver=driver)
        driver.send_versioned_push(msg)

    deliver_before = instance.obj_dump.get('deliver_before')
    deliver_before = deliver_before and DateTimeField(allow_null=True).to_internal_value(deliver_before)
    is_unallocated = (
        deliver_before and deliver_before < timezone.now() + timedelta(days=settings.UNALLOCATED_ORDER_INTERVAL)
        and instance.obj_dump.get('status') == OrderStatus.NOT_ASSIGNED
    )

    if is_unallocated:
        merchant = Merchant.objects.get(id=instance.obj_dump.get('merchant'))
        drivers = Member.drivers.all().filter(merchant_id=merchant.id)
        order_preview = {
            'server_entity_id': instance.obj_dump.get('id'),
            'model': Order.__name__
        }

        if merchant.enable_skill_sets:
            for skill_set_id in instance.obj_dump.get('skill_sets', []):
                drivers = drivers.filter(skill_sets__id=skill_set_id)

        for driver in drivers:
            msg = EventMessage(order_preview, EventMessage.DELETED)
            driver.send_versioned_push(msg, background=True)


__all__ = ['notification_on_order_deletion', 'send_job_status_notification',
           'send_job_status_notification_for_created_with_bulk']
