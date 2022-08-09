from rest_framework import mixins, viewsets

from base.permissions import IsDriver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from merchant.permissions import IsNotBlocked
from route_optimisation.api.mobile.v1.serializers import CreateRouteOptimisationSerializer, OptimisationTaskSerializer
from route_optimisation.api.permissions import RouteOptimisationEnabled
from route_optimisation.models import OptimisationTask, RouteOptimisation


class RouteOptimisationViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = RouteOptimisation.objects.all().order_by('-id')
    serializer_class = CreateRouteOptimisationSerializer
    permission_classes = [UserIsAuthenticated, IsNotBlocked, IsDriver, RouteOptimisationEnabled]


class OptimisationTaskViewSet(ReadOnlyDBActionsViewSetMixin,
                              mixins.RetrieveModelMixin,
                              viewsets.GenericViewSet):
    queryset = OptimisationTask.objects.all()
    serializer_class = OptimisationTaskSerializer
    permission_classes = [UserIsAuthenticated, IsDriver, RouteOptimisationEnabled]
