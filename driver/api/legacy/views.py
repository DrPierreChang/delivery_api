import operator as op_
from collections import Counter
from functools import reduce

from django.db.models import Count, Q
from django.forms.models import model_to_dict

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_bulk import mixins as bulk_mixins

from base.api.legacy.api import EmployeeViewSet
from base.models import Member
from base.permissions import IsAdminOrManagerOrObserver, IsDriver
from base.utils import get_driver_statistics
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.api.legacy.api import RetrieveSelfMixin
from custom_auth.permissions import IsSelfOrManagerOnly, IsSelfOrManagerOrObserver, UserIsAuthenticated
from driver.models import DriverLocation
from driver.permissions import DriverIsOwnerOrReadOnly
from driver.utils import DRIVER_STATUSES, WorkStatus
from merchant.api.legacy.serializers import HubSerializer, HubSerializerV2
from merchant.api.legacy.serializers.skill_sets import RelatedSkillSetSerializer, SkillSetSerializer
from merchant.permissions import IsNotBlocked, SkillSetsEnabled
from radaro_utils.permissions import IsAdminOrManager
from reporting.context_managers import track_fields_on_change
from reporting.models import Event
from reporting.signals import send_create_event_signal
from tasks.api.legacy.serializers import OrderSerializer
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

from ...utils.locations import prepare_locations_from_serializer
from .filters import DriverFilterSet
from .serializers.driver import (
    DriverInfoSerializer,
    DriverLocationSerializer,
    DriverStatusListSerializer,
    DriverStatusSerializer,
    ListDriverSerializer,
    UpdateDriverSerializer,
)
from .serializers.work_stats import DriverStatisticsForDriverSerializer, DriverStatisticsSerializer


