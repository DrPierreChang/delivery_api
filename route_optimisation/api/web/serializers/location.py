from rest_framework import serializers

from route_optimisation.models import DriverRouteLocation
from routing.serializers.fields import LatLngLocation


class DriverRouteLocationSerializer(serializers.ModelSerializer):
    location = LatLngLocation(required=True)

    class Meta:
        model = DriverRouteLocation
        fields = ('id', 'address', 'location',)
