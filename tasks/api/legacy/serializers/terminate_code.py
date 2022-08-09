from django.conf import settings

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.settings import api_settings

from reporting.api.legacy.serializers.delta import DeltaSerializer
from reporting.model_mapping import serializer_map
from tasks.models.terminate_code import SUCCESS_CODES_DISABLED_MSG, TerminateCode


class TerminateCodeNumberSerializer(serializers.ModelSerializer):
    class Meta:
        model = TerminateCode
        fields = ('code', 'name', 'type', 'is_comment_necessary')

    def to_internal_value(self, value):
        merchant = self.context.get('request').user.current_merchant
        try:
            code = merchant.terminate_codes.get(code=value)
            return code
        except TerminateCode.DoesNotExist:
            raise ValidationError('Your merchant does not have this code.')


class TerminateCodeSerializer(serializers.ModelSerializer):
    name = serializers.CharField(error_messages={
        'max_length': 'Description should be no longer than {max_length} characters.',
    }, max_length=100)
    type = serializers.ChoiceField(choices=TerminateCode.TYPE_CHOICES)

    class Meta:
        model = TerminateCode
        fields = ('id', 'code', 'type', 'name', 'is_comment_necessary')

    def update(self, instance, validated_data):
        if instance.code == settings.TERMINATE_CODES[instance.type]['OTHER']:
            raise serializers.ValidationError('You can\'t change "other" code.')
        return super(TerminateCodeSerializer, self).update(instance, validated_data)

    def create(self, validated_data):
        merchant = self.context.get('request').user.current_merchant
        code_type = validated_data.get('type')
        if code_type == TerminateCode.TYPE_SUCCESS and not merchant.advanced_completion_enabled:
            raise serializers.ValidationError(SUCCESS_CODES_DISABLED_MSG)
        codes = TerminateCode.objects.filter(merchant=merchant, type=code_type)
        if codes.count() >= settings.TERMINATE_CODES[code_type]['MAX_COUNT']:
            raise serializers.ValidationError({api_settings.NON_FIELD_ERRORS_KEY: ['You can\'t create more codes.']})
        return super(TerminateCodeSerializer, self).create(validated_data)


@serializer_map.register_serializer
class TerminateCodeDeltaSerializer(DeltaSerializer):
    class Meta(DeltaSerializer.Meta):
        model = TerminateCode


class ExternalTerminateCodeSerializer(TerminateCodeSerializer):
    class Meta:
        model = TerminateCode
        fields = ('code', 'type', 'name')


class ExternalTerminateCodeExtendedSerializer(ExternalTerminateCodeSerializer):
    class Meta(ExternalTerminateCodeSerializer.Meta):
        fields = ExternalTerminateCodeSerializer.Meta.fields + ('merchant',)


# For backward compatibility
class ErrorCodeSerializer(TerminateCodeSerializer):
    type = serializers.ChoiceField(choices=TerminateCode.TYPE_CHOICES, default=TerminateCode.TYPE_ERROR)


# For backward compatibility
class ErrorCodeNumberSerializer(TerminateCodeNumberSerializer):
    INVALID_TYPE_MSG = 'Current code is not error code.'

    def to_representation(self, instance):
        if instance.type == TerminateCode.TYPE_ERROR:
            return super(ErrorCodeNumberSerializer, self).to_representation(instance)

    def to_internal_value(self, value):
        internal_value = super(ErrorCodeNumberSerializer, self).to_internal_value(value)
        if internal_value.type != TerminateCode.TYPE_ERROR:
            raise ValidationError(self.INVALID_TYPE_MSG)
        return internal_value
