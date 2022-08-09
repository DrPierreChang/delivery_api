from rest_framework import mixins, permissions, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404

from rest_framework_bulk import mixins as bulk_mixins

from base.permissions import IsDriverOrReadOnly
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from merchant.permissions import BarcodesEnabled
from reporting.context_managers import track_fields_on_change
from tasks.models import Order

from ..serializers import ScanningBarcodeSerializer
from ..serializers.barcode import (
    ScanningBarcodeAfterDelivery,
    ScanningBarcodeBeforeAndAfterDelivery,
    ScanningBarcodeBeforeDelivery,
)


class OrderBarcodesViewSet(ReadOnlyDBActionsViewSetMixin, mixins.ListModelMixin, bulk_mixins.BulkUpdateModelMixin,
                           viewsets.GenericViewSet):
    permission_classes = [UserIsAuthenticated, IsDriverOrReadOnly, BarcodesEnabled]
    serializer_class = ScanningBarcodeSerializer
    parent_lookup_field = 'order_order_id'

    def _get_related_object(self):
        parent_lookup = self.kwargs.get(self.parent_lookup_field)

        if self.request.version >= 2:
            order = get_object_or_404(Order, pk=parent_lookup)
        else:
            order = get_object_or_404(Order, order_id=parent_lookup)

        return order

    def get_queryset(self):
        order = self._get_related_object()
        return order.barcodes.all()

    def get_serializer_class(self):
        order = self._get_related_object()

        if self.request.method in permissions.SAFE_METHODS:
            return super(OrderBarcodesViewSet, self).get_serializer_class()

        if order.status in (order.PICK_UP, order.ASSIGNED, order.IN_PROGRESS):
            if order.merchant.enable_barcode_before_delivery and order.status in (order.PICK_UP, order.ASSIGNED):
                return ScanningBarcodeBeforeDelivery
            if order.merchant.enable_barcode_after_delivery and order.status == order.IN_PROGRESS:
                return ScanningBarcodeAfterDelivery
            if order.merchant.option_barcodes != order.merchant.TYPES_BARCODES.disable:
                return ScanningBarcodeBeforeAndAfterDelivery

        raise ValidationError(detail={'non_field_errors': ['Cannot scan barcode with current order status']})

    def bulk_update(self, request, *args, **kwargs):
        instance = self._get_related_object()
        with track_fields_on_change(instance, initiator=request.user):
            return super(OrderBarcodesViewSet, self).bulk_update(request, *args, **kwargs)
