from django.core.validators import MinValueValidator

from rest_framework import serializers

from base.models import Car
from radaro_utils.serializers.mobile.serializers import DynamicKeySerializer


class OneTimeCapacitySerializer(DynamicKeySerializer):
    key_field = serializers.DateField()
    value_field = serializers.FloatField(allow_null=True, validators=[MinValueValidator(limit_value=0)])

    def validate_key_field(self, day):
        if day < self.root.instance.merchant.today:
            raise serializers.ValidationError('You cannot set a capacity for the past day ')
        return day

    def validate_value_field(self, value):
        if isinstance(value, int) and value < 0:
            raise serializers.ValidationError('The capacity must be at least zero')
        return value

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)

        today = self.root.instance.merchant.today
        for day in list(instance.keys()):
            if day < today:
                del instance[day]
        return instance


class WebCapacityVehicleSerializer(serializers.ModelSerializer):
    constant = serializers.FloatField(allow_null=True, source='capacity', validators=[MinValueValidator(limit_value=0)])
    one_time = OneTimeCapacitySerializer(source='one_time_capacities')

    class Meta:
        model = Car
        fields = ('constant', 'one_time')


class WebVehicleSerializer(serializers.ModelSerializer):
    type = serializers.IntegerField(read_only=True, source='car_type')
    type_name = serializers.CharField(read_only=True, source='car_type_name')
    capacity = WebCapacityVehicleSerializer(source='*')

    class Meta:
        model = Car
        fields = ('type', 'type_name', 'capacity')

    def update(self, instance, validated_data):
        if instance is None:
            instance = Car.objects.create()

        if 'one_time_capacities' in validated_data:
            one_time_capacities = self.fields['capacity'].fields['one_time']
            validated_data['one_time_capacities'] = one_time_capacities.update(
                instance.one_time_capacities, validated_data['one_time_capacities'])
        return super().update(instance, validated_data)
