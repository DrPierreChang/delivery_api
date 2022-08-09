from django.contrib.contenttypes.models import ContentType

from rest_framework import decorators, mixins, status, viewsets
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend

from base.permissions import IsDriver
from base.utils import CustomPageNumberPagination
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from merchant.models import Hub
from tasks.models import Order

from ...celery_tasks import legacy_async_driver_push
from ...const import OPTIMISATION_TYPES
from ...models import DriverRoute, DriverRouteLocation, RouteOptimisation, RoutePoint
from ..permissions import RouteOptimisationEnabled
from .filters import DriverRouteFilter, LegacyStatusFilterBackend, RouteOptimisationFilter
from .serializers import LegacyCreateRouteOptimisationSerializer, LegacyReturnRouteOptimisationSerializer
from .serializers.route import LegacyDriverRouteSerializer


class RouteOptimisationViewSet(ReadOnlyDBActionsViewSetMixin,
                               mixins.ListModelMixin,
                               viewsets.GenericViewSet):
    serializer_class = LegacyReturnRouteOptimisationSerializer
    permission_classes = [UserIsAuthenticated, IsDriver, RouteOptimisationEnabled]
    queryset = RouteOptimisation.objects.all().order_by('-id')
    filter_backends = (DjangoFilterBackend, LegacyStatusFilterBackend)
    filterset_class = RouteOptimisationFilter

    def get_queryset(self):
        queryset = super().get_queryset()\
            .filter(merchant=self.request.user.current_merchant, created_by=self.request.user, type=OPTIMISATION_TYPES.SOLO)\
            .exclude(state=RouteOptimisation.STATE.REMOVED)
        return queryset

    def get_serializer_class(self):
        if self.action == 'individual':
            return LegacyCreateRouteOptimisationSerializer
        return super().get_serializer_class()

    @decorators.action(methods=['post'], detail=False)
    def individual(self, request, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        optimisation = serializer.save()
        return_serializer = LegacyReturnRouteOptimisationSerializer(optimisation, context=self.get_serializer_context())
        if optimisation.state == RouteOptimisation.STATE.FAILED:
            legacy_async_driver_push.apply_async(countdown=5, args=(optimisation.id,))
        return Response(return_serializer.data, status=status.HTTP_201_CREATED)


class DriverRoutePagination(CustomPageNumberPagination):
    page_size = 1


class DriverRouteViewSet(ReadOnlyDBActionsViewSetMixin,
                         mixins.ListModelMixin,
                         viewsets.GenericViewSet):
    queryset = DriverRoute.objects.all().order_by('-id')
    serializer_class = LegacyDriverRouteSerializer
    permission_classes = [UserIsAuthenticated, IsDriver, RouteOptimisationEnabled]
    filter_backends = (DjangoFilterBackend,)
    filterset_class = DriverRouteFilter
    pagination_class = DriverRoutePagination

    def get_queryset(self):
        qs = super().get_queryset()\
            .filter(driver=self.request.user)\
            .filter(optimisation__state__in=[RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING])\
            .filter(state__in=[DriverRoute.STATE.CREATED, DriverRoute.STATE.RUNNING])\
            .order_by('start_time')
        return self._legacy_prefetch(qs)

    def _legacy_prefetch(self, queryset):
        from django.db import models
        content_types = ContentType.objects.get_for_models(Order, Hub, DriverRouteLocation)
        hubs_qs = self._legacy_prefetch_for_content_type(content_types[Hub])
        orders_qs = self._legacy_prefetch_for_content_type(content_types[Order])
        locations_qs = self._legacy_prefetch_for_content_type(content_types[DriverRouteLocation])
        prefetch_locations = models.Prefetch(
            'points', to_attr=DriverRoute.get_prefetch_attr_name(DriverRouteLocation), queryset=locations_qs
        )
        prefetch_hubs = models.Prefetch(
            'points', to_attr=DriverRoute.get_prefetch_attr_name(Hub), queryset=hubs_qs
        )
        prefetch_orders = models.Prefetch(
            'points', to_attr=DriverRoute.get_prefetch_attr_name(Order), queryset=orders_qs
        )
        return queryset.prefetch_related(prefetch_hubs, prefetch_orders, prefetch_locations) \
            .select_related('driver__merchant', 'optimisation')

    def _legacy_prefetch_for_content_type(self, content_type):
        qs = RoutePoint.objects.filter(point_content_type=content_type).order_by('number')
        if content_type.model == 'hub':
            qs = qs.prefetch_related('point_object__location')
        elif content_type.model == 'order':
            from django.db.models import Prefetch
            order_prefetch_list = [
                'point_object__merchant', 'point_object__manager', 'point_object__customer',
                'point_object__pre_confirmation_photos', 'point_object__order_confirmation_photos',
                'point_object__labels', 'point_object__terminate_codes',
                'point_object__barcodes', 'point_object__skill_sets', 'point_object__starting_point',
                'point_object__ending_point', 'point_object__deliver_address', 'point_object__pickup_address',
                'point_object__wayback_point', 'point_object__pickup', 'point_object__pick_up_confirmation_photos',
                'point_object__order_confirmation_documents', 'point_object__external_job',
                Prefetch('point_object__order_route_point', to_attr=Order.order_route_point.cache_name),
                Prefetch('point_object__status_events', to_attr=Order.status_events.cache_name)
            ]
            qs = qs.prefetch_related(*order_prefetch_list)
        return qs
