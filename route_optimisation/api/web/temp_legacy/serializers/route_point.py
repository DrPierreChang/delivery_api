from typing import Iterable

from rest_framework import serializers

from merchant.api.legacy.serializers.hubs import HubLocationSerializerV2
from merchant.models import Hub
from route_optimisation.const import RoutePointKind
from route_optimisation.models import DriverRouteLocation, RoutePoint
from routing.serializers.fields import LatLngLocation
from tasks.api.web.orders.serializers import ConcatenatedOrderSerializer, WebOrderSerializer


class LiteHubSerializer(serializers.ModelSerializer):
    location = HubLocationSerializerV2()

    class Meta:
        model = Hub
        fields = ('id', 'name', 'phone', 'location',)


class LiteDriverRouteLocationSerializer(serializers.ModelSerializer):
    location = LatLngLocation(required=True)

    class Meta:
        model = DriverRouteLocation
        fields = ('id', 'address', 'location',)


class ConcatRoutePoint:
    def __init__(self, route_point: RoutePoint, number):
        self.number = number
        self.route_points = [route_point]

    def __str__(self):
        return str(len(self.route_points))

    def __repr__(self):
        return '<ConcatRoutePoint of %s>' % str(self)

    def __getattr__(self, item):
        if item in ('route_points', 'number'):
            return super().__getattr__(item)
        if len(self.route_points) == 1:
            return getattr(self.route_points[0], item)
        if item in ('service_time', ):
            values = self._get_all_values(item)
            return sum(values)
        if item == 'end_time':
            return getattr(self.route_points[-1], item)
        return getattr(self.route_points[0], item)

    def _get_all_values(self, item):
        return [getattr(point, item) for point in self.route_points]

    def check_same_point(self, point: RoutePoint):
        last_point = self.route_points[-1]
        if last_point.point_kind != point.point_kind:
            return False
        if point.point_kind != RoutePointKind.PICKUP:
            return False

        object_from, object_to = last_point.point_object, point.point_object
        distance = object_from.pickup_address.distance_to(object_to.pickup_address)
        return distance == 0

    def concat(self, point: RoutePoint):
        self.route_points.append(point)


class RoutePointListSerializer(serializers.ListSerializer):
    def to_representation(self, data: Iterable[RoutePoint]):
        result = []
        prev_point = None
        number = 1

        for route_point in data:
            if prev_point is not None and prev_point.check_same_point(route_point):
                prev_point.concat(route_point)
                continue
            if prev_point is not None:
                result.append(prev_point)
                number += 1
            prev_point = ConcatRoutePoint(route_point, number)
        if prev_point is not None:
            result.append(prev_point)

        return super().to_representation(result)


class PointObjectSerializer(serializers.ModelSerializer):
    _serializers = {
        'hub': LiteHubSerializer,
        'order': WebOrderSerializer,
        'driverroutelocation': LiteDriverRouteLocationSerializer,
    }

    point_type = serializers.CharField(source='point_content_type.model')
    point_object = serializers.SerializerMethodField()
    concatenated_order = serializers.SerializerMethodField()

    class Meta:
        model = RoutePoint
        fields = (
            'id', 'point_type', 'point_object', 'concatenated_order',
        )

    def get_point_object(self, route_point):
        model_type = route_point.point_content_type.model
        serializer = self._serializers.get(model_type)
        return serializer(instance=route_point.point_object, context=self.context).data

    def get_concatenated_order(self, route_point):
        if route_point.point_content_type.model != 'order':
            return
        if not self.context['request'].user.current_merchant.enable_concatenated_orders:
            return
        order = route_point.point_object
        concatenated = order._self_concatenated if order.is_concatenated_order else order.concatenated_order
        return ConcatenatedOrderSerializer(instance=concatenated, context=self.context).data


class RoutePointSerializer(serializers.ModelSerializer):
    point = PointObjectSerializer(source='*')
    concatenated_objects = PointObjectSerializer(source='route_points', many=True)
    planned_arrival_after = serializers.SerializerMethodField()
    planned_arrival_before = serializers.SerializerMethodField()
    planned_arrival = serializers.SerializerMethodField()

    class Meta:
        model = RoutePoint
        fields = (
            'id', 'number', 'point_kind', 'point_object_id', 'point',
            'concatenated_objects',
            'service_time', 'driving_time', 'distance', 'start_time', 'end_time',
            'planned_arrival_after', 'planned_arrival_before', 'planned_arrival',
        )
        list_serializer_class = RoutePointListSerializer

    def get_planned_arrival_after(self, point):
        return serializers.DateTimeField().to_representation(point.planned_order_arrival_interval[0])

    def get_planned_arrival_before(self, point):
        return serializers.DateTimeField().to_representation(point.planned_order_arrival_interval[1])

    def get_planned_arrival(self, point):
        dt = point.start_time
        if dt is None:
            order = point.point_object
            dt = order.deliver_before
        return serializers.DateTimeField().to_representation(dt)
