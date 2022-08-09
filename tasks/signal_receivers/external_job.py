from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.dispatch import receiver

from merchant_extension.models import Checklist, ResultChecklist
from notification.utils import filter_dict
from reporting.models import Event
from reporting.signals import trigger_object_correlated_operations
from tasks.models import SKID, ConcatenatedOrder, Order
from webhooks.celery_tasks import (
    send_external_concatenated_order_event,
    send_external_daily_checklist_event,
    send_external_job_checklist_confirmation_event,
    send_external_job_checklist_event,
    send_external_job_event,
)


@receiver(trigger_object_correlated_operations)
def check_job_status_changed(sender, event, **kwargs):
    tracked_fields = ('status', 'is_confirmed_by_customer')
    # The status 'delivered' with 'is_confirmed_by_customer' enabled is considered the status 'confirmed'.

    is_order_changed_or_created = type(event.object) == Order and \
                                  event.event in (Event.MODEL_CHANGED, Event.CREATED)

    if not is_order_changed_or_created:
        return

    order_is_created = event.event == Event.CREATED
    order = event.object

    obj_dump = event.obj_dump
    new_values = filter_dict(obj_dump.get('new_values', {}), tracked_fields) or None
    if new_values or order_is_created:
        old_values = filter_dict(obj_dump.get('old_values', {}), tracked_fields) or None
        send_external_job_event.delay(order_id=order.order_id, new_values=new_values,
                                      old_values=old_values, updated_at=event.happened_at,
                                      event_type=event.event, topic='job.status_changed')


@receiver(post_save, sender=Event)
def check_job_barcodes_scanned(sender, instance, created, *args, **kwargs):
    tracked_fields = ('barcodes',)
    order_changed = type(instance.object) == Order and instance.event == Event.MODEL_CHANGED
    initiator_is_driver = instance.initiator and instance.initiator.is_driver

    if not (order_changed and initiator_is_driver):
        return

    obj_dump = instance.obj_dump
    new_values = filter_dict(obj_dump.get('new_values', {}), tracked_fields) or None

    if not new_values:
        return

    scanned_at_the_warehouse = all(code['scanned_at_the_warehouse'] for code in new_values['barcodes'])
    scanned_upon_delivery = all(code['scanned_upon_delivery'] for code in new_values['barcodes'])
    no_one_scanned_upon_delivery = not any(code['scanned_upon_delivery'] for code in new_values['barcodes'])
    topic = 'job.barcodes_scanned_upon_delivery' if scanned_upon_delivery else 'job.barcodes_scanned'
    if scanned_upon_delivery or (scanned_at_the_warehouse and no_one_scanned_upon_delivery):
        old_values = filter_dict(obj_dump.get('old_values', {}), tracked_fields) or None
        send_external_job_event.delay(
            order_id=instance.object.order_id, new_values=new_values,
            old_values=old_values, updated_at=instance.happened_at,
            event_type=instance.event, topic=topic
        )


@receiver(trigger_object_correlated_operations)
def check_job_deleted(sender, event, **kwargs):
    order_ct = ContentType.objects.get_for_model(Order, for_concrete_model=False)
    is_order_deleted = (event.content_type == order_ct) and (event.event == Event.DELETED)
    if not is_order_deleted:
        return

    send_external_job_event.delay(order_id=event.obj_dump['order_id'], new_values=None, old_values=None,
                                  updated_at=event.happened_at, event_type=event.event, topic='job.deleted')


@receiver(post_save, sender=Event)
def check_terminate_passed(sender, instance, created, *args, **kwargs):
    tracked_fields = ('completion_codes', 'completion_comment')

    if not (type(instance.object) == Order and instance.event == Event.MODEL_CHANGED):
        return

    order = instance.object
    obj_dump = instance.obj_dump
    new_values = filter_dict(obj_dump.get('new_values', {}), tracked_fields) or None

    if new_values:
        old_values = filter_dict(obj_dump.get('old_values', {}), tracked_fields) or None
        send_external_job_event.delay(
            order_id=order.order_id,
            new_values=new_values,
            old_values=old_values,
            updated_at=instance.happened_at,
            event_type=instance.event,
            topic='job.completion_codes_accepted',
        )


