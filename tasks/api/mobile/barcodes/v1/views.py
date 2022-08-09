from datetime import timedelta

from django.db.models import Prefetch, Q
from django.utils import timezone

from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from base.permissions import IsDriver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from merchant.permissions import BarcodesEnabled, IsNotBlocked
from tasks.mixins.order_status import OrderStatus
from tasks.models import Barcode, Order

from .serializers import CommentBarcodeSerializer, ScanBarcodeSerializer, StatisticsSerializer


class BarcodeViewSet(ReadOnlyDBActionsViewSetMixin,
                     mixins.ListModelMixin,
                     mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin,
                     viewsets.GenericViewSet):
    queryset = Barcode.objects.all().order_by('-pk')

    permission_classes = [UserIsAuthenticated, IsNotBlocked, IsDriver, BarcodesEnabled]
    serializer_class = CommentBarcodeSerializer

    def get_today_range(self):
        today_start = timezone.now().astimezone(self.request.user.current_merchant.timezone)
        today_start = today_start.replace(hour=0, minute=0, second=0, microsecond=0)
        return today_start, today_start + timedelta(days=1)

    def get_queryset(self):
        return super().get_queryset().filter(
            order__driver=self.request.user,
            order__status__in=OrderStatus.status_groups.ACTIVE_DRIVER,
            order__deliver_before__range=self.get_today_range(),
        )

    def update(self, *args, **kwargs):
        kwargs['partial'] = True
        return super().update(*args, **kwargs)

    def get_stats_response(self):
        # Get orders
        orders_qs = Order.aggregated_objects.filter(
            status__in=OrderStatus.status_groups.ACTIVE_DRIVER,
            driver=self.request.user,
            deliver_before__range=self.get_today_range(),
        ).order_by('-deliver_before').distinct()

        # Exclude orders with empty barcodes
        if self.request.user.current_merchant.enable_concatenated_orders:
            orders_qs = orders_qs.exclude_concatenated_child().filter(
                Q(is_concatenated_order=False, barcodes__isnull=False)
                | Q(is_concatenated_order=True, orders__barcodes__isnull=False),
            )
        else:
            orders_qs = orders_qs.exclude_concatenated_head().filter(barcodes__isnull=False)

        orders_qs = orders_qs.select_related('customer', 'deliver_address', 'pickup_address')
        orders_qs = orders_qs.prefetch_related('barcodes', 'orders__barcodes')
        orders_qs = orders_qs.prefetch_related(
            Prefetch('in_driver_route_queue', to_attr=Order.in_driver_route_queue.cache_name),
            Prefetch('order_route_point', to_attr=Order.order_route_point.cache_name),
        )
        return Response(StatisticsSerializer(orders_qs, context=self.get_serializer_context()).data)

    @action(methods=['get'], detail=False)
    def statistics(self, request, **kwargs):
        return self.get_stats_response()

    @action(methods=['post'], detail=False)
    def scan(self, request, **kwargs):
        serializer = ScanBarcodeSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        serializer.scan_barcode()
        return self.get_stats_response()
