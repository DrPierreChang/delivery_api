from operator import attrgetter

from rest_framework import serializers

from route_optimisation.models import DriverRoute, RoutePoint

from .route_point import RoutePointListSerializer


class RoutePointPolylineSerializer(serializers.ModelSerializer):
    active = serializers.BooleanField()

    class Meta:
        model = RoutePoint
        fields = ('id', 'number', 'point_kind', 'path_polyline', 'active', 'next_point_id')
        list_serializer_class = RoutePointListSerializer


class DriverRoutePolylineSerializer(serializers.ModelSerializer):
    points = serializers.SerializerMethodField()

    class Meta:
        model = DriverRoute
        fields = ('id', 'optimisation_id', 'points')

    def get_points(self, driver_route):
        points = sorted(driver_route.points.all(), key=attrgetter('number'))
        return RoutePointPolylineSerializer(points, many=True, context=self.context).data


class PolylineParamsSerializer(serializers.Serializer):
    YES = 'yes'
    NO = 'no'
    AUTO = 'auto'
    REFRESH_CHOICE = (
        (YES, 'Yes'),
        (NO, 'No'),
        (AUTO, 'Auto'),
    )
    refresh = serializers.ChoiceField(choices=REFRESH_CHOICE, default=AUTO)
