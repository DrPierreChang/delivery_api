from datetime import timedelta

from django.utils import timezone

import django_filters
import pytz
from django_filters.rest_framework import FilterSet
from pytz import UnknownTimeZoneError

from radaro_utils.db import TruncDateFunc
from route_optimisation.models import DriverRoute
from tasks.models import ConcatenatedOrder, Order


class BaseDateFilterSet(FilterSet):
    date_from = django_filters.DateFilter()
    date_to = django_filters.DateFilter()
    timezone = django_filters.CharFilter()

    class Meta:
        model = Order
        fields = ['date_from', 'date_to', 'timezone']

    def filter_queryset(self, queryset):
        tz = self.request.user.current_merchant.timezone
        if self.form.cleaned_data['timezone']:
            try:
                tz = pytz.timezone(self.form.cleaned_data['timezone'])
            except UnknownTimeZoneError:
                pass

        today = timezone.now().astimezone(tz).date()
        date_from = self.form.cleaned_data['date_from'] or today - timedelta(days=1)
        date_to = self.form.cleaned_data['date_to'] or today + timedelta(days=1)

        return self.filter_queryset_by_date(queryset, date_from, date_to, tz)

    def filter_queryset_by_date(self, queryset, date_from, date_to, tz):
        return queryset


class OrderDateFilterSet(BaseDateFilterSet):

    def filter_queryset_by_date(self, queryset, date_from, date_to, tz):
        queryset = queryset.annotate(
            delivery_date=TruncDateFunc('deliver_before', tzinfo=tz)
        )
        queryset = queryset.filter(delivery_date__range=(date_from, date_to))
        return queryset


class ConcatenatedOrderDateFilterSet(BaseDateFilterSet):
    class Meta(BaseDateFilterSet.Meta):
        model = ConcatenatedOrder

    def filter_queryset_by_date(self, queryset, date_from, date_to, tz):
        return queryset.filter(deliver_day__range=(date_from, date_to))


class OptimisationDateFilterSet(BaseDateFilterSet):
    class Meta(BaseDateFilterSet.Meta):
        model = DriverRoute

    def filter_queryset_by_date(self, queryset, date_from, date_to, tz):
        return queryset.filter(optimisation__day__range=(date_from, date_to))
