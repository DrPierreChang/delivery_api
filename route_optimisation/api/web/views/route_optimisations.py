from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend
from rest_condition import Or

from base.permissions import IsAdminOrManagerOrObserver, IsReadOnly
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from radaro_utils.permissions import IsAdminOrManager
from reporting.api.legacy.serializers.serializers import ExportReportSerializer
from reporting.models import ExportReportInstance
from route_optimisation.celery_tasks.optimisation import delete_optimisation
from route_optimisation.csv import RouteOptimisationQSWriter
from route_optimisation.models import OptimisationTask, RouteOptimisation
from tasks.api.mobile.filters.v1 import OrderFilterSet
from tasks.api.web.orders.views import WebOrderViewSet

from ...permissions import RouteOptimisationEnabled
from ..filters import GroupConst, GroupFilterBackend, RouteFilterBackend, RouteOptimisationFilter
from ..serializers import (
    ChangeSequenceSerializer,
    MoveOrdersSerializer,
    RefreshRouteSerializer,
    RouteOptimisationSerializer,
)


class RouteOptimisationViewSet(ReadOnlyDBActionsViewSetMixin,
                               mixins.ListModelMixin,
                               mixins.RetrieveModelMixin,
                               mixins.CreateModelMixin,
                               mixins.DestroyModelMixin,
                               viewsets.GenericViewSet):
    queryset = RouteOptimisation.objects.all().order_by('-id')
    serializer_class = RouteOptimisationSerializer
    permission_classes = [
        UserIsAuthenticated,
        IsAdminOrManagerOrObserver,
        Or(IsAdminOrManager, IsReadOnly),
        RouteOptimisationEnabled,
    ]
    filter_backends = (DjangoFilterBackend, GroupFilterBackend)
    filterset_class = RouteOptimisationFilter
    read_only_db_actions = ReadOnlyDBActionsViewSetMixin.read_only_db_actions + ['count_items']

    def get_queryset(self):
        qs = super().get_queryset() \
            .filter(merchant=self.request.user.current_merchant) \
            .exclude(state=RouteOptimisation.STATE.REMOVED)

        if self.action in ['polylines', 'optimisation_polylines']:
            return qs.prefetch_related('routes__points')
        return qs.prefetch_for_web_api()

    def perform_destroy(self, instance):
        if instance.delayed_task.status == OptimisationTask.IN_PROGRESS:
            raise ValidationError(_("You can't delete optimisation which hasn't yet been calculated."))
        unassign = self.request.data.get('unassign', False)
        delete_optimisation.delay(instance.id, unassign, self.request.user.id)

    @action(methods=['post'], detail=True)
    def notify_customers(self, request, **kwargs):
        instance = self.get_object()
        if instance.state not in (RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING) \
                or instance.customers_notified:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        instance.notify_customers(request.user)
        return Response()

    @action(methods=['post'], detail=True)
    def move_orders(self, request, **kwargs):
        instance = self.get_object()
        serializer = MoveOrdersSerializer(instance, data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        serializer.save()
        instance.refresh_from_db()
        return Response(self.get_serializer(instance).data)

    @action(methods=['post'], detail=True)
    def reorder_sequence(self, request, **kwargs):
        instance = self.get_object()
        serializer = ChangeSequenceSerializer(instance, data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        serializer.save()
        instance.refresh_from_db()
        return Response(self.get_serializer(instance).data)

    @action(methods=['get'], detail=False)
    def count_items(self, request, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.filter(delayed_task__status=OptimisationTask.COMPLETED)
        today = timezone.now().astimezone(request.user.current_merchant.timezone).date()
        return Response({
            GroupConst.ALL: queryset.count(),
            GroupConst.FAILED: queryset.filter(state=RouteOptimisation.STATE.FAILED).count(),
            GroupConst.SCHEDULED: queryset.filter(
                state__in=[RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING],
                day__gt=today
            ).count(),
            GroupConst.CURRENT: queryset.filter(
                state__in=[RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING],
                day=today
            ).count(),
        })

    @action(detail=True)
    def export(self, request, **kwargs):
        optimisation = self.get_object()
        report_instance = ExportReportInstance.objects.create(
            initiator=request.user,
            merchant=request.user.current_merchant,
        )
        file_name = 'RouteOptimisation_{}'.format(optimisation.id)
        report_instance.build_csv_report(
            RouteOptimisationQSWriter, {'optimisation': optimisation},
            file_name=file_name, unique_name=False,
        )
        return Response(data=ExportReportSerializer(report_instance, context=self.get_serializer_context()).data)

    @action(methods=['post'], detail=True)
    def refresh(self, request, **kwargs):
        instance = self.get_object()
        serializer = RefreshRouteSerializer(instance, data=self.request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(data=self.get_serializer(instance, context=self.get_serializer_context()).data)

    @action(methods=['post'], detail=True)
    def terminate(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.state not in (RouteOptimisation.STATE.VALIDATION, RouteOptimisation.STATE.OPTIMISING):
            return Response(status=status.HTTP_400_BAD_REQUEST)
        instance.terminate(initiator=request.user, request=request)
        return Response(status=status.HTTP_200_OK)


class AvailableForAddOrderViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [
        UserIsAuthenticated,
        IsAdminOrManagerOrObserver,
        Or(IsAdminOrManager, IsReadOnly),
        RouteOptimisationEnabled,
    ]
    parent_lookup_field = 'optimisation_pk'

    serializer_class = WebOrderViewSet.serializer_class
    serializers = WebOrderViewSet.serializers
    filter_backends = WebOrderViewSet.filter_backends + (RouteFilterBackend,)
    filterset_class = OrderFilterSet
    search_fields = WebOrderViewSet.search_fields

    get_object = WebOrderViewSet.get_object
    get_serializer = WebOrderViewSet.get_serializer
    list = WebOrderViewSet.list

    @cached_property
    def optimisation(self):
        parent_lookup = self.kwargs.get(self.parent_lookup_field)
        return get_object_or_404(RouteOptimisation, merchant=self.request.user.current_merchant, pk=parent_lookup)

    def get_queryset(self):
        optimisation = self.optimisation
        orders = optimisation.get_available_orders()
        # Filtering by drivers occurs in RouteFilterBackend
        return orders.order_by_statuses()
