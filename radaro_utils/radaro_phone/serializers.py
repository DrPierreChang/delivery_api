from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers
from rest_framework.fields import empty

from constance import config
from crequest.middleware import CrequestMiddleware

from radaro_utils.radaro_phone.utils import e164_phone_format, phone_is_valid, phone_to_international_format


class PhoneField(serializers.CharField):
    def __init__(self, **kwargs):
        # for prevent using default MaxLengthValidator
        _max_length = kwargs.pop('max_length', None)
        super(PhoneField, self).__init__(**kwargs)
        self.max_length = _max_length or 128

    def run_validation(self, data=empty):
        phone = data['phone'] if isinstance(data, dict) else data
        if data == '':
            if self.allow_blank:
                return ''
            else:
                raise serializers.ValidationError(_('This field may not be blank.'))
        if phone and isinstance(phone, str) and len(phone) > self.max_length:
                raise serializers.ValidationError(_('Phone number have too many characters'))
        return serializers.Field.run_validation(self, data)

    def get_countries(self, country):
        return config.ALLOWED_COUNTRIES if country is None else [country, ]

    def to_internal_value(self, data):
        phone, country = (data['phone'], data['country'].upper()) if isinstance(data, dict) else (data, None)

        countries = self.get_countries(country)

        phone_is_valid(phone, regions=countries)
        return e164_phone_format(phone, regions=countries)

    def to_representation(self, value):
        request = CrequestMiddleware.get_request()
        if value and request and request.version >= 2 and value.startswith('+'):
            countries = self.get_countries(None)
            return phone_to_international_format(value, regions=countries)
        return value


class RadaroPhoneField(PhoneField):
    def get_countries(self, country):
        if country is None:
            if 'merchant' in self.parent.context:
                merchant = self.parent.context.get('merchant')
                return merchant.countries if merchant else config.ALLOWED_COUNTRIES

            request = self.parent.context.get('request')
            user = request.user if request else self.parent.context.get('user')
            if user and hasattr(user, 'current_merchant_id') and user.current_merchant_id:
                countries = user.current_merchant.countries
            else:
                countries = config.ALLOWED_COUNTRIES
        else:
            countries = [country, ]
        return countries
