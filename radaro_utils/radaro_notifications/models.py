# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import models
from django.utils import timezone

from notification.utils import get_sms_info
from radaro_utils.radaro_phone.models import PhoneField


class BaseNotification(models.Model):
    sent_at = models.DateTimeField(null=True)
    message = models.TextField(blank=True)

    class Meta:
        abstract = True


class BaseMessage(models.Model):
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True)

    class Meta:
        abstract = True

    @property
    def is_sent(self):
        return self.sent_at is not None

    def _on_dispatch(self, *args, **kwargs):
        raise NotImplementedError

    def build_message(self):
        raise NotImplementedError

    def handle_message(self, message):
        raise NotImplementedError

    def dispatch(self, response_data=None, is_sent=False, save=False):
        self._on_dispatch(response_data=response_data, is_sent=is_sent, save=save)
        if is_sent:
            self.sent_at = timezone.now()
        self.dispatched_at = timezone.now()
        if response_data:
            self.response_data = response_data
        if save:
            self.save()

    def send(self, dispatch_eta=None):
        from notification.celery_tasks import send_template_notification
        send_template_notification.apply_async((type(self).__name__, self.id), eta=dispatch_eta)


class BaseMessageTemplate(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    text = models.TextField(verbose_name='sms text')
    html_text = models.TextField(blank=True, verbose_name='email text')
    subject = models.CharField(blank=True, max_length=255, verbose_name='email subject')

    class Meta:
        abstract = True


class BaseSMSMessage(BaseMessage):
    phone = PhoneField()
    sender = models.CharField(max_length=40, default='Radaro')
    segment_count = models.PositiveSmallIntegerField()
    response_data = models.TextField()
    price = models.FloatField(default=0)
    dispatched_at = models.DateTimeField(null=True)

    class Meta:
        abstract = True

    def __str__(self):
        return 'SMS for {phone} from {sender}'.format(phone=self.phone, sender=self.sender)

    def save(self, *args, **kwargs):
        if not self.pk:
            try:
                info = get_sms_info(self.text)
            except ValueError:
                self.segment_count = 1
            else:
                self.segment_count = info['segment_count']

            if not self.sender:
                if hasattr(settings, 'SMS_SENDING_PARAMETERS'):
                    self.sender = settings.SMS_SENDING_PARAMETERS['ORIGINATOR']
                else:
                    self.sender = 'Radaro'
        return super(BaseSMSMessage, self).save(*args, **kwargs)


class BaseEmailMessage(BaseMessage):
    email = models.EmailField()
    html_text = models.TextField(blank=True)
    subject = models.CharField(max_length=255, blank=True)
    message_id = models.CharField(max_length=255, blank=True)

    class Meta:
        abstract = True

    def __str__(self):
        return 'Email for {email} with id: {message_id}'\
            .format(email=self.email, message_id=self.message_id)
