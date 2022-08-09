from base.api.mobile.serializers.v2.vehicles import V2VehicleSerializer

from ..v1.serializers import DriverSerializer


class V2DriverSerializer(DriverSerializer):
    vehicle = V2VehicleSerializer(source='car')
