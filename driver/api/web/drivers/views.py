from collections import Counter

from django.db.models import Count, IntegerField, OuterRef, Q, Subquery

from rest_framework import mixins, response, viewsets
from rest_framework.decorators import action

from django_filters.rest_framework import DjangoFilterBackend
from rest_condition import Or

from base.models import Member
from base.permissions import IsAdminOrManagerOrObserver, IsReadOnly
from base.utils import get_driver_statistics
from custom_auth.permissions import UserIsAuthenticated
from driver.utils import DRIVER_STATUSES, WorkStatus
from merchant.permissions import IsNotBlocked
from radaro_utils.permissions import IsAdminOrManager
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

from .filters import WebDriverFilterSet
from .serializers import (
    WebDriverSerializer,
    WebDriverStatisticsSerializer,
    WebScheduleDriverUploadResultSerializer,
    WebScheduleDriverUploadSerializer,
)


class WebDriverViewSet(mixins.ListModelMixin,
                       mixins.UpdateModelMixin,
                       mixins.RetrieveModelMixin,
                       viewsets.GenericViewSet):
    permission_classes = [
        UserIsAuthenticated, IsNotBlocked, IsAdminOrManagerOrObserver, Or(IsAdminOrManager, IsReadOnly),
    ]
    queryset = Member.all_drivers.all().add_statuses().sort_by_status()
    serializer_class = WebDriverSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = WebDriverFilterSet

    def get_queryset(self):
        merchant = self.request.user.current_merchant

        qs = super().get_queryset()
        qs = qs.select_related('last_location', 'car', 'starting_hub__location', 'ending_hub__location')
        qs = qs.prefetch_related('skill_sets')

        if self.action in ['list', 'retrieve', 'statistics']:
            qs = qs.deleted_or_active()
        else:
            qs = qs.not_deleted().active()

        if merchant.sod_checklist_id:
            qs = qs.prefetch_sod_checklist_result(merchant)

        if merchant.eod_checklist_id:
            qs = qs.prefetch_eod_checklist_result(merchant)

        if self.action in ['list', 'retrieve', 'update']:
            orders = Order.aggregated_objects.filter_by_merchant(merchant)
            orders = orders.filter(status__in=OrderStatus.status_groups.ACTIVE_DRIVER)
            orders_count = orders.filter(driver_id=OuterRef('pk')).order_by('driver_id').values('driver_id')
            orders_count = orders_count.annotate(orders_count=Count('pk')).values('orders_count')
            orders_count = Subquery(orders_count, output_field=IntegerField())
            qs = qs.annotate(active_orders_count=orders_count)

        return qs

    @action(methods=['get'], detail=False)
    def count_items(self, request, **kwargs):
        driver_statuses = self.filter_queryset(self.get_queryset())
        driver_statuses = driver_statuses.values_list('_status', 'work_status', 'is_offline_forced')

        status_list = (
            (status, Member.calculate_work_status_for_manager(work_status, is_offline_forced))
            for status, work_status, is_offline_forced in driver_statuses
        )
        status_list = [status for status_pair in status_list for status in status_pair]
        status_stats = Counter(status_list)

        available_statuses = [WorkStatus.WORKING, WorkStatus.NOT_WORKING, WorkStatus.ON_BREAK] + DRIVER_STATUSES
        result = dict({st: 0 for st in available_statuses}, **status_stats)
        return response.Response(data=result)

    @action(methods=['get'], detail=True)
    def statistics(self, request, **kwargs):
        instance = self.get_object()

        orders = instance.order_set.filter(status=OrderStatus.DELIVERED, deleted=False)
        # Orders in which the customer has rated or left a comment
        confirmed_orders = orders.exclude(
            Q(customer_comment__isnull=True) | Q(customer_comment=''),
            rating__isnull=True,
        )
        ratings = [one_rating or 0 for one_rating in confirmed_orders.values_list('rating', flat=True)]

        low_rating_count = sum(1 for one_rating in ratings if one_rating <= instance.merchant.low_feedback_value)
        average_rating = sum(ratings) * 1. / len(ratings) if len(ratings) else None
        last_online_change = instance.event_set.all().filter(field='work_status').first()

        data = {
            'completed_order_count': orders.count(),
            'low_rating_order_count': low_rating_count,
            'average_rating': average_rating,
            'last_online_change': last_online_change and last_online_change.happened_at,
            'date_joined': instance.date_joined,
            'time_stats': get_driver_statistics(instance),
        }
        return response.Response(data=WebDriverStatisticsSerializer(instance=data).data)

    @action(methods=['post'], detail=False)
    def schedule_upload(self, request, **kwargs):
        bulk_serializer = WebScheduleDriverUploadSerializer(data=request.data, context=self.get_serializer_context())
        bulk_serializer.is_valid(raise_exception=True)
        bulk = bulk_serializer.save()

        return response.Response(data=WebScheduleDriverUploadResultSerializer(bulk).data)
