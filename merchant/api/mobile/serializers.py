from merchant.models import HubLocation
from radaro_utils.serializers.mixins import AbstractAddressSerializer


class HubLocationSerializer(AbstractAddressSerializer):

    class Meta(AbstractAddressSerializer.Meta):
        model = HubLocation

    def create(self, validated_data):
        if validated_data is None:
            return None

        location, is_created = HubLocation.objects.get_or_create(
            location=validated_data.get('location'),
            address=validated_data.get('address', ''),
        )
        return location
