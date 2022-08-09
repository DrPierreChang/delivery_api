from __future__ import unicode_literals

import copy
import uuid

from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.core.files import File
from django.db import models, transaction

from rest_framework import status

from crequest.middleware import CrequestMiddleware
from model_utils import FieldTracker

from base.models import Member
from tasks.models import Order
from tasks.models.external import ExternalSource
from webhooks.utils import get_client_ip

MERCHANT_API_KEY_LIMIT = getattr(settings, 'MERCHANT_API_KEY_LIMIT', 0)


class MerchantAPIKeyEvents(models.Model):
    CHANGED = 2
    CREATED = 1
    USED = 0
    DELETED = -1

    API_KEY_EVENTS = (
        (CREATED, 'Created'),
        (USED, 'Used'),
        (DELETED, 'Deleted'),
        (CHANGED, 'Changed')
    )

    merchant_api_key = models.ForeignKey('MerchantAPIKey', related_name='api_key_events', null=True,
                                         on_delete=models.SET_NULL)
    ip_address = models.CharField(max_length=120)
    user_agent = models.CharField(max_length=250, null=True, blank=True)
    happened_at = models.DateTimeField(auto_now_add=True)
    event_type = models.IntegerField(choices=API_KEY_EVENTS, default=CREATED)
    field = models.CharField(max_length=45, null=True, blank=True)
    new_value = models.CharField(max_length=256, null=True, blank=True)
    initiator = models.ForeignKey('base.Member', on_delete=models.PROTECT, null=True)

    request_path = models.CharField(max_length=512, null=True, blank=True)
    request_method = models.CharField(max_length=10, null=True, blank=True)
    request_data = JSONField(null=True, blank=True)
    request_query_params = JSONField(null=True, blank=True)
    response_data = JSONField(null=True, blank=True)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        verbose_name_plural = 'Merchant api key events'

    def __str__(self):
        return u'Event with id: {}'.format(self.pk)

    @staticmethod
    def get_request_log(request):
        request_data = request.data.dict() if hasattr(request.data, 'dict') else request.data
        if isinstance(request_data, dict):
            for key in request_data:
                if isinstance(request_data[key], File):
                    request_data[key] = None
        return {
            'request_path': request.path,
            'request_method': request.method,
            'request_data': copy.copy(request_data),
            'request_query_params': request.query_params.dict(),
        }

    @staticmethod
    def get_response_log(response):
        info = {'response_status': response.status_code}
        if status.is_client_error(response.status_code):
            info['response_data'] = response.data
        return info


class MerchantAPIKey(ExternalSource, models.Model):
    SINGLE = 'single'
    MULTI = 'multi'

    api_key_types = (
        (SINGLE, 'Single-User'),
        (MULTI, 'Multi-User')
    )

    tracker = FieldTracker()

    key = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    key_type = models.CharField(max_length=10, choices=api_key_types, default=SINGLE)
    available = models.BooleanField(default=True)
    name = models.CharField(blank=True, max_length=128)
    is_master_key = models.BooleanField(default=False)

    @staticmethod
    def autocomplete_search_fields():
        return "key__icontains", "id__iexact"

    def create_event_data(self, request, event_type=MerchantAPIKeyEvents.USED, field=None, new_value=None,
                          request_log=None, response=None):
        data = {
            'merchant_api_key': self,
            'ip_address': get_client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT'),
            'event_type': event_type,
            'field': field,
            'new_value': new_value,
            'initiator': request.user
        }
        data.update(request_log or {})
        if response is not None:
            data.update(MerchantAPIKeyEvents.get_response_log(response))
        return data

    def used(self, request, request_log, response):
        MerchantAPIKeyEvents.objects.create(**self.create_event_data(request, request_log=request_log,
                                                                     response=response))

    @staticmethod
    def anonymous_used(request, request_log, response):
        data = {
            'merchant_api_key': None,
            'ip_address': get_client_ip(request),
            'user_agent': request.META.get('HTTP_USER_AGENT'),
            'event_type': MerchantAPIKeyEvents.USED,
            'field': None,
            'new_value': None,
            'initiator': None,
        }
        data.update(request_log or {})
        if response is not None:
            data.update(MerchantAPIKeyEvents.get_response_log(response))

        MerchantAPIKeyEvents.objects.create(**data)

    def save(self, **kwargs):
        if not self.creator:
            managers = self.merchant.member_set
            _u = managers.filter(role__in=(Member.ADMIN, Member.MANAGER)).order_by('role').last()
            self.creator = _u
        if not self.name:
            self.name = 'Key ' + str(self.key)[:8] + '*'
        request = CrequestMiddleware.get_request()
        if not request:
            return super(MerchantAPIKey, self).save(**kwargs)
        events = []
        if not self.id:
            events.append(MerchantAPIKeyEvents(**self.create_event_data(
                request,
                event_type=MerchantAPIKeyEvents.CREATED
            )))
        else:
            for field, new_value in self.tracker.changed().items():
                events.append(MerchantAPIKeyEvents(**self.create_event_data(
                    request,
                    event_type=MerchantAPIKeyEvents.CHANGED,
                    field=field,
                    new_value=str(new_value)
                )))
        with transaction.atomic():
            super(MerchantAPIKey, self).save(**kwargs)
            MerchantAPIKeyEvents.objects.bulk_create(events)

    def __str__(self):
        return u'{}'.format(self.key)

    @property
    def related_merchants(self) -> [tuple, models.QuerySet]:
        return (self.merchant_id, ) if self.key_type == MerchantAPIKey.SINGLE \
            else self.merchants.values_list('id', flat=True)


class MerchantAPIMultiKeyManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(key_type=MerchantAPIKey.MULTI)


class MerchantAPIMultiKey(MerchantAPIKey):
    objects = MerchantAPIMultiKeyManager()

    class Meta:
        proxy = True


class MerchantWebhookEvent(models.Model):
    merchant = models.ForeignKey('merchant.Merchant', on_delete=models.CASCADE)
    sub_branding = models.ForeignKey('merchant.SubBranding', null=True, on_delete=models.SET_NULL)
    webhook_url = models.CharField(max_length=500)
    request_data = JSONField()
    response_status = models.PositiveSmallIntegerField(blank=True, null=True)
    response_text = models.TextField(blank=True, null=True)
    elapsed_time = models.DurationField(blank=True, null=True)
    exception_detail = models.TextField(blank=True, null=True)
    happened_at = models.DateTimeField()
    topic = models.CharField(max_length=64, blank=True)
    order = models.ForeignKey(Order, null=True, on_delete=models.CASCADE)

    class Meta:
        ordering = ('-happened_at',)
        indexes = [
            models.Index(fields=['-happened_at', '-id']),
        ]
