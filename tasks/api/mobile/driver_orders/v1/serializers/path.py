from rest_framework import serializers

from routing.serializers.fields import LatLngLocation
from tasks.models import Order


class LatLngListLocation(serializers.ListSerializer):
    child = LatLngLocation()


class PathSerializer(serializers.BaseSerializer):
    value_serializer = LatLngListLocation()
    key_field = serializers.CharField()

    def to_representation(self, instance):
        """
        Object instance -> Dict of primitive datatypes.
        """
        ret = {}

        for key, value in instance.items():
            if value:
                key = self.key_field.to_representation(key)
                value = self.value_serializer.to_representation(value)
                ret[key] = value

        return ret or None


class OrderPathSerializer(serializers.ModelSerializer):
    path = PathSerializer()

    class Meta:
        model = Order
        fields = ('path',)
