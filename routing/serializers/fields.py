from rest_framework import serializers


class LatLngLocation(serializers.Serializer):
    lat = serializers.FloatField(required=True)
    lng = serializers.FloatField(required=True)

    def to_internal_value(self, value):
        value = super().to_internal_value(value)
        return '{lat:.6f},{lng:.6f}'.format(**value)

    def to_representation(self, value):
        if not value:
            return None
        loc = list(map(float, value.replace(' ', '').split(',')))
        return super().to_representation({'lat': round(loc[0], 6), 'lng': round(loc[1], 6)})
