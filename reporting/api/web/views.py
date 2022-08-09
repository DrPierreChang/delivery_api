from datetime import timedelta

from django.utils import timezone

from rest_framework import viewsets
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.response import Response

from constance import config
from dateutil.parser import parse

from base.models import Member
from base.permissions import IsAdminOrManagerOrObserver
from custom_auth.permissions import UserIsAuthenticated
from driver.utils import WorkStatus
from reporting.models import Event

from .serializers import WebEventSerializer


class WebEventViewSet(viewsets.ViewSet):
    OLD_DATE = parse('01-01-1970 00:00:00+0')
    MAX_PERIOD = timedelta(minutes=15)

    permission_classes = [UserIsAuthenticated, IsAdminOrManagerOrObserver]

    def filter_queryset(self, queryset):
        return queryset.filter(created_at__lte=self.events_before)

    def get_queryset(self):
        return Event.objects.last_events(self.merchant, self.date_since)

    def get(self, *args, **kwargs):
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
            data['events'] = WebEventSerializer(events, many=True, context={'request': self.request}).data

        return Response(data=data)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        try:
            if not config.EVENT_UPDATING_ALLOWED:
                raise PermissionDenied(detail='Event updating is impossible.')

            self.events_before = timezone.now()
            self.merchant = request.user.current_merchant
            self.date_since = timezone.now() - WebEventViewSet.MAX_PERIOD
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
