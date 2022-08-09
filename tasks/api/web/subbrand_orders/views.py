from django.db.models import Prefetch

from rest_framework import mixins
from rest_framework.filters import SearchFilter
from rest_framework.viewsets import GenericViewSet

from django_filters.rest_framework import DjangoFilterBackend

from base.models import Member
from base.permissions import IsSubManager
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from merchant.permissions import IsNotBlocked
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

from ...mobile.filters.v1 import OrderFilterSet
from .filters import SubBrandOrderSortingFilter
from .serializers import ListSubManagerOrderSerializer, SubManagerOrderSerializer


class SubbrandOrderViewSet(ReadOnlyDBActionsViewSetMixin,
                           mixins.RetrieveModelMixin,
                           mixins.ListModelMixin,
                           GenericViewSet):
    queryset = Order.objects.exclude(status=OrderStatus.NOT_ASSIGNED).order_by_statuses()

    permission_classes = [UserIsAuthenticated, IsSubManager, IsNotBlocked]
    serializers = {
        'default': ListSubManagerOrderSerializer,
        'retrieve': SubManagerOrderSerializer,
        'list': ListSubManagerOrderSerializer,
    }

    filter_backends = (DjangoFilterBackend, SearchFilter, SubBrandOrderSortingFilter)
    filterset_class = OrderFilterSet

    search_fields = (
        'order_id', 'title', 'customer__name', 'customer__email', 'customer__phone',
        'deliver_address__address', 'pickup_address__address', 'driver__first_name', 'driver__last_name',
        'external_job__external_id',
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
        qs = super().get_queryset().filter(merchant_id=user.current_merchant_id, sub_branding_id=user.sub_branding_id)

        qs = qs.select_related('customer', 'deliver_address', 'pickup_address').prefetch_related('labels')
        drivers_qs = Member.drivers_with_statuses.all().select_related('last_location')
        qs = qs.prefetch_related(
            Prefetch('status_events', to_attr=Order.status_events.cache_name),
            Prefetch('in_delivery_time_queue', to_attr=Order.in_delivery_time_queue.cache_name),
            Prefetch('in_driver_route_queue', to_attr=Order.in_driver_route_queue.cache_name),
            Prefetch('driver', queryset=drivers_qs),
        )
        return qs.distinct()
