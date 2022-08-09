from operator import attrgetter

from django.contrib.auth import get_user_model

from rest_framework import serializers

from base.api.legacy.serializers import CarSerializer
from driver.models import DriverLocation
from merchant.api.legacy.serializers.hubs import HubLocationSerializerV2
from merchant.models import Hub
from route_optimisation.const import RoutePointKind
from route_optimisation.models import DriverRoute, DriverRouteLocation, RoutePoint
from routing.serializers.fields import LatLngLocation
from tasks.api.legacy.serializers import BarcodeSerializer
from tasks.api.legacy.serializers.core import OrderLocationSerializerV2
from tasks.api.legacy.serializers.customers import CustomerSerializer, PickupSerializer
from tasks.models import Order


class LiteHubSerializer(serializers.ModelSerializer):
    location = HubLocationSerializerV2()

    class Meta:
        model = Hub
        fields = ('id', 'name', 'phone', 'location',)


class ExternalLiteOrderSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer()
    pickup = PickupSerializer(allow_null=True)
    deliver_address = OrderLocationSerializerV2()
    pickup_address = OrderLocationSerializerV2(allow_null=True)
    barcodes = BarcodeSerializer(many=True)
    external_id = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            'order_id', 'external_id', 'status',
            'customer', 'deliver_address', 'deliver_after', 'deliver_before',
            'pickup', 'pickup_address', 'pickup_after', 'pickup_before', 'barcodes',
        )

    def get_external_id(self, order):
        return order.external_job.external_id if order.external_job else None


class ExternalDriverRouteLocationSerializer(serializers.ModelSerializer):
    location = LatLngLocation(required=True)

    class Meta:
        model = DriverRouteLocation
        fields = ('id', 'address', 'location',)


class ExternalRoutePointSerializer(serializers.ModelSerializer):
    _serializers = {
        'hub': LiteHubSerializer,
        'order': ExternalLiteOrderSerializer,
        'driverroutelocation': ExternalDriverRouteLocationSerializer,
    }

    point_type = serializers.SerializerMethodField()
    point_object = serializers.SerializerMethodField()
    planned_arrival_after = serializers.SerializerMethodField()
    planned_arrival_before = serializers.SerializerMethodField()
    planned_arrival = serializers.SerializerMethodField()

    class Meta:
        model = RoutePoint
        fields = (
            'id', 'number', 'point_kind', 'point_type', 'point_object_id', 'point_object',
            'service_time', 'driving_time', 'distance', 'start_time', 'end_time',
            'planned_arrival_after', 'planned_arrival_before', 'planned_arrival',
            'utilized_capacity',
        )

    def get_point_type(self, route_point):
        if route_point.point_content_type:
            return route_point.point_content_type.model

    def get_point_object(self, route_point):
        if route_point.point_content_type:
            model_type = route_point.point_content_type.model
            serializer = self._serializers.get(model_type)
            return serializer(instance=route_point.point_object).data

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


class DriverLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverLocation
        fields = ('location', )


class ExternalSmallDriverSerializer(serializers.ModelSerializer):
    car = CarSerializer()
    last_location = DriverLocationSerializer(read_only=True)

    class Meta:
        model = get_user_model()
        fields = ('member_id', 'full_name', 'car', 'is_online', 'work_status', 'phone', 'thumb_avatar_100x100',
                  'status', 'last_location')


class ExternalDriverRouteSerializer(serializers.ModelSerializer):
    points = serializers.SerializerMethodField()
    orders_count = serializers.SerializerMethodField()
    driver = ExternalSmallDriverSerializer()

    class Meta:
        model = DriverRoute
        fields = (
            'id', 'driver', 'options', 'total_time', 'driving_time', 'driving_distance',
            'start_time', 'end_time', 'orders_count', 'points', 'color', 'state',
        )

    def get_points(self, driver_route):
        hub_points = driver_route.get_typed_route_points(RoutePointKind.HUB)
        deliveries_points = driver_route.get_typed_route_points(RoutePointKind.DELIVERY)
        pickups_points = driver_route.get_typed_route_points(RoutePointKind.PICKUP)
        location_points = driver_route.get_typed_route_points(RoutePointKind.LOCATION)
        breaks_points = driver_route.get_typed_route_points(RoutePointKind.BREAK)
        points = hub_points + deliveries_points + pickups_points + location_points + breaks_points
        points = sorted(points, key=attrgetter('number'))
        return ExternalRoutePointSerializer(points, many=True, context=self.context).data

    def get_orders_count(self, driver_route):
        order_points = driver_route.get_typed_route_points(RoutePointKind.DELIVERY)
        return len(order_points)
