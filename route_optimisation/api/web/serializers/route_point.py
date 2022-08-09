from collections import defaultdict
from typing import Iterable

from django.contrib.contenttypes.models import ContentType

from rest_framework import serializers

from merchant.models import Hub
from route_optimisation.const import RoutePointKind
from route_optimisation.models import DriverRouteLocation, RoutePoint


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
        if item in ('service_time',):
            values = self._get_all_values(item)
            return sum(values)
        if item == 'end_time':
            return getattr(self.route_points[-1], item)
        if item in ('next_point_id', 'path_polyline'):
            value = None
            for point in self.route_points:
                point_value = getattr(point, item)
                if point_value is not None:
                    value = point_value
            return value
        if item == 'active':
            return any(point.active for point in self.route_points)
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


class ObjectsIdsSerializer(serializers.Serializer):
    def to_representation(self, data):
        point_objects_ids = set()
        pickups_ids = defaultdict(list)
        points_ids = defaultdict(list)
        for route_point in data:
            if route_point.point_object_id is None:
                continue
            if self._is_hub_or_location(route_point):
                point_objects_ids.add(route_point.point_object_id)
                points_ids[route_point.point_object_id].append(route_point.id)
                continue
            self._get_ids_from_order(route_point, point_objects_ids, pickups_ids, points_ids)
        return self._prepare_result(point_objects_ids, pickups_ids, points_ids)

    def _get_ids_from_order(self, route_point, point_objects_ids, pickups_ids, points_ids):
        point_object_id = self._get_order_object_id(route_point)
        point_objects_ids.add(point_object_id)
        points_ids[point_object_id].append(route_point.id)
        if route_point.point_kind == RoutePointKind.PICKUP:
            pickups_ids[point_object_id].append(route_point.point_object_id)

    def _prepare_result(self, point_objects_ids, pickups_ids, points_ids):
        result = []
        for point_object_id in point_objects_ids:
            point = {'point_object_id': point_object_id, 'point_ids': points_ids[point_object_id]}
            if len(pickups_ids):
                point['pickup_ids'] = pickups_ids[point_object_id]
            result.append(point)
        return result

    def _get_order_object_id(self, route_point):
        order = route_point.point_object
        if order.merchant.enable_concatenated_orders:
            point_object_id = order.id if order.is_concatenated_order else order.concatenated_order_id
        else:
            point_object_id = order.id
        return point_object_id or order.id

    def _is_hub_or_location(self, route_point):
        ct = ContentType.objects.get_for_models(DriverRouteLocation, Hub)
        return route_point.point_content_type in ct.values()


class RoutePointSerializer(serializers.ModelSerializer):
    objects_ids = ObjectsIdsSerializer(source='route_points')
    planned_arrival_after = serializers.SerializerMethodField()
    planned_arrival_before = serializers.SerializerMethodField()
    planned_arrival = serializers.SerializerMethodField()

    class Meta:
        model = RoutePoint
        fields = (
            'id', 'number', 'point_kind', 'objects_ids',
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
