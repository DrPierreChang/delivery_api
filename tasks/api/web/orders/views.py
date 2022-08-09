from django.http import Http404
from django.utils import timezone

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend

from base.permissions import IsAdminOrManagerOrObserver
from custom_auth.permissions import UserIsAuthenticated
from merchant.permissions import ConcatenatedOrdersEnabled, IsNotBlocked
from reporting.context_managers import track_fields_on_change
from reporting.decorators import log_fields_on_object
from reporting.mixins import TrackableCreateModelMixin, TrackableDestroyModelMixin
from reporting.utils.delete import create_delete_event
from tasks.models import ConcatenatedOrder, Order
from tasks.push_notification.push_messages.event_composers import ConcatenatedOrderUngroupedMessage
from tasks.push_notification.push_messages.order_change_status_composers import AssignedMessage
from tasks.signal_receivers.concatenated_order import co_auto_processing

from ...mobile.filters.v1 import SearchFilterBackend
from ..filters import SortFilterBackend, WebOrderFilterSet
from ..utils import CountViewMixin
from .serializers import (
    AddedOrdersConcatenatedOrderSerializer,
    ConcatenatedOrderSerializer,
    CustomerCommentOrderSerializer,
    OrderDeadlineSerializer,
    OrderIDSerializer,
    OrderPathSerializer,
    RemoveOrdersConcatenatedOrderSerializer,
    ResetOrdersConcatenatedOrderSerializer,
    WebOrderSerializer,
)

LAST_CUSTOMER_COMMENTS_LENGTH = 10


