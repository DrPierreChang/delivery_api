from rest_framework import serializers

from notification.api.mobile.utils import CurrentAPIVersionDefault
from notification.models import GCMDevice


class FCMDeviceSerializer(serializers.ModelSerializer):
    cloud_message_type = serializers.HiddenField(default=GCMDevice.FCM)
    in_use = serializers.HiddenField(default=True)
    api_version = serializers.HiddenField(default=CurrentAPIVersionDefault())
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = GCMDevice
        fields = ('registration_id', 'user', 'device_id', 'api_version', 'cloud_message_type',
                  'app_name', 'app_version', 'device_name', 'os_version', 'device_type', 'in_use')
        extra_kwargs = {
            'device_id': {'required': True, 'allow_null': False, 'validators': []},
            'device_type': {'required': True}
        }

    def create(self, validated_data):
        instance = self.Meta.model.objects\
            .update_or_create(device_id=validated_data['device_id'], defaults=validated_data)
        return instance
