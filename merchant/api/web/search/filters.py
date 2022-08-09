from django.db.models import Q

from django_filters import CharFilter
from django_filters.constants import EMPTY_VALUES
from django_filters.rest_framework import FilterSet
from watson.models import SearchEntry

from base.models import Member
from tasks.models import BulkDelayedUpload


class SearchFilter(CharFilter):
    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs.none()
        if len(value) < 3:
            return qs.none()

        if self.distinct:
            qs = qs.distinct()

        merchant = self.parent.request.user.current_merchant
        orders_q = Q(
            Q(orders_search_entries__bulk__isnull=True)
            | Q(orders_search_entries__bulk__status=BulkDelayedUpload.CONFIRMED),
            orders_search_entries__deleted=False,
            orders_search_entries__merchant_id=merchant.id,
            orders_search_entries__is_concatenated_order=False,
        )
        members_q = Q(
            members_search_entries__is_active=True,
            members_search_entries__role__in=[Member.DRIVER, Member.MANAGER_OR_DRIVER],
            members_search_entries__merchant_id=merchant.id,
        )
        return qs.filter(content__icontains=value).filter(orders_q | members_q)


class SearchFilterSet(FilterSet):
    q = SearchFilter(required=True)

    class Meta:
        model = SearchEntry
        fields = ['q']
