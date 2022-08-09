from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend
from rest_condition import Or

from base.permissions import IsAdminOrManagerOrObserver, IsReadOnly
from custom_auth.permissions import UserIsAuthenticated
from radaro_utils.permissions import IsAdminOrManager
from reporting.api.legacy.serializers.serializers import ExportReportSerializer
from reporting.models import ExportReportInstance
from route_optimisation.api.permissions import RouteOptimisationEnabled
from route_optimisation.api.web.filters import GroupConst, GroupFilterBackend, RouteOptimisationFilter
from route_optimisation.api.web.serializers import ChangeSequenceSerializer, MoveOrdersSerializer
from route_optimisation.api.web.temp_legacy.serializers import OptimisationTaskSerializer, RouteOptimisationSerializer
from route_optimisation.csv import RouteOptimisationQSWriter
from route_optimisation.models import OptimisationTask, RouteOptimisation


class RouteOptimisationViewSet(mixins.ListModelMixin,
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

    def get_queryset(self):
        return super().get_queryset() \
            .filter(merchant=self.request.user.current_merchant) \
            .exclude(state=RouteOptimisation.STATE.REMOVED) \
            .prefetch_for_web_api()

    def perform_destroy(self, instance):
        if instance.delayed_task.status == OptimisationTask.IN_PROGRESS:
            raise ValidationError(_("You can't delete optimisation which hasn't yet been calculated."))
        unassign = self.request.data.get('unassign', False)
        instance.delete(initiator=self.request.user, unassign=unassign, request=self.request)

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
        with transaction.atomic():
            serializer.is_valid(raise_exception=True)
            serializer.save()
        instance.refresh_from_db()
        return Response(self.get_serializer(instance).data)

    @action(methods=['post'], detail=True)
    def reorder_sequence(self, request, **kwargs):
        instance = self.get_object()
        serializer = ChangeSequenceSerializer(instance, data=request.data, context=self.get_serializer_context())
        with transaction.atomic():
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
        return Response(data=ExportReportSerializer(report_instance, context={'request': request}).data)


class OptimisationTaskViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = OptimisationTask.objects.all()
    serializer_class = OptimisationTaskSerializer
    permission_classes = [UserIsAuthenticated, IsAdminOrManagerOrObserver, RouteOptimisationEnabled]
