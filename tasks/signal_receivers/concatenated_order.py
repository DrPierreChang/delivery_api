import copy
from datetime import datetime, timedelta

from django.contrib.admin import ModelAdmin
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from base.models import Member
from documents.models import OrderConfirmationDocument
from merchant_extension.models import ResultChecklist, ResultChecklistAnswer, ResultChecklistAnswerPhoto
from reporting.context_managers import track_fields_on_change
from reporting.model_mapping import serializer_map
from reporting.models import Event
from reporting.signals import create_event, event_created, trigger_object_post_processing
from reporting.utils.create import create_create_event
from reporting.utils.delete import create_delete_event

from ..models import (
    ConcatenatedOrder,
    Order,
    OrderConfirmationPhoto,
    OrderPickUpConfirmationPhoto,
    OrderPreConfirmationPhoto,
)
from ..push_notification.push_messages.event_composers import (
    ConcatenatedOrderGroupedMessage,
    ConcatenatedOrderUngroupedMessage,
    OrderAddedToConcatenatedMessage,
    OrderRemovedFromConcatenatedMessage,
)

# set this object as signal sender if event should be considered as a part of concatenated order auto-processing
# and no explicit event for concatenated order is required
co_auto_processing = object()


# Checks how the order status has changed, adds or removes an order from a concatenated order
@receiver(trigger_object_post_processing)
def check_order_update(sender, event, *args, **kwargs):
    order_ct = ContentType.objects.get_for_model(Order)
    if not event.content_type == order_ct:
        return

    if event.event == Event.DELETED:
        remove_order_from_concatenated_order(
            event.obj_dump.get('id'),
            event.obj_dump.get('concatenated_order'),
            happened_at=event.happened_at,
        )
        return
    elif event.event == Event.MODEL_CHANGED:
        changed_fields = set(event.obj_dump['new_values'].keys())
        tracked_fields = {'status', 'driver', 'deliver_before', 'deleted'}
        if not (changed_fields & tracked_fields):
            return
    elif event.event == Event.CREATED:
        pass
    else:
        return

    order = event.object

    if order.concatenated_order_id is not None:
        order = check_and_update_concatenated_order(
            order=order, sender=sender, event=event, happened_at=event.happened_at, *args, **kwargs,
        )

    if not order.merchant.enable_concatenated_orders:
        return

    can_be_grouped = order.status in [Order.NOT_ASSIGNED, Order.ASSIGNED] and not order.deleted
    if order.concatenated_order_id is None and can_be_grouped:
        check_and_create_concatenated_order(
            order=order, sender=sender, event=event, happened_at=event.happened_at, *args, **kwargs,
        )


def remove_order_from_concatenated_order(order_id, concatenated_order_id, happened_at):
    concatenated_order = concatenated_order_id and ConcatenatedOrder.objects.filter(id=concatenated_order_id).first()
    if concatenated_order is None:
        return

    with track_fields_on_change(concatenated_order, sender=co_auto_processing, happened_at=happened_at):
        if order_id is not None:
            Order.all_objects.filter(id=order_id).update(concatenated_order=None)
        concatenated_order.update_data()


def check_and_update_concatenated_order(order, event, happened_at, *args, **kwargs):
    tz = order.merchant.timezone
    concatenated_order = order.concatenated_order
    available_statuses = concatenated_order.get_available_statuses_for_concatenated(concatenated_order.status)

    invalid_status = order.status not in available_statuses
    invalid_driver = concatenated_order.driver_id != order.driver_id
    invalid_deliver_date = order.deliver_before.astimezone(tz).date() != concatenated_order.deliver_day

    if invalid_status or invalid_driver or invalid_deliver_date or order.deleted:
        # Removing an inappropriate order from a concatenated order
        with track_fields_on_change(order, sender=co_auto_processing, happened_at=happened_at):
            with track_fields_on_change(concatenated_order, sender=co_auto_processing, happened_at=happened_at):
                order.concatenated_order = None
                order.save()
                concatenated_order.update_data()

                initiator_is_driver = event.initiator is not None and event.initiator.is_driver
                driver_id = event.obj_dump['old_values'].get('driver', order.driver_id)
                driver = Member.drivers.filter(id=driver_id).first() if driver_id else None
                if driver is not None and not initiator_is_driver:
                    msg = OrderRemovedFromConcatenatedMessage(order=order, driver=driver)
                    driver.send_versioned_push(msg)

    if concatenated_order.status != ConcatenatedOrder.FAILED:
        # Deleting a concatenated order if it is empty
        orders = Order.all_objects.filter(concatenated_order=concatenated_order, deleted=False)
        orders = orders.exclude(status=ConcatenatedOrder.FAILED)
        if orders.count() <= 1:
            with track_fields_on_change(list(orders), sender=co_auto_processing, happened_at=happened_at):
                create_delete_event(co_auto_processing, concatenated_order, None)
                concatenated_order.safe_delete()

                initiator_is_driver = event.initiator is not None and event.initiator.is_driver
                if concatenated_order.driver is not None and not initiator_is_driver:
                    msg = ConcatenatedOrderUngroupedMessage(order=concatenated_order)
                    concatenated_order.driver.send_versioned_push(msg)

        # Recalculate data as failed order should no longer be counted
        elif order.status == Order.FAILED:
            with track_fields_on_change(concatenated_order, sender=co_auto_processing, happened_at=happened_at):
                concatenated_order.update_data()

    return order


