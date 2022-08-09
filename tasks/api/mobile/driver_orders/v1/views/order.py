from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend
from rest_condition import Or

from base.permissions import IsDriver, IsReadOnly
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from merchant.models import SkillSet
from merchant.permissions import BarcodesEnabled, ConfirmationDocumentEnabled, IsNotBlocked
from reporting.decorators import log_fields_on_object
from reporting.mixins import TrackableCreateModelMixin
from tasks.models import Order
from tasks.permissions import CanDriverCreateOrder
from tasks.push_notification.push_messages.order_change_status_composers import AssignedMessage
from tasks.utils.events import create_document_event

from ....filters.v1 import OrderFilterSet
from ..serializers import (
    BarcodeMultipleOrdersSerializer,
    CreateDriverOrderConfirmationDocumentSerializer,
    DriverOrderCreateSerializer,
    DriverOrderSerializer,
    ImageOrderSerializer,
    OrderPathSerializer,
    ScanBarcodesSerializer,
)
from ..serializers.order.geofence import OrderGeofenceSerializer


class OrderViewSet(
    ReadOnlyDBActionsViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    TrackableCreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    # UpdateModelMixin tracked by @log_fields_on_object

    queryset = Order.objects.all()

    permission_classes = [UserIsAuthenticated, IsNotBlocked, IsDriver, Or(IsReadOnly, CanDriverCreateOrder)]
    serializers = {
        'default': DriverOrderSerializer,
        'create': DriverOrderCreateSerializer,
    }

    filter_backends = (DjangoFilterBackend,)
    filterset_class = OrderFilterSet

    def get_queryset(self):
        qs = super().get_queryset().orders_with_archived_field().prefetch_for_mobile_api()
        qs = qs.filter(merchant=self.request.user.current_merchant)
        return qs.order_by_statuses(order_finished_equal=True) if not qs.ordered else qs

    def filter_queryset(self, qs):
        qs = super().filter_queryset(qs)

        user = self.request.user
        jobs_filter = Q(driver_id=user.id)

        if user.current_merchant.in_app_jobs_assignment:
            next_week_date = (timezone.now() + timezone.timedelta(days=settings.UNALLOCATED_ORDER_INTERVAL)).date()
            free_jobs_filter = Q(
                driver__isnull=True,
                deliver_before__date__lte=next_week_date,
                deliver_before__gte=timezone.now(),
                status=Order.NOT_ASSIGNED,
            )

            if user.current_merchant.enable_skill_sets:
                exclude_skills = SkillSet.objects.exclude(drivers=user).filter(merchant_id=user.current_merchant_id)
                free_jobs_filter &= ~Q(skill_sets__in=exclude_skills)

            jobs_filter |= free_jobs_filter

        return qs.filter(jobs_filter).distinct()

    def get_serializer_class(self):
        return self.serializers.get(self.action, self.serializers['default'])

    def perform_create(self, serializer):
        order = serializer.save()
        if order.driver:
            msg = AssignedMessage(driver=order.driver, order=order, initiator=self.request.user)
            order.driver.send_versioned_push(msg)

    @log_fields_on_object()
    def update(self, *args, **kwargs):
        kwargs['partial'] = True
        return super().update(*args, **kwargs)

    @action(detail=True, methods=['patch'], permission_classes=[UserIsAuthenticated, IsDriver])
    def upload_images(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ImageOrderSerializer(instance, data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        serializer.save()
        for field in ['pick_up_confirmation_photos', 'pre_confirmation_photos', 'order_confirmation_photos']:
            instance._prefetched_objects_cache.pop(field, None)

        return Response(data=self.get_serializer(instance).data)

    @action(detail=True, methods=['patch'],
            permission_classes=[UserIsAuthenticated, IsDriver, ConfirmationDocumentEnabled])
    def upload_confirmation_document(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = CreateDriverOrderConfirmationDocumentSerializer(
            data=request.data,
            context={'request': request, 'order': instance},
        )
        serializer.is_valid(raise_exception=True)
        document = serializer.save()
        create_document_event(self.request.user, instance, document)
        instance._prefetched_objects_cache.pop('order_confirmation_documents', None)

        return Response(data=self.get_serializer(instance).data)

    @action(detail=False, methods=['post'], permission_classes=[UserIsAuthenticated, IsDriver, BarcodesEnabled])
    def scan_barcodes(self, request, **kwargs):
        barcodes_serializers = ScanBarcodesSerializer(data=request.data, context=self.get_serializer_context())
        barcodes_serializers.is_valid(raise_exception=True)
        # tracking fields inside a scan_barcode_multiple_orders
        orders = barcodes_serializers.scan_barcode_multiple_orders(request.user)
        return Response(data=BarcodeMultipleOrdersSerializer(orders.all(), many=True).data)

    @log_fields_on_object()
    @action(detail=True, methods=['post'], permission_classes=[UserIsAuthenticated, IsDriver, BarcodesEnabled],
            url_path='scan_barcodes')
    def scan_order_barcodes(self, request, **kwargs):
        instance = self.get_object()
        barcodes_serializers = ScanBarcodesSerializer(
            instance, data=request.data, context=self.get_serializer_context()
        )
        barcodes_serializers.is_valid(raise_exception=True)
        order = barcodes_serializers.scan_barcode_one_order()
        return Response(data=self.get_serializer(order).data)

    @action(detail=True, permission_classes=[UserIsAuthenticated, IsDriver])
    def path(self, request, **kwargs):
        instance = self.get_object()
        serializer = OrderPathSerializer(instance)
        return Response(data=serializer.data)

    @log_fields_on_object()
    @action(detail=True, methods=['patch'], permission_classes=[UserIsAuthenticated, IsDriver])
    def geofence(self, request, **kwargs):
        geofence_serializer = OrderGeofenceSerializer(self.get_object(), data=request.data,
                                                      context=self.get_serializer_context())
        geofence_serializer.is_valid(raise_exception=True)
        order = geofence_serializer.save()
        return Response(data=self.get_serializer(order).data)
