import copy
import json

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models import F
from django.template.loader import get_template
from django.utils import timezone

from rest_framework import status

from radaro_utils.files.utils import get_upload_path
from radaro_utils.radaro_notifications.models import (
    BaseEmailMessage,
    BaseMessageTemplate,
    BaseNotification,
    BaseSMSMessage,
)
from radaro_utils.radaro_notifications.renderers import EmailMessageRenderer, SMSMessageRenderer
from radaro_utils.radaro_notifications.sms import SMSMessage
from radaro_utils.utils import guess_mimetype

from ..mixins import MessageTemplateStatus


class Notification(BaseNotification):
    devices = models.ManyToManyField('Device', related_name='sent_notifications')
    extra = models.TextField()

    def save(self, *args, **kwargs):
        if not self.sent_at:
            self.sent_at = timezone.now()
        super(Notification, self).save(*args, **kwargs)

    def __str__(self):
        num_devices = self.devices.count()
        others_text = ' and %s other' % (num_devices - 1) if num_devices > 1 else ''
        device = self.devices.all()[0] if num_devices else None
        return u'%s%s: %s' % (device, others_text, self.message)


def save_notification(send_message_func):
    def control_message(self, message, **kwargs):
        notification = Notification.objects.create(message=message, extra=json.dumps(kwargs))
        if not isinstance(self, models.query.QuerySet):
            devices = type(self).objects.filter(id=self.id)
        else:
            devices = self
        notification.devices.add(*devices)
        try:
            result = send_message_func(self, message, **kwargs)
            notification.extra = {'kwargs': notification.extra, 'result': result}
            notification.save()
        except Exception as ex:
            notification.extra = {'kwargs': notification.extra, 'result': str(ex)}
            notification.save()

    return control_message


class PushNotificationsSettings(models.Model):
    name = models.CharField(max_length=256)
    fcm_key = models.CharField(max_length=512, blank=True)
    gcm_key = models.CharField(max_length=512, blank=True)
    gcm_max_recipients = models.PositiveIntegerField(default=1000)
    fcm_max_recipients = models.PositiveIntegerField(default=1000, validators=[MaxValueValidator(1000)])
    gcm_error_timeout = models.PositiveIntegerField(default=settings.PUSH_SERVICE_TIMEOUT)
    fcm_error_timeout = models.PositiveIntegerField(default=settings.PUSH_SERVICE_TIMEOUT)
    gcm_post_url = models.URLField(default='https://gcm-http.googleapis.com/gcm/send')
    fcm_post_url = models.URLField(default='https://fcm.googleapis.com/fcm/send')
    apns_topic = models.CharField(max_length=1024, blank=True)

    class Meta:
        verbose_name_plural = 'Notifications settings'

    def __str__(self):
        return self.name


class MerchantMessageTemplate(MessageTemplateStatus, BaseMessageTemplate):

    merchant = models.ForeignKey('merchant.Merchant', blank=True, null=True, on_delete=models.CASCADE,
                                 related_name='templates')
    template_type = models.IntegerField(choices=MessageTemplateStatus.types_choices,
                                        default=MessageTemplateStatus.ANOTHER)
    enabled = models.BooleanField(default=True, verbose_name='enable notification')
    use_default = models.BooleanField(default=True)

    class Meta:
        unique_together = ('id', 'template_type')

    def __str__(self):
        return 'Merchant id:{merchant}: "{text:.50}"'.format(merchant=self.merchant_id, text=self.text)

    @property
    def template_name(self):
        return MessageTemplateStatus.template_names_map[self.template_type]

    @classmethod
    def create_template(cls, template_type, template_name=None, merchant=None):
        if not template_name:
            template_name = MessageTemplateStatus.template_names_map.get(template_type)
        text = get_template(template_name + '.txt').template.source
        html_text = get_template(template_name + '.html').template.source
        subject = get_template(template_name + '.subject').template.source
        enabled = template_type in MessageTemplateStatus.enabled_by_default
        return cls(template_type=template_type, text=text, html_text=html_text, subject=subject, merchant=merchant,
                   enabled=enabled)

    @classmethod
    def generate_templates(cls, templates_map, merchant=None):
        for template_type, template_name in templates_map.items():
            yield cls.create_template(template_type, template_name, merchant)

    @classmethod
    def generate_merchant_templates(cls, merchant):
        merchant_templates_map = copy.copy(MessageTemplateStatus.template_names_map)
        del merchant_templates_map[MessageTemplateStatus.ANOTHER]
        del merchant_templates_map[MessageTemplateStatus.WEEKLY_REPORT]

        return cls.generate_templates(templates_map=merchant_templates_map, merchant=merchant)

    @classmethod
    def create_merchant_templates(cls, merchant):
        msg_templates = list(cls.generate_merchant_templates(merchant=merchant))
        cls.objects.bulk_create(msg_templates)


