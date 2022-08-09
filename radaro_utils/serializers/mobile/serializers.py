import copy
from collections import OrderedDict

from django.db import models
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from radaro_utils.radaro_phone import models as radaro_models
from radaro_utils.serializers.mobile.fields import (
    RadaroMobileCharField,
    RadaroMobileEmailField,
    RadaroMobilePhoneField,
    RadaroMobilePrimaryKeyRelatedField,
)


class RadaroMobileModelSerializer(serializers.ModelSerializer):
    serializer_field_mapping = copy.deepcopy(serializers.ModelSerializer.serializer_field_mapping)
    serializer_field_mapping.update({
        models.CharField: RadaroMobileCharField,
        models.TextField: RadaroMobileCharField,
        models.EmailField: RadaroMobileEmailField,
        radaro_models.PhoneField: RadaroMobilePhoneField
    })
    serializer_related_field = RadaroMobilePrimaryKeyRelatedField


class RadaroMobileListSerializer(serializers.ListSerializer):
    def to_representation(self, data):
        result = super().to_representation(data)
        if not result and self.parent is not None:
            return None
        return result


EMPTY_VALUES = (None, [], {})


class DynamicKeySerializer(serializers.BaseSerializer):
    key_field = None
    value_field = None

    default_error_messages = {
        'invalid': _('Invalid data. Expected a dictionary, but got {datatype}.')
    }

    def validate_key_field(self, key):
        return key

    def validate_value_field(self, value):
        return value

    def to_internal_value(self, data):
        """
        Dict of native values <- Dict of primitive datatypes.
        """
        if not isinstance(data, serializers.Mapping):
            message = self.error_messages['invalid'].format(
                datatype=type(data).__name__
            )
            raise serializers.ValidationError({
                serializers.api_settings.NON_FIELD_ERRORS_KEY: [message]
            }, code='invalid')

        ret = OrderedDict()
        errors = OrderedDict()

        for key, value in data.items():
            try:
                # validate key
                validated_key = self.key_field.run_validation(key)
                validated_key = self.validate_key_field(validated_key)
            except serializers.ValidationError as exc:
                errors[key] = exc.detail
            except serializers.DjangoValidationError as exc:
                errors[key] = serializers.get_error_detail(exc)
            else:
                try:
                    # if key is valid, validate value
                    validated_value = self.value_field.run_validation(value)
                    validated_value = self.validate_value_field(validated_value)
                except serializers.ValidationError as exc:
                    errors[key] = exc.detail
                except serializers.DjangoValidationError as exc:
                    errors[key] = serializers.get_error_detail(exc)
                except serializers.SkipField:
                    pass
                else:
                    # set valid key and value
                    ret[validated_key] = validated_value

        if errors:
            raise serializers.ValidationError(errors)

        return ret

    def to_representation(self, instance):
        """
        Object instance -> Dict of primitive datatypes.
        """
        ret = OrderedDict()

        for key, value in instance.items():
            if value not in EMPTY_VALUES:
                key = self.key_field.to_representation(key)
                value = self.value_field.to_representation(value)
                ret[key] = value

        return OrderedDict(sorted(ret.items(), key=lambda t: t[0]))

    def create(self, validated_data):
        result = {}
        for key, value in validated_data.items():
            if value not in EMPTY_VALUES:
                result[key] = value

        return result

    def update(self, instance, validated_data):
        for key, value in validated_data.items():
            if value in EMPTY_VALUES:
                instance.pop(key, None)
            else:
                instance[key] = value

        return instance
