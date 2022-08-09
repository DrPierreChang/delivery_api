from rest_framework import serializers

from tasks.models import SKID, Order

from .base import OrderSkidSerializer


class DeltaOrderSkidSerializer(OrderSkidSerializer):
    class Meta(OrderSkidSerializer.Meta):
        fields = ('id', 'name', 'quantity', 'weight', 'sizes', 'driver_changes')
        extra_kwargs = {
            'driver_changes': {'read_only': True},
        }


class DeltaOrderCargoes(serializers.ModelSerializer):
    skids = DeltaOrderSkidSerializer(many=True, required=False)

    class Meta:
        model = Order
        fields = ('skids',)
