from ...v1.serializers.daily_jobs import DailyOptimisationRouteSerializer, DailyOrdersSerializer
from .route_points import V2RoutePointsSerializer


class V2DailyOptimisationRouteSerializer(DailyOptimisationRouteSerializer):
    points = V2RoutePointsSerializer(source='*')


class V2DailyOrdersSerializer(DailyOrdersSerializer):
    route_optimisations = V2DailyOptimisationRouteSerializer(many=True)
