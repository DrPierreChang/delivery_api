import base64
import calendar
import uuid
from binascii import Error as ConvertError
from datetime import datetime, timedelta

from django.conf import settings
from django.core.files.base import ContentFile

from rest_framework import serializers
from rest_framework.fields import ImageField, empty

import pytz
import six
from constance import config
from dateutil.parser import parse

from radaro_utils.radaro_phone.utils import e164_phone_format, phone_is_valid


class Base64ImageField(ImageField):
    def to_internal_value(self, data):

        if not data:
            return super(Base64ImageField, self).to_internal_value(None)

        if isinstance(data, six.string_types):
            if 'data:' in data and ';base64,' in data:
                header, data = data.split(';base64,')
            try:
                decoded_file = base64.b64decode(data)
            except (TypeError, ConvertError):
                self.fail('invalid_image')
            file_name = str(uuid.uuid4())
            file_extension = self.get_file_extension(file_name, decoded_file)
            complete_file_name = "%s.%s" % (file_name, file_extension, )
            # Test for now
            try:
                bytes_image = six.BytesIO(decoded_file)
                data = ContentFile(bytes_image.getvalue(), name=complete_file_name)
            finally:
                bytes_image.close()

        return super(Base64ImageField, self).to_internal_value(data)

    def get_file_extension(self, file_name, decoded_file):
        import imghdr
        extension = imghdr.what(file_name, decoded_file)
        extension = "jpg" if extension == "jpeg" else extension
        return extension


class ParseDateTimeField(serializers.DateTimeField):

    def __init__(self, force_utc=True, *args, **kwargs):
        self.force_utc = force_utc
        self.server_timezone = pytz.timezone(settings.TIME_ZONE)
        self.utc_timezone = pytz.UTC
        super(ParseDateTimeField, self).__init__(*args, **kwargs)

    def to_internal_value(self, data):
        if not data:
            return None
        try:
            dt = parse(data, dayfirst=False)
            if self.force_utc:
                utcoffset = dt.utcoffset()
                dt = dt.replace(tzinfo=self.utc_timezone)
                if utcoffset is not None:
                    dt = dt - utcoffset
        except (ValueError, TypeError):
            raise serializers.ValidationError('Invalid date format.')
        return dt

    def to_representation(self, value):
        return super(ParseDateTimeField, self).to_representation(value)


class UTCTimestampField(serializers.DateTimeField):
    MS = '_ms'
    SEC = '_sec'

    def to_representation_ms(self, value):
        ms = value.microsecond / 1000.
        return calendar.timegm(value.utctimetuple()) * 1000 + ms

    def to_representation_sec(self, value):
        ms = value.microsecond / 1000000.
        return calendar.timegm(value.utctimetuple()) + ms

    def to_internal_value_sec(self, value):
        value = self.validate_type_of_value(value)
        return pytz.utc.localize(datetime.utcfromtimestamp(value))

    def to_internal_value_ms(self, value):
        value = self.validate_type_of_value(value)
        return pytz.utc.localize(datetime.utcfromtimestamp(value / 1000.))

    def validate_type_of_value(self, value):
        try:
            return float(value)
        except ValueError:
            raise serializers.ValidationError('Float is required')

    def __init__(self, precision=SEC, *args, **kwargs):
        super(UTCTimestampField, self).__init__(*args, **kwargs)
        for m in ['to_internal_value', 'to_representation']:
            setattr(self, m, getattr(self, m + precision))


class PhoneField(serializers.Field):
    def __init__(self, allow_blank=False, **kwargs):
        self.allow_blank = allow_blank
        super(PhoneField, self).__init__(**kwargs)

    def run_validation(self, data=empty):
        (is_empty_value, data) = self.validate_empty_values(data)
        phone = data['phone'] if type(data) == dict else data
        if data == '':
            if self.allow_blank:
                return ''
            else:
                raise serializers.ValidationError('This field may not be blank.')
        if phone and not isinstance(phone, six.string_types):
            raise serializers.ValidationError('Phone number must be string.')
        return super(PhoneField, self).run_validation(data)

    def to_internal_value(self, data):
        (phone, country) = (data['phone'], data['country'].upper()) if type(data) == dict else (data, None)

        if country is None:
            request = self.parent.context.get('request')
            user = request.user if request else self.parent.context.get('user')
            countries = user.current_merchant.countries if user else config.ALLOWED_COUNTRIES
        else:
            countries = [country, ]

        phone_is_valid(phone, regions=countries)
        return e164_phone_format(phone, regions=countries)

    def to_representation(self, value):
        return value


class CustomArrayField(serializers.ListField):
    def to_internal_value(self, data):
        if isinstance(data, str):
            data = [item for item in data.split(',') if item]
        return super(CustomArrayField, self).to_internal_value(data)

    def to_representation(self, data):
        data = super(CustomArrayField, self).to_representation(data)
        return ','.join(data)


class TimezoneField(serializers.Field):
    def to_representation(self, obj):
        return six.text_type(obj)

    def to_internal_value(self, data):
        try:
            return pytz.timezone(str(data))
        except pytz.exceptions.UnknownTimeZoneError:
            raise serializers.ValidationError('Unknown timezone')


class DurationInSecondsField(serializers.DurationField):
    def to_internal_value(self, data):
        return timedelta(seconds=data)

    def to_representation(self, value):
        return int(value.total_seconds())