class DriverViewSet(ReadOnlyDBActionsViewSetMixin, mixins.UpdateModelMixin, RetrieveSelfMixin,
                    mixins.RetrieveModelMixin, EmployeeViewSet):
    queryset = Member.drivers.all()

    merchant_position = Member.DRIVER
    serializer_class = ListDriverSerializer
    minimized_serializer_class = DriverInfoSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = DriverFilterSet
    search_fields = ('first_name', 'last_name', 'phone')
    minimized_flag = 'minimized'

    def get_serializer_class(self):
        minimize = self.minimized_flag in self.request.query_params
        if self.request.method == 'GET' and minimize:
            return self.minimized_serializer_class
        if self.action in ('update', 'partial_update'):
            return UpdateDriverSerializer
        return self.serializer_class

    def filter_queryset(self, queryset):
        from tasks.models import BulkDelayedUpload
        qs = Member.all_drivers.all().add_statuses().sort_by_status()
        qs = qs.prefetch_related('skill_sets', 'merchant__checklist', 'last_location', 'merchant__has_related_surveys',
                                 'starting_hub__location', 'ending_hub__location', 'car')
        qs = qs.annotate(active_orders_count=Count(
            'order',
            filter=Q(
                Q(order__bulk__isnull=True) | Q(order__bulk__status=BulkDelayedUpload.CONFIRMED),
                order__deleted=False, order__status__in=OrderStatus.status_groups.ACTIVE_DRIVER)
        )
        )

        # Here in the filter DriverIdFilter is defined when to display deleted orders
        qs = super(DriverViewSet, self).filter_queryset(qs)

        if self.request.user.current_merchant.sod_checklist_id:
            qs = qs.prefetch_sod_checklist_result(self.request.user.current_merchant)
        if self.request.user.current_merchant.eod_checklist_id:
            qs = qs.prefetch_eod_checklist_result(self.request.user.current_merchant)
        if self.action == 'online':
            qs = qs.filter(work_status=WorkStatus.WORKING)
        search_param = self.request.query_params.get('q')
        if search_param:
            search_conditions = reduce(
                op_.or_,
                [Q(**{field + '__icontains': search_param}) for field in self.search_fields]
            )
            qs = qs.filter(search_conditions)

        return qs

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return_serializer = self.serializer_class(instance, context=self.get_serializer_context())
        return Response(return_serializer.data)

    def perform_update(self, serializer):
        with track_fields_on_change(serializer.instance, initiator=self.request.user):
            return super().perform_update(serializer)

    @action(methods=['get'], detail=False, permission_classes=[UserIsAuthenticated, IsAdminOrManagerOrObserver])
    def count_items(self, request, **kwargs):
        driver_statuses_dataset = self.filter_queryset(None).values_list('_status', 'work_status', 'is_offline_forced')
        driver_statuses = [_status for _status, _, _ in driver_statuses_dataset]
        driver_statuses += [
            Member.calculate_work_status_for_manager(work_status, is_offline_forced)
            for _, work_status, is_offline_forced in driver_statuses_dataset
        ]

        count = Counter(driver_statuses)
        statuses = [WorkStatus.WORKING, WorkStatus.NOT_WORKING, WorkStatus.ON_BREAK, *DRIVER_STATUSES]
        count_result = dict({st: 0 for st in statuses}, **count)

        return Response(data=count_result)

    @action(detail=False, permission_classes=[UserIsAuthenticated, IsAdminOrManagerOrObserver])
    def online(self, request, **kwargs):
        return self.list(request)

    @action(methods=['get', 'put'], detail=True, permission_classes=[UserIsAuthenticated, IsSelfOrManagerOnly])
    def status(self, request, pk=None, **kwargs):
        instance = self.get_object()
        if request.method == 'PUT':
            serializer_params = dict(data=request.data, context={'request': request})
            if isinstance(request.data, list) and self.request.user.id == instance.id:
                serializer = DriverStatusListSerializer(instance, **serializer_params)
            else:
                serializer = DriverStatusSerializer(instance, **serializer_params)

            serializer.is_valid(raise_exception=True)
            serializer.save()

        return Response(data=DriverStatusSerializer(instance, context={'request': request}).data)

    @action(methods=['put', 'patch'], detail=True, permission_classes=[UserIsAuthenticated, IsAdminOrManager, IsNotBlocked],
                  url_path='bulk-assign')
    def bulk_assign(self, request, **kwargs):
        ret = []
        instance = self.get_object()
        status_code = status.HTTP_200_OK
        _fieldnames = ['driver', 'status']
        order_ids = request.data.get('order_ids', [])
        old_values = {}

        for order in Order.objects.filter(order_id__in=order_ids):
            old_values.update({order.order_id: model_to_dict(order, fields=_fieldnames)})
            serializer = OrderSerializer(order, data={'status': Order.ASSIGNED},
                                         context={'request': request}, partial=True)
            if not serializer.is_valid():
                error = serializer.errors
                error["order_id"] = order.order_id
                ret.append(error)
                status_code = status.HTTP_400_BAD_REQUEST

        if not ret:
            Order.objects.filter(order_id__in=order_ids).update(driver=instance, status=Order.ASSIGNED)
            for order in Order.objects.filter(order_id__in=order_ids):
                events = []
                for key in _fieldnames:
                    params = dict(initiator=request.user, field=key, new_value=getattr(order, key),
                                  object=order, event=Event.CHANGED)
                    events.append(Event.generate_event(self, **params))
                obj_dump = {
                    "new_values": model_to_dict(order, fields=_fieldnames),
                    "old_values": old_values.get(order.order_id)
                }
                events.append(Event.generate_event(self, initiator=request.user, obj_dump=obj_dump,
                                                   object=order, event=Event.MODEL_CHANGED))
                send_create_event_signal(events)
                ret.append(OrderSerializer(order).data)

        return_data = {"errors": ret} if status_code == status.HTTP_400_BAD_REQUEST else ret

        return Response(data=return_data, status=status_code)

    @action(methods=['get', ], detail=True, url_path='driver-stats',
            permission_classes=[UserIsAuthenticated, IsSelfOrManagerOrObserver])
    def driver_statistics(self, request, **kwargs):
        instance = self.get_object()
        LOW_RATING_VALUE = instance.current_merchant.low_feedback_value

        orders = instance.order_set.filter(status=OrderStatus.DELIVERED, deleted=False)
        # Orders in which the customer has rated or left a comment
        confirmed_orders = orders.exclude(
            Q(customer_comment__isnull=True) | Q(customer_comment=''),
            rating__isnull=True,
        )
        ratings = [one_rating or 0 for one_rating in confirmed_orders.values_list('rating', flat=True)]

        low_ratings = [x for x in ratings if x <= LOW_RATING_VALUE]
        last_online_change = instance.event_set.all().filter(field='work_status').first()
        data = {
            'completed_jobs': orders.count(),
            'low_rating_jobs': len(low_ratings),
            'average_rating': sum(ratings) * 1. / len(ratings) if ratings else None,
            'last_online_change': last_online_change and last_online_change.happened_at,
            'date_joined': instance.date_joined,
            'time_stats': get_driver_statistics(instance),
        }

        if self.request.user.is_driver:
            data = DriverStatisticsForDriverSerializer(instance=data).data
        else:
            data = DriverStatisticsSerializer(instance=data).data

        return Response(data=data)

    @action(methods=['post', ], detail=True, url_path='ping', permission_classes=[UserIsAuthenticated, IsDriver])
    def set_last_ping(self, request, **kwargs):
        instance = self.get_object()
        instance.set_last_ping()
        return Response()


