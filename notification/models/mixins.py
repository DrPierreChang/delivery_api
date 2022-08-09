import itertools as it_
import operator as op_

from django.conf import settings
from django.db import transaction
from django.db.models import Q

import deprecation

from radaro_utils.radaro_phone.utils import phone_is_mobile

from ..settings import __version__
from .notifications import TemplateEmailMessage, TemplateSMSMessage


class SendNotificationMixin(object):
    default_phone_field = ''
    default_email_field = ''

    def _get_context(self, extra_context=None):
        extra_context = extra_context or {}
        context = {type(self).__name__.lower(): self, 'settings': settings}
        context.update(extra_context)

        return context

    def _get_phone(self):
        return getattr(self, 'phone', None) or getattr(self, self.default_phone_field, None)

    def _get_email(self):
        return getattr(self, 'email', None) or getattr(self, self.default_email_field, None)

    def _get_sender(self):
        return getattr(self, 'default_sms_sender', None)

    def _send_sms(self, template, phone=None, sender=None, extra_context=None, dispatch_eta=None, **kwargs):
        context = self._get_context(extra_context)
        order = context.get('order', None)
        phone = phone or self._get_phone()

        if not phone or not phone_is_mobile(phone):
            return

        sms_sender = sender or self._get_sender()
        sms_message = TemplateSMSMessage.objects.create(template=template, order=order, phone=phone,
                                                        sender=sms_sender, context=context)
        sms_message.send(dispatch_eta=dispatch_eta)

    def _send_email(self, template, email=None, attachments=None, extra_context=None, dispatch_eta=None, **kwargs):
        context = self._get_context(extra_context)
        if 'merchant' not in context:
            context['merchant'] = template.merchant
        email = email or self._get_email()
        attachments = attachments or []

        if not email:
            return

        email_message = TemplateEmailMessage.objects.create(email=email, template=template, context=context)
        email_message.add_attachments(attachments)

        email_message.send(dispatch_eta=dispatch_eta)

    def send_notification(self, template_type, merchant_id=None, send_sms=True, send_email=True, **kwargs):
        from .notifications import MerchantMessageTemplate
        template = MerchantMessageTemplate.objects.filter(
            merchant_id=merchant_id,
            template_type=template_type,
            enabled=True
        ).first()

        if not template:
            return
        if send_sms:
            self._send_sms(template=template, **kwargs)
        if send_email:
            self._send_email(template=template, **kwargs)

    def push_available(self, exclude_devices=None):
        _device_versions = getattr(self, '_device_versions', None)
        if not _device_versions or exclude_devices:
            _devices = self.device_set.filter(in_use=True).exclude(
                Q(apnsdevice__device_id__in=exclude_devices) | Q(gcmdevice__device_id__in=exclude_devices)
            ) if exclude_devices else self.device_set.filter(in_use=True).all()
            _devices = _devices.order_by('api_version').values('id', 'api_version')
            _device_versions = {version: [item['id'] for item in ids] for version, ids
                                in it_.groupby(_devices, op_.itemgetter('api_version'))}
            self._device_versions = _device_versions
        return True if _device_versions else False

    @deprecation.deprecated(deprecated_in='2.0', removed_in='3.0',
                            current_version=__version__,
                            details='Use send_versioned_push instead.')
    def send_push(self, message_type, data, async_=True):
        from notification.celery_tasks import send_device_notification

        # TODO: Maybe raise Exception
        if self.push_available():
            notify = send_device_notification.delay if async_ else send_device_notification
            for _, _devices_ids in self._device_versions.items():
                notify({'type': message_type, 'data': data}, _devices_ids)

    def send_versioned_push(self, message_obj, exclude_devices=None, async_=True, background=False):
        if self.push_available(exclude_devices=exclude_devices):
            from notification.celery_tasks import send_device_notification
            notify = send_device_notification.delay if async_ else send_device_notification
            for version, _devices_ids in self._device_versions.items():
                def callback():
                    language = getattr(self, 'language', settings.LANGUAGE_CODE)
                    notify(
                        device_ids=_devices_ids,
                        message=message_obj.get_kwargs(version=version, language=language),
                        content_available=background
                    )
                callback() if settings.TESTING_MODE else transaction.on_commit(callback)


__all__ = ['SendNotificationMixin', ]
