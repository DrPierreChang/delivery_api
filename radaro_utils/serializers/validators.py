from __future__ import absolute_import

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.datetime_safe import datetime
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

import pytz
from constance import config

from radaro_utils.exceptions import TimeMismatchingError


class ValidateEarlierThanNow(object):
    _message = 'This date cannot be in future.'
    delta = timedelta(seconds=5)

    def __call__(self, value):
        if value and value > timezone.now() + self.delta:
            raise TimeMismatchingError(reason=self._message)
        else:
            return value


class ValidateEarlierThanNowConfigurable(ValidateEarlierThanNow):
    def __call__(self, value):
        self.delta = timedelta(seconds=config.ALLOWED_DELTA_IN_FUTURE)
        return super(ValidateEarlierThanNowConfigurable, self).__call__(value)


class ValidateLaterDoesNotExist(object):
    _message = 'Cannot create {} earlier then the latest one.'

    def __init__(self, queryset, time_fieldname):
        self.queryset = queryset
        oldest_object = self.queryset.order_by(time_fieldname).only(time_fieldname).last()
        self.oldest_time = getattr(oldest_object, time_fieldname) if oldest_object is not None else None
        super(ValidateLaterDoesNotExist, self).__init__()

    def __call__(self, value):
        if value and self.oldest_time and value < self.oldest_time:
            raise TimeMismatchingError(
                reason=self._message.format(self.queryset.model._meta.verbose_name),
                last_item_time=self.oldest_time
            )
        else:
            return value


class LaterThenNowValidator(object):
    _message = _('This date cannot be earlier than now.')

    def __call__(self, value):
        if not value:
            return value
        server_timezone = pytz.timezone(settings.TIME_ZONE)
        now = server_timezone.localize(datetime.now())
        if value < now:
            raise serializers.ValidationError(self._message)


class RangeBoundsValidator(object):
    _message = 'Range lower bound must be less than range upper bound.'

    def __call__(self, value):
        if value.lower < value.upper:
            return value
        raise serializers.ValidationError(self._message)


class SameDayRangeValidation(object):
    _message = 'Range lower and upper bounds must be within one day.'

    def __init__(self):
        self.merchant = None

    def __call__(self, value):
        low, up = value.lower, value.upper
        if self.merchant:
            low, up = low.astimezone(self.merchant.timezone), up.astimezone(self.merchant.timezone)
        if low.date() != up.date():
            raise serializers.ValidationError(self._message)

    def set_context(self, serializer_field):
        request = serializer_field.parent.context.get('request')
        if request and request.user:
            self.merchant = request.user.current_merchant


class NotEmptyValidator(object):
    _message = 'This field cannot be empty value.'

    def __call__(self, value):
        if not value:
            raise serializers.ValidationError(self._message)


class ExternalIDUniqueTogetherValidator(serializers.UniqueTogetherValidator):
    def __call__(self, attrs, *args, **kwargs):
        try:
            super(ExternalIDUniqueTogetherValidator, self).__call__(attrs, *args, **kwargs)
        except serializers.ValidationError as ex:
            full_details = ex.get_full_details()
            if full_details and full_details[0].get('code') == 'unique' and 'external_id' in attrs:
                message = "Order with such api key and id \"%s\" already exists." % attrs['external_id']
                raise serializers.ValidationError(message, code='unique')
            else:
                raise
