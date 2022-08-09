from django.db.models import Q

from rest_framework import filters

from django_filters import ChoiceFilter
from django_filters.constants import EMPTY_VALUES

from radaro_utils.filters.rest_framework_filters import RadaroModelMultipleChoiceFilter
from tasks.api.mobile.filters.v1 import OrderFilterSet
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order


class WebStatusGroupFilter(ChoiceFilter):
    SUCCESSFUL = 'successful'
    UNSUCCESSFUL = 'unsuccessful'
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    CONFIRMED = 'confirmed'

    choices = (
        (SUCCESSFUL, 'successful'),
        (UNSUCCESSFUL, 'unsuccessful'),
        (ACTIVE, 'active'),
        (INACTIVE, 'inactive'),
        (CONFIRMED, 'confirmed'),
    )
    status_groups_filters = {
        SUCCESSFUL: Q(status__in=OrderStatus.status_groups.SUCCESSFUL),
        UNSUCCESSFUL: Q(status__in=OrderStatus.status_groups.UNSUCCESSFUL),
        ACTIVE: Q(status__in=OrderStatus.status_groups.UNFINISHED),
        INACTIVE: Q(status__in=OrderStatus.status_groups.FINISHED),
        CONFIRMED: Q(status=OrderStatus.DELIVERED, is_confirmed_by_customer=True),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(choices=self.choices, *args, **kwargs)

    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs
        if self.distinct:
            qs = qs.distinct()

        return qs.filter(self.status_groups_filters[value])


class TypesGroupFilter(ChoiceFilter):
    ALL = 'all'
    SINGLE = 'single'
    CONCATENATED = 'concatenated'
    AGGREGATED = 'aggregated'
    choices = (
        (ALL, 'all'),
        (SINGLE, 'single'),
        (CONCATENATED, 'concatenated'),
        (AGGREGATED, 'aggregated'),
    )
    types_groups_filters = {
        ALL: Q(),
        SINGLE: Q(is_concatenated_order=False),
        CONCATENATED: Q(is_concatenated_order=True),
        AGGREGATED: Q(concatenated_order__isnull=True),
    }
    types_groups_without_concatenated_filters = {
        ALL: Q(is_concatenated_order=False),
        SINGLE: Q(is_concatenated_order=False),
        CONCATENATED: None,
        AGGREGATED: Q(is_concatenated_order=False),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(choices=self.choices, *args, **kwargs)

    def get_merchant(self):
        return self.parent.request.user.current_merchant

    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            value = self.ALL
        if self.distinct:
            qs = qs.distinct()

        if self.get_merchant().enable_concatenated_orders:
            qs_filter = self.types_groups_filters[value]
        else:
            qs_filter = self.types_groups_without_concatenated_filters[value]

        if qs_filter is not None:
            return qs.filter(qs_filter)
        else:
            return qs.none


class SortFilterBackend(filters.OrderingFilter):
    ordering_param = 'order_by'

    def get_qs_ordering(self, ordering, request, queryset, view):
        ordering_fields = dict(self.get_valid_fields(queryset, view, {'request': request}))

        distinct = []
        qs_ordering = []
        for item in ordering:
            descending = item[0] == '-'

            qs_fields = ordering_fields[item.lstrip('-')]
            if isinstance(qs_fields, str):
                qs_fields = (qs_fields,)

            distinct += qs_fields
            if descending:
                qs_ordering += [f'-{item}' for item in qs_fields]
            else:
                qs_ordering += qs_fields

        return qs_ordering, distinct

    def filter_queryset(self, request, queryset, view):
        exclude_ordering_from_actions = getattr(view, 'exclude_ordering_from_actions', [])
        if view.action in exclude_ordering_from_actions:
            return queryset

        ordering = self.get_ordering(request, queryset, view)

        if ordering:
            qs_ordering, distinct = self.get_qs_ordering(ordering, request, queryset, view)
            return queryset.order_by(*qs_ordering).distinct(*distinct, 'id')

        return queryset


class WebOrderFilterSet(OrderFilterSet):
    group = WebStatusGroupFilter()
    types_group = TypesGroupFilter()
    id = RadaroModelMultipleChoiceFilter(to_field_name='id', queryset=Order.aggregated_objects.all())

    class Meta(OrderFilterSet.Meta):
        fields = OrderFilterSet.Meta.fields + ['types_group', 'id']
