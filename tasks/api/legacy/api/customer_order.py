from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from base.utils.views import ReadOnlyDBActionsViewSetMixin
from driver.api.legacy.serializers.location import DriverLocationSerializer
from reporting.decorators import log_fields_on_object
from reporting.models import Event
from tasks.mixins.order_status import OrderStatus
from tasks.models import ConcatenatedOrder, Order

from ..serializers import CustomerOrderSerializer, CustomerOrderStatsSerializer
from .customer import CustomerViewSet, PickupViewSet
from .mixins import CurrentLocationMixin, ObjectByUIDB64ApiBase


class BaseCustomerOrderViewSet(ReadOnlyDBActionsViewSetMixin,
                               mixins.RetrieveModelMixin,
                               mixins.ListModelMixin,
                               CurrentLocationMixin,
                               ObjectByUIDB64ApiBase):
    queryset = Order.aggregated_objects.all().order_by('-created_at')
    serializer_class = CustomerOrderSerializer
    location_serializer_class = DriverLocationSerializer
    lookup_field = 'order_token'

    def get_queryset(self):
        return super(BaseCustomerOrderViewSet, self).get_queryset().select_related(
            'pickup_address', 'deliver_address', 'driver__last_location', 'driver__car',
            'manager', 'merchant', 'sub_branding'
        ).prefetch_related('skill_sets',)

    def get_object(self):
        order = super().get_object()
        if order.is_concatenated_order:
            order.__class__ = ConcatenatedOrder
        return order

    @action(methods=['get'], detail=True)
    def stats(self, request, **kwargs):
        instance = self.get_object()
        try:
            last_event_id = int(request.query_params.get('last_event', 0))
            last_location_id = int(request.query_params.get('last_location', 0))
        except ValueError:
            raise APIException('Parameters should be integer type.')

        data = {'order': instance}

        events = self._get_related_events(instance)
        if events.filter(id__gt=last_event_id).exists():
            data['history'] = events

        driver = instance.driver
        if driver and driver.last_location_id and driver.last_location.id > last_location_id and driver.current_path:
            data['route'] = driver.current_path

        message = self._get_message(instance)
        if message:
            data['message'] = message

        return Response(data=CustomerOrderStatsSerializer(data, context=self.get_serializer_context()).data)

    def _get_related_events(self, instance):
        raise NotImplementedError()

    def _get_message(self, instance):
        raise NotImplementedError()


class CustomerOrderViewSet(BaseCustomerOrderViewSet):
    uidb64_lookup_viewset = CustomerViewSet

    def filter_queryset(self, queryset):
        return super(CustomerOrderViewSet, self).filter_queryset(queryset).filter(customer_id=self._object_id)

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'customer_type': 'deliver'}

    @action(methods=['put', 'patch'], detail=True)
    @log_fields_on_object(fields=['is_confirmed_by_customer'])
    def confirmation(self, request, **kwargs):
        instance = self.get_object()

        data = request.data
        if isinstance(data, dict):
            data.update({'is_confirmed_by_customer': True})
        else:
            data = {'is_confirmed_by_customer': True}

        serializer = self.get_serializer(
            instance,
            data=data,
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        instance.handle_customer_rating()

        return Response(data=serializer.data, status=status.HTTP_200_OK)

    def _get_related_events(self, instance):
        return Event.objects.customer_tracking(instance, OrderStatus.status_groups.TRACKABLE)

    def _get_message(self, instance):
        return instance.get_message_to_customer()


class PickupOrderViewSet(BaseCustomerOrderViewSet):
    uidb64_lookup_viewset = PickupViewSet

    def filter_queryset(self, queryset):
        return super(PickupOrderViewSet, self).filter_queryset(queryset).filter(pickup_id=self._object_id)

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'customer_type': 'pickup'}

    def _get_related_events(self, instance):
        return Event.objects.pickup_tracking(instance, OrderStatus.status_groups.PICKUP_TRACKABLE)

    def _get_message(self, instance):
        return instance.get_message_to_pickup()
