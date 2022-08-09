from rest_framework import serializers

from tasks.models import SKID


class OrderSkidWeightSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKID
        fields = ('value', 'unit')
        extra_kwargs = {
            'value': {'source': 'weight', 'required': True},
            'unit': {'source': 'weight_unit', 'required': True}
        }


class OrderSkidSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKID
        fields = ('width', 'height', 'length', 'unit')
        extra_kwargs = {
            'width': {'required': True},
            'height': {'required': True},
            'length': {'required': True},
            'unit': {'source': 'sizes_unit', 'required': True}
        }


class OrderSkidSerializer(serializers.ModelSerializer):
    weight = OrderSkidWeightSerializer(source='*')
    sizes = OrderSkidSizeSerializer(source='*')

    class Meta:
        model = SKID
        fields = ('name', 'quantity', 'weight', 'sizes')