class DriverSkillSetsViewSet(ReadOnlyDBActionsViewSetMixin, bulk_mixins.BulkDestroyModelMixin, mixins.ListModelMixin,
                             mixins.CreateModelMixin, viewsets.GenericViewSet):
    permission_classes = [UserIsAuthenticated, IsDriver, SkillSetsEnabled]
    serializer_class = SkillSetSerializer
    relative_skill_set_serializer = RelatedSkillSetSerializer
    parent_lookup_field = 'driver_pk'

    def _get_related_object(self):
        return self.request.user

    def get_queryset(self):
        member = self._get_related_object()
        return member.skill_sets.all().order_by('-pk')

    def create(self, request, *args, **kwargs):
        serializer = self.relative_skill_set_serializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        skill_sets = serializer.validated_data.get('skill_sets', [])

        driver = self._get_related_object()
        with track_fields_on_change(driver, initiator=driver, sender=Member):
            driver.skill_sets.add(*skill_sets)

        serializer = self.get_serializer(skill_sets, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def bulk_destroy(self, request, *args, **kwargs):
        serializer = self.relative_skill_set_serializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        skill_sets = serializer.validated_data.get('skill_sets', [])

        driver = self._get_related_object()
        with track_fields_on_change(driver, initiator=driver, sender=Member):
            driver.skill_sets.remove(*skill_sets)

        return Response(status=status.HTTP_204_NO_CONTENT)


class DriverLocationViewSet(ReadOnlyDBActionsViewSetMixin, mixins.ListModelMixin, mixins.CreateModelMixin,
                            viewsets.GenericViewSet):
    queryset = DriverLocation.objects.all()
    serializer_class = DriverLocationSerializer
    permission_classes = [UserIsAuthenticated, DriverIsOwnerOrReadOnly]

    def initial(self, request, *args, **kwargs):
        super(DriverLocationViewSet, self).initial(request, *args, **kwargs)
        driver_pk = kwargs.get('driver_pk')
        self.driver = request.user if driver_pk == 'me' else \
            get_object_or_404(Member.drivers.filter(merchant=request.user.current_merchant), pk=driver_pk)
        self.q = self.queryset.filter(member=self.driver).order_by('-created_at')
        self.last_loc = self.q.first()

    def get_queryset(self):
        return self.q

    def create(self, request, *args, **kwargs):
        # Also `is_many` designates whether these locations from offline or no.
        self.is_many = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=self.is_many)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        prepare_locations_from_serializer(serializer, self.last_loc, self.is_many)
        self.driver.set_last_ping()


class DriverHubViewSet(ReadOnlyDBActionsViewSetMixin, mixins.ListModelMixin, viewsets.GenericViewSet):

    permission_classes = [UserIsAuthenticated, DriverIsOwnerOrReadOnly]
    serializer_class = HubSerializer
    serializer_class_v2 = HubSerializerV2

    def get_serializer_class(self):
        if self.request.version >= 2:
            return self.serializer_class_v2
        return self.serializer_class

    def get_queryset(self):
        hubs = self.request.user.wayback_hubs.all().order_by('id')
        if not len(hubs):
            return self.request.user.current_merchant.hub_set.all().order_by('id')
        return hubs
