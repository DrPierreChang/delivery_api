from django.db import models

from rest_framework import filters

import django_filters
from django_filters.fields import IsoDateTimeField, RangeField
from django_filters.rest_framework import FilterSet
from django_filters.widgets import RangeWidget

from base.models import Member
from merchant.models import Label, SkillSet, SubBranding
from radaro_utils.filters.rest_framework_filters import RadaroModelMultipleChoiceFilter
from tasks.mixins.order_status import OrderStatus, StatusFilterConditions
from tasks.models import Order


def filter_orders_for_reports(qs, group):
    if group and group in StatusFilterConditions.available:
        return qs.filter(models.Q(**StatusFilterConditions.status_groups[group]))
    return qs


class CustomRangeWidget(RangeWidget):
    """Date widget to help filter by *_start and *_end."""
    suffixes = ['0', '1']


class ISODateTimeRangeField(RangeField):
    widget = CustomRangeWidget

    def __init__(self, *args, **kwargs):
        fields = (
            IsoDateTimeField(),
            IsoDateTimeField())
        super(ISODateTimeRangeField, self).__init__(fields, *args, **kwargs)


class ISODateTimeFromToRangeFilter(django_filters.RangeFilter):
    field_class = ISODateTimeRangeField


class StatusGroupFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        group = request.GET.get('group', '')
        if request.user.is_driver and group:
            is_archived = group == 'archived'
            queryset = queryset.orders_with_archived_field().filter(archived=is_archived)
            if group == 'active':
                group = 'active_driver'
        queryset = filter_orders_for_reports(queryset, group)
        return queryset


class OrderFilterSet(FilterSet):
    status = django_filters.MultipleChoiceFilter(choices=OrderStatus._status, distinct=False)
    deliver_after = ISODateTimeFromToRangeFilter()
    deliver_before = ISODateTimeFromToRangeFilter()
    updated_at = ISODateTimeFromToRangeFilter()
    labels = RadaroModelMultipleChoiceFilter(to_field_name='id', queryset=Label.objects.all(),
                                             conjoined=True, distinct=False)
    skill_sets = RadaroModelMultipleChoiceFilter(to_field_name='id', queryset=SkillSet.objects.all(),
                                                 conjoined=True, distinct=False)
    sub_branding = RadaroModelMultipleChoiceFilter(to_field_name='id', queryset=SubBranding.objects.all(),
                                                   distinct=False)
    driver = RadaroModelMultipleChoiceFilter(to_field_name='id', queryset=Member.drivers.all(),
                                             distinct=False)
    # distinct is disabled here, so as not to overwrite distinct by individual fields from OrderViewSet

    class Meta:
        model = Order
        fields = ['status', 'driver', 'bulk_id', 'deliver_after', 'deliver_before', 'labels', 'updated_at', 'skill_sets',
                  'sub_branding']
