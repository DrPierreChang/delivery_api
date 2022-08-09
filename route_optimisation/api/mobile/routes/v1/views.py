from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from base.permissions import IsDriver
from custom_auth.permissions import UserIsAuthenticated
from route_optimisation.api.permissions import RouteOptimisationEnabled
from route_optimisation.models import DriverRoute, RouteOptimisation

from .serializers import RefreshRouteSerializer


class DriverRouteViewSetV1(viewsets.GenericViewSet):
    queryset = DriverRoute.objects.all().select_related('optimisation')
    permission_classes = [UserIsAuthenticated, IsDriver, RouteOptimisationEnabled]

    def get_queryset(self):
        return super().get_queryset().filter(
            driver=self.request.user,
            optimisation__state__in=(RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING),
        )

    @action(methods=['post'], detail=True)
    def refresh(self, request, **kwargs):
        instance = self.get_object()
        serializer = RefreshRouteSerializer(instance, context=self.get_serializer_context())
        serializer.save()
        return Response()
