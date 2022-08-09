from radaro_utils.serializers.mixins import AbstractAddressSerializer
from tasks.models import OrderLocation


class OrderLocationSerializer(AbstractAddressSerializer):

    class Meta(AbstractAddressSerializer.Meta):
        model = OrderLocation
        fields = AbstractAddressSerializer.Meta.fields + ('secondary_address',)

    def create(self, validated_data):
        if validated_data is None:
            return None

        location, _ = OrderLocation.objects.get_or_create(
            location=validated_data.get('location'),
            address=validated_data.get('address', ''),
            secondary_address=validated_data.get('secondary_address', ''),
            raw_address='',
        )
        return location
