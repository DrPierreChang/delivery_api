import operator
from collections import Counter
from functools import reduce

from django.conf import settings
from django.db.models import Prefetch, Q
from django.utils import timezone

from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend

from base.models import Member
from base.permissions import IsAdminOrManagerOrObserver, IsDriver, IsManagerOrReadOnly
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from merchant.models import SkillSet
from merchant.permissions import BarcodesEnabled, ConfirmationDocumentEnabled, IsNotBlocked
from reporting.decorators import log_fields_on_object
from reporting.mixins import TrackableCreateModelMixin, TrackableDestroyModelMixin, TrackableUpdateModelMixin
from reporting.signals import create_event
from reporting.utils.report import get_request_params
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order
from tasks.permissions import CanCreateOrder
from tasks.push_notification.push_messages.event_composers import ChecklistMessage
from tasks.push_notification.push_messages.order_change_status_composers import AssignedMessage
from tasks.utils.events import create_document_event

from ..filters import OrderFilterSet, StatusGroupFilterBackend
from ..serializers.barcode import ScanBarcodesCodeDataSerializer
from ..serializers.core import (
    CommentOrderSerializer,
    OrderAssignTimeSerializer,
    OrderPathSerializer,
    OrderTableSerializer,
    OrderWaybackTimeSerializer,
)
from ..serializers.documents import CreateOrderConfirmationDocumentSerializer, OrderConfirmationDocumentSerializer
from ..serializers.orders import (
    BarcodeInformationSerializer,
    DriverCreateOrderSerializer,
    DriverCreateOrderSerializerV2,
    DriverOrderSerializer,
    DriverOrderSerializerV2,
    GeofenceEnteredRequestSerializer,
    ListOrderSerializerV2,
    OrderDeadlineSerializer,
    OrderIDSerializer,
    OrderSerializer,
    OrderSerializerV2,
    RetrieveOrderSerializer,
    RetrieveOrderSerializerV2,
    WaybackPointSerializer,
)
from .mixins import CurrentLocationMixin