def check_and_create_concatenated_order(order, event, happened_at, *args, **kwargs):
    exist_concatenated_order = ConcatenatedOrder.objects.filter_by_order(order).first()

    if exist_concatenated_order is not None:
        with track_fields_on_change(order, sender=co_auto_processing, happened_at=happened_at):
            with track_fields_on_change(exist_concatenated_order, sender=co_auto_processing, happened_at=happened_at):
                order.concatenated_order = exist_concatenated_order
                order.save()
                exist_concatenated_order.update_data()

                initiator_is_driver = event.initiator is not None and event.initiator.is_driver
                if order.driver is not None and not initiator_is_driver:
                    msg = OrderAddedToConcatenatedMessage(order=order)
                    order.driver.send_versioned_push(msg)

    else:
        deliver_before_min = order.deliver_before.astimezone(order.merchant.timezone)
        deliver_before_min = deliver_before_min.replace(hour=0, minute=0, second=0, microsecond=0)

        matching_orders = Order.all_objects.filter(
            deleted=False,
            merchant_id=order.merchant_id,
            driver_id=order.driver_id,
            status=order.status,
            deliver_before__range=(deliver_before_min, deliver_before_min + timedelta(days=1)),
            customer_id=order.customer_id,
            deliver_address_id=order.deliver_address_id,
        ).exclude(id=order.id)

        if matching_orders.exists():
            tracked_orders = list(matching_orders) + [order]
            with track_fields_on_change(tracked_orders, sender=co_auto_processing, happened_at=happened_at):
                new_concatenated_order = ConcatenatedOrder.objects.create_from_order(order)
                matching_orders.update(concatenated_order=new_concatenated_order)
                new_concatenated_order.update_data()
                create_create_event(co_auto_processing, new_concatenated_order, None)

                initiator_is_driver = event.initiator is not None and event.initiator.is_driver
                if new_concatenated_order.driver is not None and not initiator_is_driver:
                    msg = ConcatenatedOrderGroupedMessage(order=new_concatenated_order)
                    new_concatenated_order.driver.send_versioned_push(msg)

    return order


# # Checks how the status of the concatenated order has changed, adds orders if they fit
@receiver(trigger_object_post_processing)
def check_concatenated_order_update(sender, event, *args, **kwargs):
    order_ct = ContentType.objects.get_for_model(ConcatenatedOrder, for_concrete_model=False)
    if event.content_type != order_ct:
        return
    if event.event != Event.MODEL_CHANGED:
        return
    if 'status' not in event.obj_dump['new_values']:
        return

    concatenated_order = event.object
    concatenated_order.__class__ = ConcatenatedOrder

    if concatenated_order.status not in [Order.NOT_ASSIGNED, Order.ASSIGNED]:
        return
    if concatenated_order.deleted:
        return

    deliver_before_min = datetime.combine(concatenated_order.deliver_day, datetime.min.time())
    deliver_before_min = concatenated_order.merchant.timezone.localize(deliver_before_min)

    matching_orders = Order.all_objects.filter(
        deleted=False,
        merchant_id=concatenated_order.merchant_id,
        driver_id=concatenated_order.driver_id,
        status=concatenated_order.status,
        deliver_before__range=(deliver_before_min, deliver_before_min + timedelta(days=1)),
        customer_id=concatenated_order.customer_id,
        deliver_address_id=concatenated_order.deliver_address_id,
        concatenated_order_id=None,
    )

    if matching_orders.exists():
        matching_orders_list = list(matching_orders)
        with track_fields_on_change(list(matching_orders), sender=co_auto_processing, happened_at=event.happened_at):
            with track_fields_on_change(concatenated_order, sender=co_auto_processing, happened_at=event.happened_at):
                matching_orders.update(concatenated_order=concatenated_order)
                concatenated_order.update_data()

                initiator_is_driver = event.initiator is not None and event.initiator.is_driver
                if concatenated_order.driver is not None and not initiator_is_driver:
                    for order in matching_orders_list:
                        order.concatenated_order = concatenated_order
                        msg = OrderAddedToConcatenatedMessage(order=order)
                        order.driver.send_versioned_push(msg)


