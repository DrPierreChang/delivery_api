from django.db.models import Prefetch, Q

from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from django_filters.rest_framework import DjangoFilterBackend

from base.models import Member
from base.permissions import IsGroupManager
from custom_auth.permissions import UserIsAuthenticated
from merchant.permissions import IsNotBlocked
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

from ..orders.serializers import OrderPathSerializer
from ..subbrand_orders_dev.filters import SubBrandOrderSortingFilter
from ..subbrand_orders_dev.serializers import SubManagerOrderSerializer
from .filters import GroupMerchantFilter, GroupOrderFilterSet
from .serializers import ShortGroupSubManagerOrderSerializer


class WebGroupOrdersViewSet(mixins.RetrieveModelMixin,
                            mixins.ListModelMixin,
                            GenericViewSet):

    queryset = Order.objects.exclude(status=OrderStatus.NOT_ASSIGNED).order_by_statuses(order_finished_equal=True)

    permission_classes = (UserIsAuthenticated, IsGroupManager, IsNotBlocked)

    filter_backends = (DjangoFilterBackend, SearchFilter, SubBrandOrderSortingFilter, GroupMerchantFilter)
    filterset_class = GroupOrderFilterSet

    serializers = {
        'default': ShortGroupSubManagerOrderSerializer,
        'retrieve': SubManagerOrderSerializer,
        'list': ShortGroupSubManagerOrderSerializer,
    }

    search_fields = (
        'order_id', 'title', 'customer__name', 'customer__email', 'customer__phone',
        'deliver_address__address', 'pickup_address__address', 'driver__first_name', 'driver__last_name',
        'external_job__external_id', 'merchant__name'
    )
    ordering_fields = (
        'deliver_before',
        'customer__name',
        ('driver__full_name', ('driver__first_name', 'driver__last_name')),
    )

    def get_serializer_class(self):
        return self.serializers.get(self.action, self.serializers['default'])

    def get_queryset(self):
        user = self.request.user

        group_filter = Q(merchant_id__in=user.merchants.all().values_list('id', flat=True), sub_branding__isnull=True)
        exclude_condition = Q()
        if user.sub_brandings.exists():
            group_filter |= Q(sub_branding_id__in=user.sub_brandings.all().values_list('id', flat=True))
            if user.show_only_sub_branding_jobs:
                exclude_merchants = user.sub_brandings.all().values_list('merchant_id', flat=True)
                exclude_condition |= Q(merchant_id__in=exclude_merchants, sub_branding__isnull=True)

        qs = super().get_queryset().filter(group_filter).exclude(exclude_condition)

        qs = qs.select_related('customer', 'deliver_address', 'pickup', 'pickup_address')
        qs = qs.prefetch_related('labels', 'merchant', 'sub_branding')
        drivers_qs = Member.drivers_with_statuses.all().select_related('last_location')
        qs = qs.prefetch_related(
            Prefetch('status_events', to_attr=Order.status_events.cache_name),
            Prefetch('in_delivery_time_queue', to_attr=Order.in_delivery_time_queue.cache_name),
            Prefetch('in_driver_route_queue', to_attr=Order.in_driver_route_queue.cache_name),
            Prefetch('driver', queryset=drivers_qs),
        )
        return qs.distinct()

    @action(detail=True, methods=['get'])
    def path(self, request, **kwargs):
        instance = self.get_object()
        serializer = OrderPathSerializer(instance)
        return Response(data=serializer.data)