class WebOrderViewSet(CountViewMixin,
                      TrackableCreateModelMixin,
                      mixins.UpdateModelMixin,
                      TrackableDestroyModelMixin,
                      mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet):
    queryset = Order.aggregated_objects.all()
    permission_classes = [UserIsAuthenticated, IsNotBlocked, IsAdminOrManagerOrObserver]
    serializer_class = None
    serializers = {
        'order_serializer': WebOrderSerializer,
        'concatenated_order_serializer': ConcatenatedOrderSerializer,
        'create_order_serializer': WebOrderSerializer,
    }

    filter_backends = (DjangoFilterBackend, SearchFilterBackend, SortFilterBackend)
    filterset_class = WebOrderFilterSet
    search_fields = (
        'customer__name', 'customer__email', 'customer__phone', 'deliver_address__address', 'deliver_address__location'
    )
    ordering_fields = [
        # ('<sort field>': ('<queryset field>',))
        ('statistics__created_at', 'created_at'),
        ('statistics__updated_at', 'updated_at'),
        ('statistics__duration', 'duration'),
        'order_id',
        'rating',
        ('status', ('sort_rate', 'sort_rate_inside_statuses')),
        ('driver__full_name', ('driver__first_name', 'driver__last_name')),
        'customer__name',
        'sub_branding__name',
    ]
    exclude_ordering_from_actions = ['count_items']

    status_fieldname_to_count = 'status'

    def get_queryset(self):
        queryset = Order.aggregated_objects.filter(merchant=self.request.user.current_merchant)
        if self.action in self.exclude_ordering_from_actions:
            return queryset
        return queryset.order_by_statuses(order_finished_equal=True)

    def get_object(self):
        order = super().get_object()
        if order.is_concatenated_order:
            order.__class__ = ConcatenatedOrder
        return order

    def get_serializer(self, instance=None, *args, **kwargs):
        if instance:
            if instance.is_concatenated_order:
                serializer_class = self.serializers['concatenated_order_serializer']
            else:
                serializer_class = self.serializers['order_serializer']
        else:
            serializer_class = self.serializers['create_order_serializer']

        kwargs['context'] = self.get_serializer_context()
        return serializer_class(instance=instance, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        # get order ids api
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.values('id', 'sort_rate', 'sort_rate_inside_statuses', 'is_concatenated_order')
        page_min_orders = self.paginate_queryset(queryset)

        # prefetch and serialize simple orders
        o_ids = [order['id'] for order in page_min_orders if not order['is_concatenated_order']]
        if o_ids:
            orders = Order.objects.all().filter(id__in=o_ids).prefetch_for_web_api()
            o_serializer = self.serializers['order_serializer']
            o_list = o_serializer(orders, many=True, context=self.get_serializer_context()).data
        else:
            o_list = []

        # prefetch and serialize concatenated orders
        co_ids = [order['id'] for order in page_min_orders if order['is_concatenated_order']]
        if co_ids:
            concatenated_orders = ConcatenatedOrder.objects.all().filter(id__in=co_ids).prefetch_for_web_api()
            co_serializer = self.serializers['concatenated_order_serializer']
            co_list = co_serializer(concatenated_orders, many=True, context=self.get_serializer_context()).data
        else:
            co_list = []

        # combine orders in sorted list
        aggregated_orders_list = o_list + co_list
        aggregated_orders_dict = {order['id']: order for order in aggregated_orders_list}
        sorted_aggregated_orders_list = [aggregated_orders_dict[order['id']] for order in page_min_orders]
        return self.get_paginated_response(sorted_aggregated_orders_list)

    def perform_destroy(self, instance):
        instance.safe_delete()
        if instance.is_concatenated_order and instance.driver:
            msg = ConcatenatedOrderUngroupedMessage(order=instance)
            instance.driver.send_versioned_push(msg)

    def perform_create(self, serializer):
        order = serializer.save()
        if order.driver:
            msg = AssignedMessage(driver=order.driver, order=order, initiator=self.request.user)
            order.driver.send_versioned_push(msg)

    @log_fields_on_object()
    def update(self, *args, **kwargs):
        kwargs['partial'] = True
        order = self.get_object()
        if order.is_concatenated_order:
            tr_orders = list(order.orders.all())
            with track_fields_on_change(tr_orders, initiator=self.request.user, sender=co_auto_processing):
                return super().update(*args, **kwargs)
        else:
            return super().update(*args, **kwargs)

    def get_pages(self, queryset, serializer_class, **kwargs):
        page = self.paginate_queryset(queryset)
        serializer = serializer_class(page, many=True, **kwargs)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=['get'])
    def path(self, request, **kwargs):
        instance = self.get_object()
        if instance.is_concatenated_order:
            raise Http404
        serializer = OrderPathSerializer(instance)
        return Response(data=serializer.data)

    @action(detail=False, methods=['get'])
    def ids(self, *args, **kwargs):
        orders = self.filter_queryset(self.get_queryset())
        return self.get_pages(orders, OrderIDSerializer, context=self.get_serializer_context())

    @action(detail=False, methods=['get'], permission_classes=[UserIsAuthenticated])
    def deadlines(self, *args, **kwargs):
        orders = self.filter_queryset(self.get_queryset())
        orders = orders.filter(status__in=Order.status_groups.ACTIVE, deliver_before__gt=timezone.now())
        orders = orders.order_by('deliver_before').distinct('deliver_before', 'id')
        return self.get_pages(orders, OrderDeadlineSerializer, context=self.get_serializer_context())

    @action(detail=False, methods=['get'])
    def last_customer_comments(self, request, **kwargs):
        orders = self.filter_queryset(self.get_queryset())
        orders = orders.filter(is_confirmed_by_customer=True).select_related('customer')
        orders = orders.order_by('-updated_at').distinct('updated_at', 'id')
        return Response(data=CustomerCommentOrderSerializer(orders[:LAST_CUSTOMER_COMMENTS_LENGTH], many=True).data)

    @action(detail=True, methods=['get', 'put', 'patch', 'delete'])
    def orders(self, request, **kwargs):
        instance = self.get_object()
        if not instance.is_concatenated_order:
            raise Http404

        if request.method == 'GET':
            return self.get_pages(
                instance.orders.all().prefetch_for_web_api().order_inside_concatenated(),
                self.serializers['order_serializer'], context=self.get_serializer_context(),
            )
        else:
            if request.method == 'PUT':
                serializer_class = ResetOrdersConcatenatedOrderSerializer
            elif request.method == 'DELETE':
                serializer_class = RemoveOrdersConcatenatedOrderSerializer
            else:  # request.method == 'PATCH'
                serializer_class = AddedOrdersConcatenatedOrderSerializer

            with track_fields_on_change(instance, initiator=self.request.user, sender=self):
                # aggregated orders events are tracked in update() serializer method
                update_serializer = serializer_class(
                    instance, data=request.data, context=self.get_serializer_context()
                )
                update_serializer.is_valid(raise_exception=True)
                self.perform_update(update_serializer)

            if instance.orders.count() == 0:
                create_delete_event(self, instance, request.user, request)
                self.perform_destroy(instance)
                return Response(status=status.HTTP_204_NO_CONTENT)

            serializer = self.get_serializer(instance, context=self.get_serializer_context())
            return Response(serializer.data)


class AvailableConcatenatedOrderViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [UserIsAuthenticated, IsNotBlocked, IsAdminOrManagerOrObserver, ConcatenatedOrdersEnabled]
    serializer_class = WebOrderSerializer
    parent_lookup_field = 'orders_pk'

    filter_backends = WebOrderViewSet.filter_backends
    filterset_class = WebOrderViewSet.filterset_class
    search_fields = WebOrderViewSet.search_fields

    @property
    def concatenated_order(self):
        parent_lookup = self.kwargs.get(self.parent_lookup_field)
        return get_object_or_404(ConcatenatedOrder, merchant=self.request.user.current_merchant, pk=parent_lookup)

    def get_queryset(self):
        orders = self.concatenated_order.available_orders.prefetch_for_web_api()
        return orders.order_by_statuses(order_finished_equal=True)