# TODO: Split on driver's and manager's viewsets
class OrderViewSet(ReadOnlyDBActionsViewSetMixin,
                   mixins.RetrieveModelMixin,
                   TrackableUpdateModelMixin,
                   TrackableDestroyModelMixin,
                   mixins.ListModelMixin,
                   TrackableCreateModelMixin,
                   CurrentLocationMixin):
    lookup_field = 'order_id'
    LAST_COMMENTS_LENGTH = 10

    queryset = Order.objects.all()

    permission_classes = [UserIsAuthenticated, IsManagerOrReadOnly, IsNotBlocked]
    serializers = {
        'default': {
            'retrieve': RetrieveOrderSerializer,
            'list': RetrieveOrderSerializer,
            'default': OrderSerializer,
            'active': RetrieveOrderSerializer,
            '_driver': DriverOrderSerializer,
            '_driver_create': DriverCreateOrderSerializer,
            'search': RetrieveOrderSerializer
        },
        2: {
            'retrieve': RetrieveOrderSerializerV2,
            'list': ListOrderSerializerV2,
            'default': OrderSerializerV2,
            'active': ListOrderSerializerV2,
            '_driver': DriverOrderSerializerV2,
            '_driver_create': DriverCreateOrderSerializerV2,
            'search': ListOrderSerializerV2
        }
    }

    filter_backends = (DjangoFilterBackend, StatusGroupFilterBackend)
    filterset_class = OrderFilterSet

    driver_select_related = ('manager', 'customer', 'deliver_address', 'starting_point', 'merchant', 'ending_point',
                             'pickup_address', 'wayback_point', 'wayback_hub__location', 'pickup')
    manager_select_related = ('driver', 'deliver_address', 'pickup_address', 'starting_point', 'customer', 'manager',
                              'bulk', 'driver__merchant', 'driver__car', 'merchant', 'ending_point', 'pickup')
    manager_select_related_for_list = ('deliver_address', 'pickup_address', 'customer', 'bulk', 'starting_point',
                                       'wayback_point', 'wayback_hub__location', 'pickup')
    common_prefetch_related = ('terminate_codes', 'labels', 'barcodes', 'skill_sets', 'skids',
                               Prefetch('status_events', to_attr=Order.status_events.cache_name),)
    manager_prefetch_related = common_prefetch_related
    driver_prefetch_related = common_prefetch_related \
                              + ('driver_checklist__confirmation_photos',
                                 'order_confirmation_documents', 'pick_up_confirmation_photos',
                                 'pre_confirmation_photos', 'order_confirmation_photos',
                                 Prefetch('order_route_point', to_attr=Order.order_route_point.cache_name),)
    search_fields = ('order_id', 'title', 'description', 'comment', 'customer__name', 'customer__email',
                     'customer__phone', 'deliver_address__address', 'deliver_address__location')

    archive_flag = 'archived'

    def get_queryset(self):
        return self._sort_queryset(self._get_queryset())

    def _sort_queryset(self, qs):
        driver = None
        if self.request.method == 'GET' and self.action in ['list', 'jobs_sorting']:
            drivers_param = self.request.GET.getlist('driver')
            if self.request.user.is_driver:
                driver = self.request.user
            elif len(drivers_param) == 1:
                driver = Member.objects.filter(id=drivers_param[0]).select_related('merchant').first()
        if driver:
            status_in_active = set().union(self.request.GET.getlist('group'),
                                           self.request.GET.getlist('status')). \
                intersection(set(OrderStatus.status_groups.UNFINISHED))
            group_is_active = self.request.query_params.get('group', '') == 'active'
            if status_in_active or group_is_active:
                qs = qs.order_active_orders_for_driver()
            elif self.archive_flag in self.request.GET.getlist('group'):
                qs = qs.order_by('-updated_at').distinct('updated_at', 'id')
            else:
                qs = qs.order_by_statuses()
        else:
            qs = qs.order_by_statuses()
        return qs

    def _get_queryset(self):
        user = self.request.user
        qs = self.queryset.filter(merchant=user.current_merchant).distinct()

        if user.is_driver:
            jobs_filter = Q(driver=user)

            if user.current_merchant.in_app_jobs_assignment:
                next_week_date = (timezone.now() + timezone.timedelta(days=settings.UNALLOCATED_ORDER_INTERVAL)).date()
                free_jobs_filter = Q(driver_id__isnull=True,
                                     status=Order.NOT_ASSIGNED,
                                     deadline_notified=False,
                                     deliver_before__date__lte=next_week_date)
                if user.current_merchant.enable_skill_sets:
                    # chosen set of skills that the driver DOES NOT own
                    exclude_skills = SkillSet.objects.exclude(drivers=user)
                    # here are filtered orders requiring skills that the driver does not own
                    free_jobs_filter &= ~Q(skill_sets__in=exclude_skills)
                jobs_filter |= free_jobs_filter

            qs = qs.filter(jobs_filter)

        if self.request.method != 'GET':
            return qs

        if user.is_driver:
            if self.action in ['list', 'jobs_sorting']:
                qs = qs.orders_with_archived_field()
            qs = qs \
                .prefetch_related(*self.driver_prefetch_related) \
                .select_related(*self.driver_select_related)
        else:
            if self.action != 'retrieve':
                qs = self.filter_queryset(qs.order_by_statuses()) \
                    .select_related(*self.manager_select_related_for_list)
            qs = qs \
                .select_related(*self.manager_select_related) \
                .prefetch_related(*self.manager_prefetch_related)
        return qs

    def get_object(self):
        if self.request.version >= 2:
            self.kwargs['pk'] = self.kwargs['order_id']
            self.lookup_field = 'pk'
        return super(OrderViewSet, self).get_object()

    def get_serializer_class(self):
        serializer_version = self.serializers.get(self.request.version, self.serializers['default'])
        is_driver = self.request.user.is_driver
        if is_driver:
            action = '_driver' if not self.action == 'create' else '_driver_create'
        else:
            action = self.action
        return serializer_version.get(action, serializer_version['default'])

    def perform_destroy(self, instance):
        instance.safe_delete()

    def perform_create(self, serializer):
        obj = serializer.save(manager=self.request.user, merchant=self.request.user.current_merchant)
        if obj.driver:
            msg = AssignedMessage(driver=obj.driver, order=obj, initiator=self.request.user)
            obj.driver.send_versioned_push(msg)

    def get_pages(self, queryset, serializer_class, **kwargs):
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = serializer_class(page, many=True, **kwargs)
            return self.get_paginated_response(serializer.data)

        serializer = serializer_class(queryset, many=True, **kwargs)
        return Response(serializer.data)

    def get_permissions(self):
        if self.action in ['create', ]:
            self.permission_classes = [UserIsAuthenticated, CanCreateOrder, IsNotBlocked]
        return super(OrderViewSet, self).get_permissions()

    @action(methods=['get'], detail=False, permission_classes=[UserIsAuthenticated, IsAdminOrManagerOrObserver])
    def count_items(self, request, *args, **kwargs):
        queryset = self.queryset.filter(merchant=request.user.current_merchant)
        status_counter = Counter(queryset.values_list('status', flat=True))
        status_counter['active'] = queryset.filter(status__in=OrderStatus.status_groups.ACTIVE).count()
        result = dict({st: 0 for st in OrderStatus.status_groups.ALL}, **status_counter)
        return Response(data=result)

    @action(methods=['get'], detail=False, permission_classes=[UserIsAuthenticated, IsAdminOrManagerOrObserver])
    def active(self, request, *args, **kwargs):
        qp = {'group': 'active'}
        qp.update(request.GET)
        request.GET = qp
        return self.list(request, *args, **kwargs)

    @action(methods=['put'], detail=True, permission_classes=[UserIsAuthenticated, IsDriver])
    @log_fields_on_object(fields=['driver', 'status'])
    def status(self, request, order_id=None, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if any([item in request.data for item in ('terminate_code', 'error_code', 'terminate_codes')]):
            instance.handle_termination_code()
        instance.handle_confirmation()

        return Response(data=serializer.data)

    @action(detail=True, permission_classes=[UserIsAuthenticated, IsManagerOrReadOnly])
    def path(self, request, **kwargs):
        instance = self.get_object()
        serializer = OrderPathSerializer(instance)
        return Response(data=serializer.data)

    @action(detail=True, permission_classes=[UserIsAuthenticated, IsManagerOrReadOnly])
    def assign_time(self, request, **kwargs):
        instance = self.get_object()
        return Response(OrderAssignTimeSerializer({'assign_time': instance.assigned_at}).data)

    @action(detail=True, permission_classes=[UserIsAuthenticated, IsManagerOrReadOnly])
    def wayback_time(self, request, **kwargs):
        instance = self.get_object()
        return Response(OrderWaybackTimeSerializer({'wayback_time': instance.wayback_at}).data)

    @action(detail=True, methods=['put', 'patch'], permission_classes=[UserIsAuthenticated, IsDriver])
    @log_fields_on_object()
    def wayback_point(self, request, **kwargs):
        instance = self.get_object()
        wayback_point_serializer = WaybackPointSerializer(instance=instance, data=request.data, partial=True,
                                                          context={'request': request})
        wayback_point_serializer.is_valid(raise_exception=True)
        wayback_point_serializer.save()
        wayback_point_serializer.instance.calculate_wayback_distance()
        return Response(data=wayback_point_serializer.data)

    @action(detail=True, methods=['put', 'patch'], permission_classes=[UserIsAuthenticated, IsDriver])
    @log_fields_on_object(fields=['geofence_entered', 'status'])
    def geofence(self, request, **kwargs):
        instance = self.get_object()
        geofence_entered_serializer = GeofenceEnteredRequestSerializer(instance.status, data=request.data)
        geofence_entered_serializer.is_valid(raise_exception=True)

        serializer = self.get_serializer(
            instance,
            data=geofence_entered_serializer.validated_data,
            context={'request': request},
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        # If driver has to complete checklist we should notify him when he enters geofence area
        if all([serializer.validated_data.get('geofence_entered'),
                order.driver_checklist,
                not order.driver_checklist_passed,
                not serializer.validated_data.get('changed_in_offline', False)]):
            request.user.send_versioned_push(ChecklistMessage(order))

        return Response(data=serializer.data)

    @action(detail=True, methods=['put', 'patch'], permission_classes=[UserIsAuthenticated, IsDriver])
    @log_fields_on_object(fields=['driver', 'status'])
    def confirmation(self, request, order_id=None, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, context={'request': request}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if any([item in request.data for item in ('terminate_code', 'error_code', 'terminate_codes')]):
            instance.handle_termination_code()
        instance.handle_confirmation()

        return Response(data=serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[UserIsAuthenticated, IsAdminOrManagerOrObserver])
    def table(self, request, **kwargs):
        q = request.query_params.get('q', '')
        search_conditions = reduce(operator.or_, [Q(**{f + '__icontains': q}) for f in self.search_fields])
        sort_by = request.query_params.get('sort_by', 'created_at')
        desc = (request.query_params.get('desc', 'true') == 'true')
        params = get_request_params(request)
        orders, evs = Order.objects.report_with_assigned_at_events(sort_by, desc, merchant=self.request.user.current_merchant,
                                                                   extra_conditions=search_conditions, **params)
        qs = self.filter_queryset(orders)
        return self.get_pages(qs, OrderTableSerializer, events=evs)

    @action(detail=False, methods=['get'], permission_classes=[UserIsAuthenticated, IsAdminOrManagerOrObserver])
    def last_comments(self, request, **kwargs):
        q = self.queryset.filter(is_confirmed_by_customer=True, merchant=request.user.current_merchant) \
                .order_by('-updated_at')[:self.LAST_COMMENTS_LENGTH]
        return Response(CommentOrderSerializer(q, many=True).data)

    @action(detail=False, methods=['get'], permission_classes=[UserIsAuthenticated])
    def search(self, request, **kwargs):
        q = request.GET.get('q', '')
        orders = self.get_queryset()
        if q:
            user = request.user
            if user.is_manager:
                orders = self.filter_queryset(orders)
            query = reduce(operator.or_, [Q(**{f + '__icontains': q}) for f in self.search_fields])
            selected_orders = orders.filter(query)
        else:
            selected_orders = orders.none()
        return self.get_pages(selected_orders, self.get_serializer_class(), context={'request': request})

    @action(detail=False, methods=['get'], permission_classes=[UserIsAuthenticated])
    def deadlines(self, request, **kwargs):
        user = request.user
        selected_orders = self.queryset \
            .filter(merchant=user.current_merchant, status__in=Order.status_groups.ACTIVE, deliver_before__gt=timezone.now()) \
            .order_by('deliver_before')
        return self.get_pages(selected_orders, OrderDeadlineSerializer, context={'request': request})

    @action(detail=False, methods=['get'], permission_classes=[UserIsAuthenticated])
    def jobs_sorting(self, request, **kwargs):
        orders = self.filter_queryset(self.get_queryset())
        return self.get_pages(orders, OrderIDSerializer, context={'request': request})

    @action(detail=False, methods=['post'], permission_classes=[UserIsAuthenticated, IsDriver, BarcodesEnabled])
    def scan_barcodes(self, request, **kwargs):
        barcodes_serializers = ScanBarcodesCodeDataSerializer(data=request.data, context={'request': request})
        barcodes_serializers.is_valid(raise_exception=True)
        orders = barcodes_serializers.confirm_barcode_scan(request.user)
        return Response(data=BarcodeInformationSerializer(orders.all(), many=True).data)

    @action(detail=True, methods=['patch'],
            permission_classes=[UserIsAuthenticated, IsDriver, ConfirmationDocumentEnabled])
    def upload_confirmation_document(self, request, **kwargs):
        instance = self.get_object()
        serializer = CreateOrderConfirmationDocumentSerializer(
            data=request.data,
            context={'request': request, 'order': instance},
        )
        serializer.is_valid(raise_exception=True)
        document = serializer.save()
        create_document_event(self.request.user, instance, document)

        return Response(data=self.get_serializer(instance).data)
