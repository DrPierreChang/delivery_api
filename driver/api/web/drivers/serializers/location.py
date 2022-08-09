from rest_framework import serializers

from driver.models import DriverLocation
from radaro_utils.serializers.fields import UTCTimestampField
from radaro_utils.serializers.web.mixins import AbstractAddressSerializer
from routing.serializers.fields import LatLngLocation


class WebPrimaryAddressSerializer(serializers.Serializer):
    location = LatLngLocation(required=False, source='prepared_location')
    address = serializers.CharField(required=False)


class WebDriverLocationSerializer(AbstractAddressSerializer):
    primary_address = WebPrimaryAddressSerializer(source='*')
    timestamp = UTCTimestampField()

    class Meta:
        model = DriverLocation
        fields = (
            'primary_address', 'description', 'accuracy', 'speed', 'bearing', 'timestamp',
            'created_at', 'source', 'offline', 'google_request_cost', 'in_progress_orders', 'google_requests',
        )
