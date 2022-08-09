from rest_framework import serializers

from radaro_utils.serializers.mobile.fields import NullResultMixin
from tasks.models import SKID, Order


class DriverOrderSkidWeightSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKID
        fields = ('value', 'unit')
        extra_kwargs = {
            'value': {'source': 'weight', 'required': True},
            'unit': {'source': 'weight_unit', 'required': True}
        }


class DriverOrderSkidSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKID
        fields = ('width', 'height', 'length', 'unit')
        extra_kwargs = {
            'width': {'required': True},
            'height': {'required': True},
            'length': {'required': True},
            'unit': {'source': 'sizes_unit', 'required': True}
        }


class DriverSkidSerializer(serializers.ModelSerializer):
    weight = DriverOrderSkidWeightSerializer(source='*')
    sizes = DriverOrderSkidSizeSerializer(source='*')
    id = serializers.IntegerField(read_only=True)

    class Meta:
        model = SKID
        fields = ('id', 'name', 'quantity', 'weight', 'sizes')


class DriverOrderCargoes(NullResultMixin, serializers.ModelSerializer):
    skids = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ('skids',)

    def get_skids(self, instance):
        if hasattr(instance, 'not_deleted_skids'):
            skids = instance.not_deleted_skids
        else:
            skids = instance.skids.all().exclude(driver_changes=SKID.DELETED)
        return DriverSkidSerializer(skids, many=True).data or None
