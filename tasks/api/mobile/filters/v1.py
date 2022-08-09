import operator
from functools import reduce

from django.db.models import Q

from rest_framework import filters

import django_filters
from django_filters import ChoiceFilter
from django_filters.constants import EMPTY_VALUES
from django_filters.rest_framework import FilterSet, IsoDateTimeFromToRangeFilter

from base.models import Member
from merchant.models import Label, SkillSet, SubBranding
from radaro_utils.filters.rest_framework_filters import RadaroModelMultipleChoiceFilter
from tasks.mixins.order_status import OrderStatus
from tasks.models import Customer, Order


class StatusGroupFilter(ChoiceFilter):
    UNALLOCATED = 'unallocated'
    ACTIVE = 'active'
    FINISHED = 'finished'
    UNFINISHED = 'unfinished'
    choices = (
        (UNALLOCATED, 'unallocated'),
        (ACTIVE, 'active'),
        (FINISHED, 'finished'),
        (UNFINISHED, 'unfinished'),
    )
    status_groups_filters = {
        UNALLOCATED: Q(status=OrderStatus.NOT_ASSIGNED),
        ACTIVE: Q(status__in=OrderStatus.status_groups.ACTIVE_DRIVER),
        UNFINISHED: Q(status__in=OrderStatus.status_groups.UNFINISHED),
        FINISHED: Q(status__in=OrderStatus.status_groups.FINISHED),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(choices=self.choices, *args, **kwargs)

    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs
        if self.distinct:
            qs = qs.distinct()

        return qs.filter(self.status_groups_filters[value])


class SearchFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        query = request.GET.get('q', '')
        if query:
            prepared_query = reduce(operator.or_, [Q(**{f + '__icontains': query}) for f in view.search_fields])
            return queryset.filter(prepared_query)
        return queryset


class OrderFilterSet(FilterSet):
    status = django_filters.MultipleChoiceFilter(choices=OrderStatus._status)
    # ?status=failed&status=delivered
    deliver_before = IsoDateTimeFromToRangeFilter()
    # ?deliver_before_after=2015-01-08T21:00:00.000Z&deliver_before_before=2025-01-05T21:00:00.000Z
    updated_at = IsoDateTimeFromToRangeFilter()
    # ?updated_at_after=2015-01-08T21:00:00.000Z&updated_at_before=2025-01-05T21:00:00.000Z
    labels = RadaroModelMultipleChoiceFilter(
        to_field_name='id',
        queryset=Label.objects.all(),
        conjoined=True,
    )
    # ?labels=477
    skill_sets = RadaroModelMultipleChoiceFilter(
        to_field_name='id',
        queryset=SkillSet.objects.all(),
        conjoined=True,
    )
    # ?skill_sets=171
    sub_branding = RadaroModelMultipleChoiceFilter(
        to_field_name='id',
        queryset=SubBranding.objects.all(),
    )
    # ?sub_branding=243
    driver = RadaroModelMultipleChoiceFilter(to_field_name='id', queryset=Member.drivers.all())
    # ?driver=678
    group = StatusGroupFilter()
    # ?group=active
    customer = RadaroModelMultipleChoiceFilter(to_field_name='id', queryset=Customer.objects.all())
    # ?customer=12

    class Meta:
        model = Order
        fields = [
            'status', 'deliver_before', 'updated_at', 'labels', 'skill_sets', 'sub_branding', 'driver', 'group',
            'bulk_id', 'customer',
        ]
