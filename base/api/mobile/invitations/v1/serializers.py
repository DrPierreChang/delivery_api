from datetime import timedelta

from django.conf import settings
from django.contrib.auth import password_validation as validators
from django.core import exceptions
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from constance import config

from base.models import Member
from base.utils import MobileAppVersionsConstants
from radaro_utils.radaro_phone.serializers import RadaroPhoneField


class DriverRegisterSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=256)
    phone = RadaroPhoneField()
    pin_code = serializers.CharField(max_length=10)

    ANDROID = MobileAppVersionsConstants.ANDROID
    APP_TYPES = (
        (ANDROID, 'Android'),
    )
    APP_VARIANTS = [(key, key) for key in settings.ANDROID_SMS_VERIFICATION.keys()]
    app_type = serializers.ChoiceField(required=False, choices=APP_TYPES)
    app_variant = serializers.ChoiceField(required=False, choices=APP_VARIANTS)

    class Meta:
        PAIR_FOUND = 'Phone and pin code pair was found.'
        fields = ('phone', 'password', 'pin_code', 'app_type', 'app_variant')
        required = ('phone', 'password', 'pin_code')

    def __init__(self, *args, **kwargs):
        # Don't pass the 'fields' arg up to the superclass
        fields = kwargs.pop('fields', None)
        # Instantiate the superclass normally
        super(DriverRegisterSerializer, self).__init__(*args, **kwargs)

        if fields is not None:
            # Drop any fields that are not specified in the `fields` argument.
            allowed = set(fields)
            existing = set(self.fields.keys())
            for field_name in existing - allowed:
                self.fields.pop(field_name)

    def validate_phone(self, value):
        if Member.objects.filter(phone=value).exists():
            raise serializers.ValidationError(_('Already registered.'))
        else:
            if not self.context['queryset'].filter(phone=value).exists():
                raise serializers.ValidationError(_('No invitations with this phone number were found.'))
        return value

    def validate_password(self, value):
        try:
            validators.validate_password(value)
        except exceptions.ValidationError as err:
            raise serializers.ValidationError(err.messages)
        return value

    def validate(self, attrs):
        pin = attrs.get('pin_code', None)
        equals_to_master_pin = (pin == config.MASTER_PIN)
        pin_in_database = self.context['queryset'].filter(
            phone=attrs['phone'],
            pin_code=pin,
            pin_code_timestamp__gt=timezone.now() - timedelta(minutes=config.TOKEN_TIMEOUT_MIN),
        )

        if pin and not pin_in_database.exists() and not equals_to_master_pin:
            raise serializers.ValidationError({'pin_code': _('Pin code is not valid or out of date.')})
        return attrs

    def get_sms_android_verification_hash(self):
        if self.validated_data.get('app_type', None) == self.ANDROID and 'app_variant' in self.validated_data:
            app_variant = self.validated_data['app_variant']
            return settings.ANDROID_SMS_VERIFICATION[app_variant]
