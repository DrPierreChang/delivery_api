from rest_framework import serializers

from merchant.models import Hub, HubLocation
from radaro_utils.serializers.web.mixins import AbstractAddressSerializer


class HubLocationSerializer(AbstractAddressSerializer):
    class Meta(AbstractAddressSerializer.Meta):
        model = HubLocation
        fields = AbstractAddressSerializer.Meta.fields + ('description',)

    def create(self, validated_data):
        if validated_data is None:
            return None

        location, _ = HubLocation.objects.get_or_create(
            location=validated_data.get('location'),
            address=validated_data.get('address', '')
        )
        return location


class WebHubSerializer(serializers.ModelSerializer):
    location = HubLocationSerializer(allow_null=True)

    class Meta:
        model = Hub
        fields = ('id', 'name', 'phone_number', 'location', 'status')
        extra_kwargs = {'phone_number': {'source': 'phone'}}
