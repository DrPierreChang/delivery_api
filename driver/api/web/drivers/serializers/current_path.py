from rest_framework import serializers

from routing.serializers.fields import LatLngLocation

from .location import WebDriverLocationSerializer


class WebPrimaryAddressConverterSerializer(serializers.Serializer):
    location = LatLngLocation(required=False)
    address = serializers.CharField(required=False)


class WebDriverLocationConverterSerializer(WebDriverLocationSerializer):
    primary_address = WebPrimaryAddressConverterSerializer(source='*')
    timestamp = serializers.FloatField()


class WebCurrentPathDriverSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    path_before = serializers.JSONField(required=False)
    before = WebDriverLocationConverterSerializer(required=False)
    path = serializers.JSONField(required=False)
    now = WebDriverLocationConverterSerializer(required=False)
