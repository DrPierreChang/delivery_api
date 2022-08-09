from rest_framework import serializers

from base.models import Car


class VehicleSerializer(serializers.ModelSerializer):
    type = serializers.ChoiceField(choices=Car.vehicle_types, required=False, source='car_type')
    type_name = serializers.SerializerMethodField()
    capacity = serializers.IntegerField()

    class Meta:
        model = Car
        fields = ('type', 'type_name', 'capacity')

    def get_type_name(self, instance):
        return Car.vehicle_types_for_version(version=2).get(instance.car_type)
