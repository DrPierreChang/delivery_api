from __future__ import unicode_literals

from rest_framework import serializers

from base.models import Car


class CarSerializer(serializers.ModelSerializer):
    car_type_name = serializers.SerializerMethodField()

    class Meta:
        model = Car
        fields = ('car_type', 'car_type_name', 'capacity')

    def get_car_type_name(self, instance):
        request_version = getattr(self.context.get('request'), 'version', 2)
        # convert translated __proxy__ object into str() for correct serialization
        return str(Car.vehicle_types_for_version(request_version).get(instance.car_type))
