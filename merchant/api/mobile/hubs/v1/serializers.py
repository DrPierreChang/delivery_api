from merchant.models import Hub
from radaro_utils.serializers.mobile.serializers import RadaroMobileListSerializer, RadaroMobileModelSerializer

from ...serializers import HubLocationSerializer


class HubSerializer(RadaroMobileModelSerializer):
    location = HubLocationSerializer()

    class Meta:
        list_serializer_class = RadaroMobileListSerializer
        model = Hub
        fields = ('id', 'name', 'location')
