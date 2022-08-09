from rest_framework import serializers

from tasks.models import SKID, Order


class WebOrderSkidWeightSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKID
        fields = ('value', 'unit')
        extra_kwargs = {
            'value': {'source': 'weight', 'required': True},
            'unit': {'source': 'weight_unit', 'required': True}
        }


class WebOrderSkidSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKID
        fields = ('width', 'height', 'length', 'unit')
        extra_kwargs = {
            'width': {'required': True},
            'height': {'required': True},
            'length': {'required': True},
            'unit': {'source': 'sizes_unit', 'required': True}
        }


class WebSkidSerializer(serializers.ModelSerializer):
    weight = WebOrderSkidWeightSerializer(source='*')
    sizes = WebOrderSkidSizeSerializer(source='*')
    id = serializers.IntegerField(read_only=True)

    class Meta:
        model = SKID
        fields = ('id', 'name', 'quantity', 'weight', 'sizes', 'driver_changes', 'original_skid')


class WebOrderCargoes(serializers.ModelSerializer):
    skids = WebSkidSerializer(many=True)

    class Meta:
        model = Order
        fields = ('skids',)
