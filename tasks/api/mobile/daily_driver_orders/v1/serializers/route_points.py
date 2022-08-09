from collections import defaultdict
from operator import attrgetter

from rest_framework import serializers

from merchant.api.mobile.hubs.v1.serializers import HubSerializer
from radaro_utils.serializers.mobile.serializers import RadaroMobileListSerializer
from route_optimisation.api.legacy.serializers.location import DriverRouteLocationSerializer
from route_optimisation.const import RoutePointKind
from route_optimisation.models import RoutePoint

from ....concatenated_orders.v1.serializers import DriverConcatenatedOrderSerializer
from ....driver_orders.v1.serializers import DriverOrderSerializer


class PlannedArrivalSerializer(serializers.Serializer):
    before = serializers.DateTimeField()
    after = serializers.DateTimeField()

    class Meta:
        fields = ('before', 'after')


class RoutePointAbstractSerializer(serializers.ModelSerializer):
    planned_arrival = serializers.SerializerMethodField()
    planned_time = serializers.SerializerMethodField()
    point_object = None

    class Meta:
        model = RoutePoint
        fields = ('number', 'point_kind', 'planned_arrival', 'planned_time', 'point_object')
        list_serializer_class = RadaroMobileListSerializer

    def get_planned_arrival(self, point):
        interval = point.planned_order_arrival_interval
        return {
            'after': serializers.DateTimeField().to_representation(interval[0]),
            'before': serializers.DateTimeField().to_representation(interval[1]),
        }

    def get_planned_time(self, point):
        return serializers.DateTimeField().to_representation(point.start_time)


class RouteOrderPointSerializer(RoutePointAbstractSerializer):
    point_object = serializers.SerializerMethodField()

    def get_point_object(self, point):
        return DriverOrderSerializer(point.point_object, context=self.context).data


class RouteConcatenatedOrderPointSerializer(RoutePointAbstractSerializer):
    point_object = serializers.SerializerMethodField()
    concatenated_order = serializers.SerializerMethodField()

    class Meta(RoutePointAbstractSerializer.Meta):
        fields = RoutePointAbstractSerializer.Meta.fields + ('concatenated_order',)

    def get_point_object(self, point):
        return DriverOrderSerializer(point.point_object, context=self.context).data

    def get_concatenated_order(self, point):
        order = point.point_object
        concatenated = order._self_concatenated if order.is_concatenated_order else order.concatenated_order
        return DriverConcatenatedOrderSerializer(concatenated, context=self.context).data


class RouteHubPointSerializer(RoutePointAbstractSerializer):
    point_object = HubSerializer()


class RouteLocationPointSerializer(RoutePointAbstractSerializer):
    point_object = DriverRouteLocationSerializer()


class RoutePointsSerializer(serializers.Serializer):
    hubs = RouteHubPointSerializer(many=True)
    orders = RouteOrderPointSerializer(many=True)
    concatenated_orders = RouteConcatenatedOrderPointSerializer(many=True)
    locations = RouteLocationPointSerializer(many=True)

    class Meta:
        fields = ('hubs', 'orders', 'concatenated_orders', 'locations')

    def to_representation(self, instance):
        self._update_points_info(instance)
        return super().to_representation(instance)

    def _update_points_info(self, instance):
        points = self._get_points(instance)
        points = sorted(points, key=attrgetter('number'))
        concatenated_pickups = self._find_concatenated_pickups(instance.concatenated_orders)

        number = 1
        for point in points:
            if point.point_kind == RoutePointKind.PICKUP:
                key = self._get_concatenated_pickup_unique_key(point)
                if len(concatenated_pickups.get(key, [])) >= 2:
                    instance.concatenated_orders.remove(point)
                    concatenated_pickups[key].pop()
                    continue

            point.number = number
            number += 1

    def _get_points(self, instance):
        return instance.hubs + instance.orders + instance.concatenated_orders + instance.locations

    def _find_concatenated_pickups(self, concatenated_orders):
        concatenated_pickups = defaultdict(list)
        for point in concatenated_orders:
            if point.point_kind == RoutePointKind.PICKUP and point.point_object.pickup_address_id:
                concatenated_pickups[self._get_concatenated_pickup_unique_key(point)].append(point)
        return concatenated_pickups

    @staticmethod
    def _get_concatenated_pickup_unique_key(point):
        return point.point_object.pickup_address_id, point.point_object.concatenated_order_id
