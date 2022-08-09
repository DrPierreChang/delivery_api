from rest_framework import serializers

from radaro_utils.serializers.mobile.serializers import RadaroMobileListSerializer
from route_optimisation.models import DriverRoute

from ....concatenated_orders.v1.serializers import DriverConcatenatedOrderSerializer
from ....driver_orders.v1.serializers import DriverOrderSerializer
from .route_points import RoutePointsSerializer


class DailyOptimisationRouteSerializer(serializers.ModelSerializer):
    total_time = serializers.IntegerField()
    driving_time = serializers.IntegerField()
    points = RoutePointsSerializer(source='*')

    class Meta:
        list_serializer_class = RadaroMobileListSerializer
        fields = (
            'id', 'optimisation_id', 'color', 'total_time', 'driving_time', 'driving_distance', 'start_time',
            'end_time', 'points',
        )
        model = DriverRoute


class DailyOrdersSerializer(serializers.Serializer):
    delivery_date = serializers.DateField()
    route_optimisations = DailyOptimisationRouteSerializer(many=True)
    orders = serializers.SerializerMethodField()
    concatenated_orders = serializers.SerializerMethodField()

    class Meta:
        fields = ('delivery_date', 'route_optimisations', 'orders')

    def get_orders(self, instance):
        return DriverOrderSerializer(instance['orders'], many=True, context=self.context).data or None

    def get_concatenated_orders(self, instance):
        serializer = DriverConcatenatedOrderSerializer(instance['concatenated_orders'], many=True, context=self.context)
        return serializer.data or None
