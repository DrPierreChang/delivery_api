from operator import attrgetter

from django.contrib.contenttypes.models import ContentType

from rest_framework import serializers

from merchant.api.legacy.serializers.hubs import HubSerializer, HubSerializerV2
from merchant.models import Hub
from route_optimisation.api.legacy.serializers.location import DriverRouteLocationSerializer
from route_optimisation.const import OPTIMISATION_TYPES, RoutePointKind
from route_optimisation.models import DriverRoute, RoutePoint
from tasks.api.legacy.serializers import DriverOrderSerializer
from tasks.api.legacy.serializers.orders import DriverOrderSerializerV2


class RoutePointSerializer(serializers.ModelSerializer):
    point_type = serializers.CharField(source='point_content_type.model')
    point_object = serializers.SerializerMethodField()
    planned_arrival_after = serializers.SerializerMethodField()
    planned_arrival_before = serializers.SerializerMethodField()
    planned_arrival = serializers.SerializerMethodField()

    serializers_dict = {
        'default': {
            'order': DriverOrderSerializer,
            'hub': HubSerializer,
            'driverroutelocation': DriverRouteLocationSerializer,
        },
        2: {
            'hub': HubSerializerV2,
            'order': DriverOrderSerializerV2,
            'driverroutelocation': DriverRouteLocationSerializer,
        }
    }

    class Meta:
        model = RoutePoint
        fields = ('point_type', 'point_object', 'number', 'planned_arrival',
                  'planned_arrival_after', 'planned_arrival_before',)

    def get_point_object(self, route_point):
        model_type = route_point.point_content_type.model
        serializer_version = self.serializers_dict.get(self.context['request'].version,
                                                       self.serializers_dict['default'])
        serializer = serializer_version[model_type]
        return serializer(instance=route_point.point_object).data

    def get_planned_arrival_after(self, route_point):
        return serializers.DateTimeField().to_representation(route_point.planned_order_arrival_interval[0])

    def get_planned_arrival_before(self, route_point):
        return serializers.DateTimeField().to_representation(route_point.planned_order_arrival_interval[1])

    def get_planned_arrival(self, point):
        dt = point.start_time
        if dt is None:
            order = point.point_object
            dt = order.deliver_before
        return serializers.DateTimeField().to_representation(dt)


class LegacyDriverRouteSerializer(serializers.ModelSerializer):
    day = serializers.DateField(source='optimisation.day', read_only=True)
    relevant_for_days = serializers.SerializerMethodField()
    route_points_locations = serializers.SerializerMethodField()
    route_points_hubs = serializers.SerializerMethodField()
    route_points_orders = serializers.SerializerMethodField()
    start_time = serializers.SerializerMethodField()
    end_time = serializers.SerializerMethodField()
    start_hub = serializers.SerializerMethodField()
    end_hub = serializers.SerializerMethodField()
    start_location = serializers.SerializerMethodField()
    end_location = serializers.SerializerMethodField()
    is_individual = serializers.SerializerMethodField()
    optimization = serializers.PrimaryKeyRelatedField(read_only=True, source='optimisation')

    class Meta:
        model = DriverRoute
        fields = ('id', 'day', 'relevant_for_days', 'route_points_locations', 'route_points_hubs',
                  'route_points_orders', 'driving_time', 'driving_distance', 'start_time',
                  'end_time', 'start_hub', 'end_hub', 'start_location', 'end_location', 'is_individual', 'optimization')

    def __init__(self, *args, **kwargs):
        super(LegacyDriverRouteSerializer, self).__init__(*args, **kwargs)
        self._points = None

    def to_representation(self, driver_route):
        location_points = driver_route.get_typed_route_points(RoutePointKind.LOCATION)
        hub_points = driver_route.get_typed_route_points(RoutePointKind.HUB)
        deliveries_points = driver_route.get_typed_route_points(RoutePointKind.DELIVERY)
        points = hub_points + deliveries_points + location_points
        points = sorted(points, key=attrgetter('number'))
        # Number field should increase by 1 in legacy API. Because pickup points is not returning here.
        for number, point in zip(range(1, 1+len(points)), points):
            point.number = number
        self._points = {
            RoutePointKind.LOCATION: location_points,
            RoutePointKind.HUB: hub_points,
            RoutePointKind.DELIVERY: deliveries_points,
        }
        return super(LegacyDriverRouteSerializer, self).to_representation(driver_route)

    def get_route_points_locations(self, driver_route):
        location_points = self._points[RoutePointKind.LOCATION]
        return RoutePointSerializer(location_points, many=True, context=self.context).data

    def get_route_points_hubs(self, driver_route):
        hub_points = self._points[RoutePointKind.HUB]
        return RoutePointSerializer(hub_points, many=True, context=self.context).data

    def get_route_points_orders(self, driver_route):
        order_points = self._points[RoutePointKind.DELIVERY]
        return RoutePointSerializer(order_points, many=True, context=self.context).data

    def get_relevant_for_days(self, route):
        return [str(route.optimisation.day)]

    def get_is_individual(self, route):
        return route.optimisation.type == OPTIMISATION_TYPES.SOLO

    def get_start_time(self, route):
        return route.start_time and route.start_time.astimezone(route.driver.current_merchant.timezone).time()

    def get_end_time(self, route):
        return route.end_time and route.end_time.astimezone(route.driver.current_merchant.timezone).time()

    def get_start_hub(self, route):
        start_point = route.points.order_by('number').first()
        if start_point.point_content_type == ContentType.objects.get_for_model(Hub):
            return start_point.point_object_id
        return None

    def get_end_hub(self, route):
        end_point = route.points.order_by('number').last()
        if end_point.point_content_type == ContentType.objects.get_for_model(Hub):
            return end_point.point_object_id
        return None

    def get_start_location(self, route):
        return None

    def get_end_location(self, route):
        return None
