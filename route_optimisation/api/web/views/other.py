from rest_framework import mixins, viewsets

from django_filters.rest_framework import DjangoFilterBackend

from base.permissions import IsAdminOrManagerOrObserver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from route_optimisation.models import DriverRouteLocation, OptimisationTask

from ...permissions import RouteOptimisationEnabled
from ..filters import DriverRouteLocationFilter
from ..serializers import DriverRouteLocationSerializer, OptimisationTaskSerializer


class OptimisationTaskViewSet(ReadOnlyDBActionsViewSetMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = OptimisationTask.objects.all()
    serializer_class = OptimisationTaskSerializer
    permission_classes = [UserIsAuthenticated, IsAdminOrManagerOrObserver, RouteOptimisationEnabled]


class DriverRouteLocationViewSet(ReadOnlyDBActionsViewSetMixin,
                                 mixins.ListModelMixin,
                                 mixins.RetrieveModelMixin,
                                 viewsets.GenericViewSet):
    queryset = DriverRouteLocation.objects.all()
    serializer_class = DriverRouteLocationSerializer
    permission_classes = [UserIsAuthenticated, IsAdminOrManagerOrObserver, RouteOptimisationEnabled]
    filter_backends = (DjangoFilterBackend,)
    filterset_class = DriverRouteLocationFilter
