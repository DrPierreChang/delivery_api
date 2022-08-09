from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from base.permissions import IsDriver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from documents.models import OrderConfirmationDocument
from merchant.permissions import BarcodesEnabled, ConfirmationDocumentEnabled, IsNotBlocked
from reporting.context_managers import track_fields_on_change
from reporting.decorators import log_fields_on_object
from tasks.models import ConcatenatedOrder
from tasks.signal_receivers.concatenated_order import co_auto_processing
from tasks.utils.events import create_document_event

from ...driver_orders.v1.serializers import CreateDriverOrderConfirmationDocumentSerializer, ImageOrderSerializer
from .serializers import (
    ConcatenatedOrderGeofenceSerializer,
    DriverConcatenatedOrderSerializer,
    ScanBarcodesConcatenatedOrderSerializer,
)


class ConcatenatedOrderViewSet(ReadOnlyDBActionsViewSetMixin,
                               mixins.RetrieveModelMixin,
                               mixins.UpdateModelMixin,
                               viewsets.GenericViewSet):
    # UpdateModelMixin tracked by @log_fields_on_object

    queryset = ConcatenatedOrder.objects.all()
    permission_classes = [UserIsAuthenticated, IsNotBlocked, IsDriver]
    serializer_class = DriverConcatenatedOrderSerializer

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset().filter(merchant=user.current_merchant)
        if self.action in ['retrieve']:
            qs = qs.prefetch_for_mobile_api()
        return qs

    @log_fields_on_object()
    def update(self, *args, offline_happened_at, **kwargs):
        kwargs['partial'] = True
        concatenated_order = self.get_object()
        orders = list(concatenated_order.orders.all())
        if orders:
            if offline_happened_at is not None:
                event_kwargs = {'happened_at': offline_happened_at}
            else:
                event_kwargs = {}
            with track_fields_on_change(orders, initiator=self.request.user, sender=co_auto_processing, **event_kwargs):
                return super().update(*args, **kwargs)
        else:
            return super().update(*args, **kwargs)

    @action(detail=True, methods=['patch'], permission_classes=[UserIsAuthenticated, IsNotBlocked, IsDriver])
    def upload_images(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ImageOrderSerializer(instance, data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(data=self.get_serializer(instance).data)

    @action(detail=True, methods=['patch'],
            permission_classes=[UserIsAuthenticated, IsNotBlocked, IsDriver, ConfirmationDocumentEnabled])
    def upload_confirmation_document(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = CreateDriverOrderConfirmationDocumentSerializer(
            data=request.data,
            context={'request': request, 'order': instance},
        )
        serializer.is_valid(raise_exception=True)
        document = serializer.save()

        create_document_event(self.request.user, instance, document)
        nested_documents = OrderConfirmationDocument.objects.filter(
            name=document.name, order__concatenated_order=instance
        ).select_related('order')
        for nested_document in nested_documents:
            create_document_event(self.request.user, nested_document.order, nested_document)

        return Response(data=self.get_serializer(instance).data)

    @action(detail=True, methods=['post'],
            permission_classes=[UserIsAuthenticated, IsNotBlocked, IsDriver, BarcodesEnabled])
    def scan_barcodes(self, request, **kwargs):
        barcodes_serializers = ScanBarcodesConcatenatedOrderSerializer(
            self.get_object(), data=request.data, context=self.get_serializer_context()
        )
        barcodes_serializers.is_valid(raise_exception=True)
        # tracking fields inside a scan_barcode_concatenated_order
        barcodes_serializers.scan_barcode_concatenated_order()

        return Response(data=self.get_serializer(self.get_object()).data)

    @log_fields_on_object()
    @action(detail=True, methods=['patch'], permission_classes=[UserIsAuthenticated, IsNotBlocked, IsDriver])
    def geofence(self, request, **kwargs):
        geofence_serializer = ConcatenatedOrderGeofenceSerializer(
            self.get_object(), data=request.data, context=self.get_serializer_context())
        geofence_serializer.is_valid(raise_exception=True)
        order = geofence_serializer.save()
        return Response(data=self.get_serializer(order).data)