class TemplateMessageMixin(models.Model):
    template = models.ForeignKey('MerchantMessageTemplate', on_delete=models.CASCADE)

    renderer_class = None

    class Meta:
        abstract = True


class TemplateSMSMessage(BaseSMSMessage, TemplateMessageMixin):
    order = models.ForeignKey('tasks.Order', null=True, blank=True, on_delete=models.SET_NULL)

    renderer_class = SMSMessageRenderer

    class Meta:
        verbose_name = 'SMS message'
        verbose_name_plural = 'SMS messages'

    def __init__(self, *args, **kwargs):
        context = kwargs.pop('context', {})
        super(TemplateSMSMessage, self).__init__(*args, **kwargs)

        if not self.pk and self.template_id:
            self.renderer = self.renderer_class(template=self.template)
            self.text = self.renderer.render(context)

    def _on_dispatch(self, response_data=None, is_sent=True, save=False):
        merchant = self.template.merchant
        if not (is_sent and merchant):
            return

        self.price = merchant.price_per_sms * self.segment_count
        if save:
            self.save()
        merchant.balance = F('balance') - self.price
        merchant.save(update_fields=['balance'])

    def build_message(self):
        return SMSMessage(text=self.text, phone_number=self.phone, sender=self.sender)

    def handle_message(self, message):
        response_data = message.sms_status.service_response if hasattr(message, 'sms_status') else None
        is_sent = response_data and message.sms_status.service_response.status_code == status.HTTP_200_OK

        self.dispatch(response_data=response_data, is_sent=is_sent)


class TemplateEmailMessage(BaseEmailMessage, TemplateMessageMixin):
    renderer_class = EmailMessageRenderer

    class Meta:
        verbose_name = 'Email message'
        verbose_name_plural = 'Email messages'

    def __init__(self, *args, **kwargs):
        context = kwargs.pop('context', {})
        super(TemplateEmailMessage, self).__init__(*args, **kwargs)

        if not self.pk and self.template_id:
            self.renderer = self.renderer_class(template=self.template)
            self.text, self.subject, self.html_text = self.renderer.render(context)

    def _on_dispatch(self, response_data=None, is_sent=False, save=False):
        if is_sent:
            self.message_id = response_data.recipients[self.email].message_id

    def _prepare_email_attachments(self):
        for attachment in self.attachments.all():
            file_name = attachment.file.name
            mime_type = guess_mimetype(file_name)
            yield (file_name, attachment.file.read(), mime_type)

    def _get_from_email(self):
        value = settings.DEFAULT_FROM_EMAIL
        merchant = self.template.merchant
        if merchant:
            email_prefix = merchant.email_sender_name or settings.EMAIL_PREFIX
            email_sender = merchant.email_sender or settings.SERVER_EMAIL_FROM
            value = '{} <{}>'.format(email_prefix, email_sender)
        return value

    def build_message(self):
        email_attachments = tuple(self._prepare_email_attachments())

        email = EmailMultiAlternatives(
            subject=self.subject, body=self.text,
            from_email=self._get_from_email(),
            to=[self.email, ],
            attachments=email_attachments
        )
        email.attach_alternative(self.html_text, 'text/html')
        return email

    def handle_message(self, message):
        response_data = getattr(message, 'anymail_status', None)
        is_sent = response_data and message.anymail_status.esp_response.status_code == status.HTTP_202_ACCEPTED

        self.dispatch(response_data=response_data, is_sent=is_sent)

    def add_attachments(self, attachments):
        attachments_to_add = []
        for attachment in attachments:
            attachments_to_add.append(TemplateEmailAttachment(file=attachment, email_message=self))
        TemplateEmailAttachment.objects.bulk_create(attachments_to_add)


class TemplateEmailAttachment(models.Model):
    file = models.FileField(upload_to=get_upload_path)
    created_at = models.DateTimeField(auto_now_add=True)
    email_message = models.ForeignKey(TemplateEmailMessage, related_name='attachments', on_delete=models.CASCADE)


__all__ = ['Notification', 'BaseNotification', 'PushNotificationsSettings', 'TemplateEmailMessage',
           'TemplateEmailAttachment', 'TemplateSMSMessage', 'MerchantMessageTemplate', 'save_notification', ]
