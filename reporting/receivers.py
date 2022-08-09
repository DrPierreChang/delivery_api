from __future__ import unicode_literals

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from base.models import Member
from driver.utils import WorkStatus
from merchant.models import Hub, Merchant, SkillSet, SubBranding
from notification.models import MerchantMessageTemplate
from notification.push_messages.utils import send_on_event_data_notifications
from reporting.model_mapping import serializer_map
from reporting.models import Event, ExportReportInstance
from reporting.signals import create_event, trigger_object_correlated_operations, trigger_object_post_processing
from tasks.celery_tasks import generate_driver_path, notify_customer_delayed
from tasks.mixins.order_status import OrderStatus
from tasks.models import ConcatenatedOrder, Order
from tasks.models.terminate_code import TerminateCode


@receiver(trigger_object_post_processing)
def trigger_order_status_events(event, **kwargs):
    if event.event != Event.CHANGED or event.field != 'status' or not type(event.object) == Order:
        return

    new_value = event.new_value
    order = event.object
    order.set_update_time()

    if event.initiator and event.initiator.is_driver:
        order.set_actual_device()

    if new_value in [OrderStatus.IN_PROGRESS, OrderStatus.PICK_UP]:
        order.on_start_statuses(change_time=event.happened_at, to_status=new_value)
        order.save()

    if new_value == OrderStatus.PICK_UP:
        order.notify_pickup()
    elif new_value == OrderStatus.IN_PROGRESS:
        if not (order.merchant.enable_concatenated_orders and order.is_concatenated_child):
            notify_customer_delayed(order)
    elif new_value in [OrderStatus.DELIVERED, OrderStatus.FAILED]:
        order.end_order()
        generate_driver_path(order)


@receiver(trigger_object_post_processing)
def trigger_concatenated_order_status_events(event, **kwargs):
    if event.event != Event.CHANGED or event.field != 'status' or not type(event.object) == ConcatenatedOrder:
        return
    if not event.object.merchant.enable_concatenated_orders:
        return

    new_value = event.new_value
    order = event.object

    if event.initiator and event.initiator.is_driver:
        order.set_actual_device()

    if new_value in [OrderStatus.IN_PROGRESS, OrderStatus.PICK_UP]:
        order.on_start_statuses(change_time=event.happened_at, to_status=new_value)
        order.save()

    if new_value == OrderStatus.IN_PROGRESS:
        notify_customer_delayed(order)
    elif new_value in [OrderStatus.DELIVERED, OrderStatus.FAILED]:
        order.end_order()
        generate_driver_path(order)


@receiver(trigger_object_correlated_operations)
def trigger_order_termination(event, **kwargs):
    if type(event.object) not in [Order, ConcatenatedOrder]:
        return
    if event.event != Event.MODEL_CHANGED:
        return

    order = event.object
    if order.concatenated_order_id is not None and order.status == order.concatenated_order.status:
        return

    dump = event.obj_dump
    old_status = dump.get('old_values', {}).get('status')
    new_status = dump.get('new_values', {}).get('status')
    if new_status == OrderStatus.FAILED and old_status == OrderStatus.IN_PROGRESS:
        notify_customer_delayed(order, template_type=MerchantMessageTemplate.CUSTOMER_JOB_TERMINATED)


@receiver(post_save, sender=Event)
def inactive_driver(sender, instance, created, *args, **kwargs):
    driver = instance.object
    DeltaSerializer = serializer_map.get_for(Order)

    def _create_event(order, old_dict):
        new_dict = DeltaSerializer(order).data
        create_event(old_dict, new_dict, initiator=instance.initiator, instance=order, sender=sender,
                     track_change_event=DeltaSerializer.Meta.track_change_event)

    if all([
        instance.field == 'is_active',
        instance.new_value == 'False',
        instance.content_type_id == ContentType.objects.get_for_model(Member).id,
    ]):
        orders = Order.objects.filter(driver=driver, status__in=OrderStatus.status_groups.UNFINISHED)\
            .exclude(status=OrderStatus.NOT_ASSIGNED)
        with transaction.atomic():
            for order in orders:
                old_dict = DeltaSerializer(order).data
                if order.status in [OrderStatus.IN_PROGRESS, OrderStatus.PICK_UP]:
                    order.status = OrderStatus.FAILED
                elif order.status == OrderStatus.ASSIGNED:
                    order.status = OrderStatus.NOT_ASSIGNED
                    order.driver = None
                elif order.status == OrderStatus.WAY_BACK:
                    order.status = OrderStatus.DELIVERED
                order.save()
                _create_event(order, old_dict)
            # Logout and set offline
            driver.work_status = WorkStatus.NOT_WORKING
            driver.user_auth_tokens.all().delete()
            driver.save()


@receiver(pre_delete, sender=ExportReportInstance)
def report_file_delete(sender, instance, **kwargs):
    instance.file.delete(False)


@receiver(post_save, sender=Event)
def send_event_notification(sender, instance, created, *args, **kwargs):
    trackable_models = {Hub, Merchant, SubBranding, TerminateCode, SkillSet}
    track_for_changes_only = {Merchant, }

    obj_model = type(instance.object) if instance.object_id else instance.content_type.model_class()
    merchant = instance.object if obj_model == Merchant else instance.merchant

    if obj_model in trackable_models and instance.event == Event.MODEL_CHANGED:
        obj_preview = {
            'id': instance.object_id,
            'model': obj_model.__name__
        }
        new_values = instance.obj_dump.get('new_values', {})
        if filter(lambda f: f not in getattr(obj_model, 'untracked_for_events', ()), new_values):
            send_on_event_data_notifications(merchant, obj_preview, instance.event)

    elif obj_model in (trackable_models - track_for_changes_only) and instance.event in (Event.CREATED, Event.DELETED):
        obj_preview = {
            'id': instance.object_id or instance.obj_dump.get('id'),
            'model': obj_model.__name__
        }
        send_on_event_data_notifications(merchant, obj_preview, instance.event)
