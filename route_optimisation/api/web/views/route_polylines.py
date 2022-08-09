from rest_framework import mixins, viewsets
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend
from rest_condition import Or

from base.permissions import IsAdminOrManagerOrObserver, IsReadOnly
from custom_auth.permissions import UserIsAuthenticated
from radaro_utils.permissions import IsAdminOrManager
from route_optimisation.models import DriverRoute, RouteOptimisation
from route_optimisation.utils.refresh_polylines import OptimisationRefreshPolylines

from ...permissions import RouteOptimisationEnabled
from ..filters import DriverRouteFilter
from ..serializers import DriverRoutePolylineSerializer, PolylineParamsSerializer


class RoutePolylinesViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = DriverRoute.objects.all().order_by('-id')
    serializer_class = DriverRoutePolylineSerializer
    permission_classes = [
        UserIsAuthenticated,
        IsAdminOrManagerOrObserver,
        Or(IsAdminOrManager, IsReadOnly),
        RouteOptimisationEnabled,
    ]
    filter_backends = (DjangoFilterBackend,)
    filterset_class = DriverRouteFilter

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.filter(optimisation__merchant=self.request.user.current_merchant)
        qs = qs.exclude(optimisation__state=RouteOptimisation.STATE.REMOVED)
        return qs.prefetch_related('points')

    def refresh_routes(self, routes, request):
        serializer = PolylineParamsSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        refresh = serializer.validated_data.get('refresh', serializer.AUTO)

        if refresh == serializer.NO:
            return routes

        routes_for_refresh = {}
        for one_route in routes:
            need_refresh = False
            if refresh == serializer.YES:
                need_refresh = True
            elif refresh == serializer.AUTO:
                point_list = [point for point in one_route.points.all().order_by('number') if point.active]
                for start_point, end_point in zip(point_list[:-1], point_list[1:]):
                    if start_point.path_polyline is None:
                        need_refresh = True
                    if start_point.next_point_id != end_point.id:
                        need_refresh = True

            if need_refresh:
                if one_route.optimisation_id not in routes_for_refresh:
                    routes_for_refresh[one_route.optimisation_id] = {
                        'optimisation': one_route.optimisation,
                        'routes': list()
                    }
                routes_for_refresh[one_route.optimisation_id]['routes'].append(one_route)

        for item in routes_for_refresh.values():
            OptimisationRefreshPolylines(item['optimisation']).refresh_polylines(item['routes'])
            for route in item['routes']:
                route.refresh_from_db()

        return routes

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            page = self.refresh_routes(page, request)
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