@receiver(event_created)
def check_order_change_concatenated_order(sender, event, *args, **kwargs):
    if sender == co_auto_processing:
        return

    if not type(event.object) == Order:
        return

    if event.event != Event.MODEL_CHANGED:
        return

    changed_fields = set(event.obj_dump['new_values'].keys())
    serializer_class = serializer_map.get_for(ConcatenatedOrder)

    old_concatenated_order_id = event.obj_dump['old_values'].get('concatenated_order', None)
    new_concatenated_order_id = event.obj_dump['new_values'].get('concatenated_order', None)
    # The concatenated_order_id has changed in the admin panel
    if isinstance(sender, ModelAdmin) and old_concatenated_order_id != new_concatenated_order_id:

        if old_concatenated_order_id:
            old_concatenated_order = ConcatenatedOrder.objects.get(id=old_concatenated_order_id)
            new_dict = serializer_class(old_concatenated_order).data
            old_dict = copy.deepcopy(new_dict)
            old_dict['order_ids'].append(event.object_id)
            # the old object has one job removed
            create_event(
                old_dict, new_dict, initiator=event.initiator, instance=old_concatenated_order,
                sender=co_auto_processing, track_change_event=serializer_class.Meta.track_change_event
            )

        if new_concatenated_order_id:
            new_concatenated_order = ConcatenatedOrder.objects.get(id=new_concatenated_order_id)
            new_dict = serializer_class(new_concatenated_order).data
            old_dict = copy.deepcopy(new_dict)
            old_dict['order_ids'].remove(event.object_id)
            # the new object has one job added
            create_event(
                old_dict, new_dict, initiator=event.initiator, instance=new_concatenated_order,
                sender=co_auto_processing, track_change_event=serializer_class.Meta.track_change_event
            )

    # Order has been changed
    # Except for concatenated_order, which could only be changed automatically (check_order_update)
    # or in the admin panel.
    # Both cases have already been prepared
    elif not (changed_fields & {'concatenated_order'}) and event.object.concatenated_order_id is not None:
        create_event(
            {}, {}, initiator=event.initiator, instance=event.object.concatenated_order, sender=co_auto_processing,
            track_change_event=serializer_class.Meta.track_change_event, force_create=True,
        )


@receiver(post_save, sender=OrderPickUpConfirmationPhoto)
def check_create_concatenated_order_pick_up_confirmation_photo(sender, instance, created, *args, **kwargs):
    if created and instance.order.is_concatenated_order:
        photos = [
            OrderPickUpConfirmationPhoto(
                order=order, image=instance.image, thumb_image_100x100_field=instance.thumb_image_100x100_field
            )
            for order in instance.order.active_nested_orders.filter(pickup_address_id__isnull=False)
        ]
        OrderPickUpConfirmationPhoto.objects.bulk_create(photos)


@receiver(post_save, sender=OrderConfirmationPhoto)
def check_create_concatenated_order_confirmation_photo(sender, instance, created, *args, **kwargs):
    if created and instance.order.is_concatenated_order:
        photos = [
            OrderConfirmationPhoto(
                order=order, image=instance.image, thumb_image_100x100_field=instance.thumb_image_100x100_field
            )
            for order in instance.order.active_nested_orders
        ]
        OrderConfirmationPhoto.objects.bulk_create(photos)


@receiver(post_save, sender=OrderPreConfirmationPhoto)
def check_create_concatenated_order_pre_confirmation_photo(sender, instance, created, *args, **kwargs):
    if created and instance.order.is_concatenated_order:
        photos = [
            OrderPreConfirmationPhoto(
                order=order, image=instance.image, thumb_image_100x100_field=instance.thumb_image_100x100_field
            )
            for order in instance.order.active_nested_orders
        ]
        OrderPreConfirmationPhoto.objects.bulk_create(photos)


