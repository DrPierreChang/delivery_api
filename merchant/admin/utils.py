from django.core.files.base import ContentFile
from django.db.models.signals import post_save

from documents.models import Tag
from merchant.models import Merchant
from merchant.models.mixins import MerchantTypes
from notification.mixins import MessageTemplateStatus
from notification.models import MerchantMessageTemplate
from reporting.models import Event
from reporting.signals import event_created
from tasks.models import Order
from tasks.models.terminate_code import TerminateCode


def on_change_merchant_type(merchant):
    enabled = merchant.merchant_type == MerchantTypes.MERCHANT_TYPES.MIELE_SURVEY
    qs = MerchantMessageTemplate.objects\
        .filter(template_type=MessageTemplateStatus.SPECIAL_MIELE_SURVEY, merchant=merchant)
    if enabled and not qs.exists():
        template = MerchantMessageTemplate.create_template(
            template_type=MessageTemplateStatus.SPECIAL_MIELE_SURVEY,
            merchant=merchant
        )
        template.save()
    qs.update(enabled=enabled)


def deactivate_way_back(merchant, user):
    orders = Order.objects.filter(merchant=merchant, deleted=False, status=Order.WAY_BACK)
    order_dump = {"old_values": {"status": Order.WAY_BACK}, "new_values": {"status": Order.DELIVERED}}
    orders.update(status=Order.DELIVERED)

    for order in orders:
        model_changed_event = Event.objects.create(object=order, merchant=merchant, event=Event.MODEL_CHANGED,
                                                   obj_dump=order_dump, initiator=user)
        field_changed_event = Event.objects.create(object=order, merchant=merchant, event=Event.CHANGED,
                                                   field="status", new_value=Order.DELIVERED,
                                                   initiator=user)
        post_save.send(Event, instance=model_changed_event, created=True)
        post_save.send(Event, instance=field_changed_event, created=True)
        event_created.send(sender=None, event=model_changed_event)
        event_created.send(sender=None, event=field_changed_event)


def reset_autogenerated_settings(merchant_id, source_merchant_id):
    MerchantMessageTemplate.objects.filter(merchant_id=merchant_id).delete()
    TerminateCode.objects.filter(merchant_id=merchant_id).delete()

    reused_settings = list(MerchantMessageTemplate.objects.filter(merchant_id=source_merchant_id)
                           .order_by('created_at')) \
        + list(Tag.objects.filter(merchant_id=source_merchant_id))
    for setting_obj in reused_settings:
        setting_obj.pk, setting_obj.merchant_id = None, merchant_id
        setting_obj.save()

    reused_codes = TerminateCode.objects.filter(merchant_id=source_merchant_id) \
        .values('type', 'code', 'name', 'is_comment_necessary', 'email_notification_recipient')
    TerminateCode.objects.bulk_create(TerminateCode(merchant_id=merchant_id, **code_data) for code_data in reused_codes)


def copy_merchant_logo(merchant_id, source_merchant_id):
    merchant, source_merchant = Merchant.objects.get(pk=merchant_id), Merchant.objects.get(pk=source_merchant_id)
    if not source_merchant.logo:
        return
    with ContentFile(source_merchant.logo.read()) as content:
        merchant.logo.save(name=source_merchant.logo.name, content=content, save=True)
