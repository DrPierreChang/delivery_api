from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from rest_framework_bulk import BulkListSerializer, BulkSerializerMixin

from base.api.legacy.serializers import UserSerializer
from notification.models import APNSDevice, GCMDevice, MerchantMessageTemplate


class DeviceSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(source='user', read_only=True)

    device_id = serializers.CharField(required=True, validators=[], allow_blank=False)
    registration_id = serializers.CharField(required=True, validators=[], allow_blank=False)

    def validate(self, data):
        Model = type(self).Meta.model
        try:
            instance, created = Model.objects.get_or_create(device_id=data['device_id'],
                                                            defaults={'registration_id': data['registration_id']})
            self.instance = instance
        except Model.DoesNotExist:
            pass
        return data

    def save(self, **kwargs):
        kwargs['api_version'] = self.context['request'].version
        super(DeviceSerializer, self).save(**kwargs)

    class Meta:
        fields = ('registration_id', 'user', 'user_id', 'real_type', 'device_id',
                  'app_name', 'app_version', 'device_name', 'os_version')
        read_only_fields = ('real_type', )


class GCMDeviceSerializer(DeviceSerializer):
    class Meta(DeviceSerializer.Meta):
        model = GCMDevice

    def save(self, **kwargs):
        return super(GCMDeviceSerializer, self).save(cloud_message_type=GCMDevice.GCM, **kwargs)


class FCMDeviceSerializer(DeviceSerializer):
    class Meta(DeviceSerializer.Meta):
        model = GCMDevice
        fields = DeviceSerializer.Meta.fields + ('device_type',)

    def save(self, **kwargs):
        return super(FCMDeviceSerializer, self).save(cloud_message_type=GCMDevice.FCM, **kwargs)


class APNSDeviceSerializer(DeviceSerializer):
    class Meta(DeviceSerializer.Meta):
        model = APNSDevice


class MerchantMessageTemplateSerializer(BulkSerializerMixin, serializers.ModelSerializer):
    type = serializers.SerializerMethodField()

    class Meta:
        model = MerchantMessageTemplate
        fields = ('id', 'type', 'text', 'enabled')
        list_serializer_class = BulkListSerializer

    def get_type(self, instance):
        return instance.get_template_type_display()

    def validate_enabled(self, value):
        request = self.context['request']
        if value and not request.user.current_merchant.sms_enable:
            raise ValidationError('SMS notifications should be enabled.')
        return value
