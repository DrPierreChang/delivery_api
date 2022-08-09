from rest_framework import serializers

from ...v1.serializers.route_points import RoutePointAbstractSerializer, RoutePointsSerializer


class V2RouteBreakPointObjectSerializer(serializers.Serializer):
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()


class V2RouteBreakPointSerializer(RoutePointAbstractSerializer):
    point_object = V2RouteBreakPointObjectSerializer(source='*')


class V2RoutePointsSerializer(RoutePointsSerializer):
    breaks = V2RouteBreakPointSerializer(many=True)

    class Meta:
        fields = ('hubs', 'orders', 'concatenated_orders', 'locations', 'breaks')

    def _get_points(self, instance):
        return instance.hubs + instance.orders + instance.concatenated_orders + instance.locations + instance.breaks
