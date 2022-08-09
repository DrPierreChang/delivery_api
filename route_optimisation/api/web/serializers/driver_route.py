from operator import attrgetter

from rest_framework import serializers

from driver.models import DriverLocation
from route_optimisation.api.web.serializers.route_point import RoutePointSerializer
from route_optimisation.const import RoutePointKind
from route_optimisation.models import DriverRoute


class DriverLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverLocation
        fields = ('location', )


class DriverRouteSerializer(serializers.ModelSerializer):
    points = serializers.SerializerMethodField()
    orders_count = serializers.SerializerMethodField()

    class Meta:
        model = DriverRoute
        fields = (
            'id', 'driver_id', 'total_time', 'driving_time', 'driving_distance',
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
        return RoutePointSerializer(points, many=True, context=self.context).data

    def get_orders_count(self, driver_route):
        order_points = driver_route.get_typed_route_points(RoutePointKind.DELIVERY)
        return len(order_points)
