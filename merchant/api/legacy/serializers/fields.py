from __future__ import unicode_literals

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

import pytz
from dateutil.parser import parse

from merchant.models import Label, Merchant, SubBranding


class CustomChoiceField(serializers.ChoiceField):
    def to_representation(self, value):
        return {
            'values': dict((elem[1], elem[0]) for elem in self.choices.items()),
            'choice': value,
            'short': Merchant.distance_aliases[value]
        }


class ParseDateTimeTZField(serializers.DateTimeField):
    """
    This serializer representates datetime objects to the chosen in merchant settings format and TZ.
    This includes parsing strings and formatting dates to strings with chosen format and TZ.
    """
    formats = {
        Merchant.LITTLE_ENDIAN: '%d/%m/%Y %X',
        Merchant.MIDDLE_ENDIAN: '%m/%d/%Y %X',
        Merchant.BIG_ENDIAN: '%Y-%m-%d %X'
    }
    parse_detail = {
        Merchant.LITTLE_ENDIAN: dict(dayfirst=True, yearfirst=False),
        Merchant.MIDDLE_ENDIAN: dict(dayfirst=False, yearfirst=False),
        Merchant.BIG_ENDIAN: dict(yearfirst=True, dayfirst=False),
    }

    def __init__(self, *args, **kwargs):
        self.server_timezone = pytz.timezone(settings.TIME_ZONE)
        self.utc_timezone = pytz.UTC
        super(ParseDateTimeTZField, self).__init__(*args, **kwargs)

    def _init_merchant(self):
        try:
            self.merchant = self.context['user'].current_merchant
        except:
            try:
                self.merchant = self.context['request'].user.current_merchant
            except:
                raise ValidationError('Serializer initiated without information about users\'s merchant.')

    def to_representation(self, value):
        self._init_merchant()
        return value.astimezone(self.merchant.timezone).strftime(self.formats[self.merchant.date_format])

    def to_internal_value(self, data):
        if not data:
            return None
        try:
            self._init_merchant()
            dt = parse(data, **self.parse_detail[self.merchant.date_format])
            if not dt.tzinfo:
                dt = self.merchant.timezone.localize(dt)
            return dt.astimezone(self.server_timezone)
        except ValueError:
            raise serializers.ValidationError('Invalid date format.')


class LabelPKField(serializers.PrimaryKeyRelatedField):
    queryset = Label.objects.all()
    default_error_messages = {
        'does_not_exist': 'You don\'t have a label with this ID ({pk_value}).',
    }

    def use_pk_only_optimization(self):
        return False

    def to_internal_value(self, data):
        if self.pk_field is not None:
            data = self.pk_field.to_internal_value(data)
        try:
            return self.get_queryset().get(pk=data)
        except (TypeError, ValueError, ObjectDoesNotExist):
            self.fail('does_not_exist', pk_value=data)


class SubBrandPKField(serializers.PrimaryKeyRelatedField):
    queryset = SubBranding.objects.all()
    default_error_messages = {
        'does_not_exist': 'You don\'t have a sub-brand with this ID ({pk_value}).',
    }

    def to_internal_value(self, data):
        if self.pk_field is not None:
            data = self.pk_field.to_internal_value(data)
        try:
            return self.get_queryset().get(pk=data)
        except (TypeError, ValueError, ObjectDoesNotExist):
            self.fail('does_not_exist', pk_value=data)


class LabelHexColorField(serializers.Field):
    def to_representation(self, value):
        return Label.BASE_COLORS.get(value)

    def to_internal_value(self, data):
        data = [key for key, value in Label.BASE_COLORS.items() if data == value]
        if not data:
            raise serializers.ValidationError("Invalid color value.")
        return data[0]