@receiver(post_save, sender=OrderConfirmationDocument)
def check_create_concatenated_order_confirmation_document(sender, instance, created, *args, **kwargs):
    if created and instance.order.is_concatenated_order:
        documents = [
            OrderConfirmationDocument(document=instance.document, name=instance.name, order=order)
            for order in instance.order.active_nested_orders.exclude(order_confirmation_documents__name=instance.name)
        ]
        OrderConfirmationDocument.objects.bulk_create(documents)


@receiver(m2m_changed, sender=OrderConfirmationDocument.tags.through)
def check_add_concatenated_order_confirmation_document_tags(instance, action, reverse, pk_set, *args, **kwargs):
    if reverse is False and action == 'post_add':
        if instance.order.is_concatenated_order:
            documents = OrderConfirmationDocument.objects.filter(
                document=instance.document, order__concatenated_order=instance.order
            )
            for document in documents:
                document.tags.add(*pk_set)


@receiver(m2m_changed, sender=ConcatenatedOrder.terminate_codes.through)
def check_add_concatenated_order_terminate_codes(instance, action, reverse, pk_set, *args, **kwargs):
    if reverse is False and action == 'post_add':
        if instance.is_concatenated_order:
            for order in instance.active_nested_orders:
                order.terminate_codes.add(*pk_set)


@receiver(post_save, sender=ResultChecklistAnswer)
def check_create_concatenated_order_answer(sender, instance, created, *args, **kwargs):
    if not created:
        return

    order = getattr(instance.result_checklist, 'order', None)
    if order is None:
        return
    if not order.is_concatenated_order:
        return
    order.__class__ = ConcatenatedOrder

    answers = [
        ResultChecklistAnswer(
            result_checklist=order.driver_checklist, question=instance.question, answer=instance.answer,
            text=instance.text,
        )
        for order in order.active_nested_orders
    ]
    ResultChecklistAnswer.objects.bulk_create(answers)


@receiver(post_save, sender=ResultChecklistAnswerPhoto)
def check_create_concatenated_order_answer_photo(sender, instance, created, *args, **kwargs):
    if not created:
        return
    order = getattr(instance.answer_object.result_checklist, 'order', None)
    if order is None:
        return
    if not order.is_concatenated_order:
        return

    photos = []
    result_checklists = [order.driver_checklist_id for order in order.orders.all()]
    answer_objects = ResultChecklistAnswer.objects.filter(
        answer_id=instance.answer_object.answer_id,
        question_id=instance.answer_object.question_id,
        result_checklist_id__in=result_checklists,
    )
    for answer_object in answer_objects:
        photos.append(ResultChecklistAnswerPhoto(
            answer_object=answer_object,
            image=instance.image,
            thumb_image_100x100_field=instance.thumb_image_100x100_field,
            image_location=instance.image_location,
            happened_at=instance.happened_at,
        ))

    ResultChecklistAnswerPhoto.objects.bulk_create(photos, signal=False)


@receiver(post_save, sender=ResultChecklist)
def check_save_concatenated_order_checklist(sender, instance, created, *args, **kwargs):
    concatenated_order = getattr(instance, 'order', None)
    if concatenated_order is None:
        return
    if not concatenated_order.is_concatenated_order:
        return
    concatenated_order.__class__ = ConcatenatedOrder

    for order in concatenated_order.active_nested_orders:
        checklist = order.driver_checklist
        if not order.driver_checklist.is_passed:
            # For the ChecklistResult model event, you must specify the initiator.
            with track_fields_on_change(checklist, initiator=order.driver):
                checklist.save()


__all__ = [
    'check_order_update', 'check_order_change_concatenated_order', 'check_concatenated_order_update',
    'check_create_concatenated_order_pick_up_confirmation_photo',
    'check_create_concatenated_order_confirmation_photo', 'check_create_concatenated_order_pre_confirmation_photo',
    'check_create_concatenated_order_confirmation_document',
    'check_add_concatenated_order_confirmation_document_tags', 'check_add_concatenated_order_terminate_codes',
    'check_create_concatenated_order_answer', 'check_save_concatenated_order_checklist',
    'co_auto_processing',
]
