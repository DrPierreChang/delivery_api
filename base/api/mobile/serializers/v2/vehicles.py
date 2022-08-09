from rest_framework import serializers

from ..v1.vehicles import VehicleSerializer


class V2VehicleSerializer(VehicleSerializer):
    capacity = serializers.FloatField()
