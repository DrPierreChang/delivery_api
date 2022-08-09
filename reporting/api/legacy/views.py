from __future__ import absolute_import, unicode_literals

from datetime import timedelta

from django.utils import timezone

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from constance import config
from dateutil.parser import parse

from base.models import Member
from base.permissions import IsAdminOrManagerOrObserver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from driver.utils import WorkStatus
from merchant.models import Merchant
from reporting.models import Event, ExportReportInstance
from reporting.utils.report import fill_data_and_sum, get_request_params
from tasks.celery_tasks.reporting import generate_report_file
from tasks.models import Order

from .serializers.serializers import (
    EventSerializerV2,
    ExportReportSerializer,
    OrderResultReportSerializer,
    OrderStatsReportSerializer,
    SMSReportSerializer,
)


class ReportViewSet(viewsets.GenericViewSet):
    queryset = Member.objects.all()
    permission_classes = [UserIsAuthenticated, IsAdminOrManagerOrObserver]

    def get_queryset(self):
        return self.queryset.filter(merchant=self.request.user.current_merchant)

    @action(detail=False)
    def orders(self, request, **kwargs):
        export = request.query_params.get('export')
        params = get_request_params(request)

        if not export:
            data = OrderResultReportSerializer(
                Order.objects.sum_report_by_date(merchant=self.request.user.current_merchant, **params),
                many=True
            ).data

            sum_ = {'total_tasks': 0, 'successful_tasks': 0, 'unsuccessful_tasks': 0}
            data = fill_data_and_sum(data, params, sum_)
            return Response({'data': data, 'sum_data': sum_})
        if export:
            params['merchant'] = self.request.user.current_merchant
            inst = ExportReportInstance.objects.create(merchant=self.request.user.current_merchant, file=None)
            generate_report_file.apply_async(args=(inst.id, request.user.id, params, export))
            try:
                new_inst = ExportReportInstance.objects.get(id=inst.id)
            except ExportReportInstance.DoesNotExist:
                raise APIException(detail='Task does not exist.')
            return Response(data=ExportReportSerializer(new_inst, context={'request': request}).data)

    @action(detail=False)
    def locations(self, request, **kwargs):
        params = get_request_params(request)
        return Response(data=Order.objects.order_locations_by_date(merchant=self.request.user.current_merchant, **params))

    @action(detail=False)
    def orderstats(self, request, **kwargs):
        params = get_request_params(request)
        data = OrderStatsReportSerializer(
            Order.objects.distance_time_by_date(merchant=self.request.user.current_merchant, **params),
            many=True
        ).data
        sum_ = {'sum_distance': 0, 'sum_duration': 0, 'finished_tasks': 0}
        data = fill_data_and_sum(data, params, sum_)
        if sum_['finished_tasks']:
            sum_['avg_distance'] = sum_['sum_distance'] / sum_['finished_tasks']
            sum_['avg_duration'] = sum_['sum_duration'] / sum_['finished_tasks']
        return Response({'sum_data': sum_, 'data': data})

    @action(url_path='sms-stats', detail=False)
    def sms_stats(self, request, **kwargs):
        date_from = request.query_params.get('date_from', '')
        date_to = request.query_params.get('date_to', '')

        serializer = SMSReportSerializer(data={'date_from': date_from, 'date_to': date_to})
        serializer.is_valid(raise_exception=True)

        merchant_report_data = Merchant.objects\
            .cms_report_data(merchant_id=self.request.user.current_merchant_id, **serializer.validated_data)[0]
        report_fields = (
                'sms_order_in_progress', 'sms_order_terminated', 'sms_order_follow_up',
                'sms_order_follow_up_reminder', 'sms_invitation', 'sms_invitation_complete',
                'sms_order_upcoming_delivery'
            )
        report_data = {field: getattr(merchant_report_data, field, 0) for field in report_fields}

        return Response({'count_per_type': report_data})


class EventViewSet(viewsets.ViewSet):
    OLD_DATE = parse('01-01-1970 00:00:00+0')
    MAX_PERIOD = timedelta(minutes=15)

    permission_classes = [UserIsAuthenticated, IsAdminOrManagerOrObserver]

    def filter_queryset(self, queryset):
        return queryset.filter(created_at__lte=self.events_before)

    def get_queryset(self):
        return Event.objects.last_events(self.merchant, self.date_since)

    def get(self, *args, **kwargs):
        if self.request.version < 2:
            raise NotFound('Endpoint new-events version 1 is not supported')

        data = {
            'events_before': self.events_before.isoformat(),
            'events_since': self.date_since.isoformat()
        }

        drivers = Member.all_drivers.all().not_deleted().filter(
            work_status=WorkStatus.WORKING,
            merchant=self.merchant,
            current_path_updated__gt=self.date_since,
            current_path_updated__lte=self.events_before
        ).order_by('id').distinct('id')
        if drivers.exists():
            data['paths'] = [d.current_path for d in drivers if d.current_path]

        events = self.filter_queryset(self.get_queryset())
        events = list(events)
        if events:
            events = Event.objects.prepare_for_list(events)
            events = Event.objects.filter_out_without_object(events)
            data['events'] = EventSerializerV2(events, many=True, context={'request': self.request}).data

        return Response(data=data)

    def initial(self, request, *args, **kwargs):
        super(EventViewSet, self).initial(request, *args, **kwargs)
        try:
            if not config.EVENT_UPDATING_ALLOWED:
                raise PermissionDenied(detail='Event updating is impossible.')

            self.events_before = timezone.now()
            self.merchant = request.user.current_merchant
            self.date_since = timezone.now() - EventViewSet.MAX_PERIOD
            try:
                custom_date_since = parse(request.query_params.get('date_since').replace('Z', '+'))
                if self.date_since < custom_date_since:
                    self.date_since = custom_date_since
            except (AttributeError, ValueError):
                pass

        except AttributeError:
            raise PermissionDenied(detail='Only members of merchant are allowed to see events.')
        except KeyError:
            raise APIException(detail='No date since was provided.')
        except ValueError:
            raise APIException(detail='Illegal date format.')


class ExportReportViewSet(ReadOnlyDBActionsViewSetMixin, ReadOnlyModelViewSet):
    permission_classes = [UserIsAuthenticated]
    serializer_class = ExportReportSerializer

    def get_queryset(self):
        return ExportReportInstance.objects.filter(merchant=self.request.user.current_merchant)