@receiver(post_save, sender=Event)
def check_uploaded_confirmation_document(sender, instance, created, *args, **kwargs):
    tracked_fields = ('order_confirmation_documents',)

    if not (isinstance(instance.object, Order) and instance.event == Event.MODEL_CHANGED):
        return

    order = instance.object
    obj_dump = instance.obj_dump
    new_values = filter_dict(obj_dump.get('new_values', {}), tracked_fields) or None

    if new_values:
        old_values = filter_dict(obj_dump.get('old_values', {}), tracked_fields) or None
        send_external_job_event.delay(
            order_id=order.order_id,
            new_values=new_values,
            old_values=old_values,
            updated_at=instance.happened_at,
            event_type=instance.event,
            topic='job.uploaded_confirmation_document',
        )


@receiver(post_save, sender=Event)
def check_sod_checklist_passed(sender, instance, created, *args, **kwargs):
    is_checklist_passed = isinstance(instance.object, ResultChecklist) \
                          and instance.event == Event.MODEL_CHANGED \
                          and instance.object.checklist.checklist_type == Checklist.START_OF_DAY \
                          and instance.object.is_passed

    if not is_checklist_passed:
        return

    result_checklist = instance.object

    send_external_daily_checklist_event.delay(
        result_checklist_id=result_checklist.id,
        updated_at=instance.happened_at,
        topic='checklist.start_of_day_checklist_passed',
    )


@receiver(post_save, sender=Event)
def check_eod_checklist_passed(sender, instance, created, *args, **kwargs):
    is_checklist_passed = isinstance(instance.object, ResultChecklist) \
                          and instance.event == Event.MODEL_CHANGED \
                          and instance.object.checklist.checklist_type == Checklist.END_OF_DAY \
                          and instance.object.is_passed

    if not is_checklist_passed:
        return

    result_checklist = instance.object

    send_external_daily_checklist_event.delay(
        result_checklist_id=result_checklist.id,
        updated_at=instance.happened_at,
        topic='checklist.end_of_day_checklist_passed',
    )


@receiver(post_save, sender=Event)
def check_job_checklist_passed(sender, instance, created, *args, **kwargs):
    is_checklist_passed = isinstance(instance.object, ResultChecklist) \
                          and instance.event == Event.MODEL_CHANGED \
                          and instance.object.checklist.checklist_type == Checklist.JOB \
                          and instance.object.is_passed

    if not is_checklist_passed:
        return

    result_checklist = instance.object

    send_external_job_checklist_event.delay(
        result_checklist_id=result_checklist.id,
        updated_at=instance.happened_at,
        topic='checklist.job_checklist_passed',
    )
    send_external_job_checklist_confirmation_event.delay(
        result_checklist_id=result_checklist.id,
        updated_at=instance.happened_at,
        topic='checklist.job_checklist_confirmation',
    )


def _prepared_skids_for_webhook(skids):
    for skid in skids:
        if skid['driver_changes'] == SKID.DELETED:
            for field in list(skid.keys()):
                if field not in ['id', 'driver_changes', 'original_skid']:
                    del skid[field]


@receiver(post_save, sender=Event)
def check_cargoes_changed(sender, instance, created, *args, **kwargs):
    tracked_fields = ('cargoes',)
    order_changed = type(instance.object) == Order and instance.event == Event.MODEL_CHANGED
    initiator_is_driver = instance.initiator and instance.initiator.is_driver

    if not (order_changed and initiator_is_driver):
        return

    obj_dump = instance.obj_dump
    new_values = filter_dict(obj_dump.get('new_values', {}), tracked_fields) or None

    if new_values:
        topic = 'job.cargoes_changed'
        old_values = filter_dict(obj_dump.get('old_values', {}), tracked_fields) or None

        _prepared_skids_for_webhook(new_values['cargoes']['skids'])
        _prepared_skids_for_webhook(old_values['cargoes']['skids'])

        send_external_job_event.delay(
            order_id=instance.object.order_id, new_values=new_values,
            old_values=old_values, updated_at=instance.happened_at,
            event_type=instance.event, topic=topic
        )


@receiver(post_save, sender=Event)
def check_concatenated_order_created(sender, instance, created, *args, **kwargs):
    is_concatenated_order_created = isinstance(instance.object, ConcatenatedOrder) and instance.event == Event.CREATED
    if not is_concatenated_order_created:
        return
    concatenated_order = instance.object

    send_external_concatenated_order_event.delay(
        concatenated_order_id=concatenated_order.id,
        updated_at=instance.happened_at,
        topic='concatenated_order.created',
    )


__all__ = [
    'check_job_status_changed', 'check_job_barcodes_scanned', 'check_terminate_passed',
    'check_uploaded_confirmation_document', 'check_sod_checklist_passed', 'check_job_checklist_passed',
    'check_cargoes_changed', 'check_concatenated_order_created',
]
