from django.db.models import Prefetch

from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from django_filters.rest_framework import DjangoFilterBackend

from base.models import Member
from base.permissions import IsSubManager
from custom_auth.permissions import UserIsAuthenticated
from merchant.permissions import IsNotBlocked
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

from ...mobile.filters.v1 import OrderFilterSet
from ..orders.serializers.other import OrderPathSerializer
from .filters import SubBrandOrderSortingFilter
from .serializers import ShortSubManagerOrderSerializer, SubManagerOrderSerializer


class WebSubbrandOrderViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin, GenericViewSet):
    queryset = Order.objects.exclude(status=OrderStatus.NOT_ASSIGNED).order_by_statuses(order_finished_equal=True)

    permission_classes = [UserIsAuthenticated, IsSubManager, IsNotBlocked]
    serializers = {
        'default': ShortSubManagerOrderSerializer,
        'retrieve': SubManagerOrderSerializer,
    }

    filter_backends = (DjangoFilterBackend, SearchFilter, SubBrandOrderSortingFilter)
    filterset_class = OrderFilterSet

    search_fields = (
        'order_id', 'title', 'customer__name', 'customer__email', 'customer__phone',
        'deliver_address__address', 'pickup_address__address', 'driver__first_name', 'driver__last_name',
        'external_job__external_id',
    )
    ordering_fields = (
        ('deliver_before', 'deliver_before'),
        ('deliver_customer_name', 'customer__name',),
        ('driver_full_name', ('driver__first_name', 'driver__last_name')),
    )

    def get_serializer_class(self):
        return self.serializers.get(self.action, self.serializers['default'])

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset().filter(merchant_id=user.current_merchant_id, sub_branding_id=user.sub_branding_id)

        qs = qs.select_related('customer', 'pickup', 'deliver_address', 'pickup_address')
        drivers_qs = Member.drivers_with_statuses.all().select_related('last_location')
        qs = qs.prefetch_related(
            'labels', 'merchant',
            Prefetch('status_events', to_attr=Order.status_events.cache_name),
            Prefetch('in_delivery_time_queue', to_attr=Order.in_delivery_time_queue.cache_name),
            Prefetch('in_driver_route_queue', to_attr=Order.in_driver_route_queue.cache_name),
            Prefetch('order_route_point', to_attr=Order.order_route_point.cache_name),
            Prefetch('driver', queryset=drivers_qs),
        )
        return qs.distinct()

    @action(detail=True, methods=['get'])
    def path(self, request, **kwargs):
        instance = self.get_object()
        serializer = OrderPathSerializer(instance)
        return Response(data=serializer.data)
