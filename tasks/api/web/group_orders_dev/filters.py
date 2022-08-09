from django.db.models import Q

from rest_framework import filters

from tasks.api.mobile.filters.v1 import OrderFilterSet


class GroupOrderFilterSet(OrderFilterSet):
    sub_branding = None

    class Meta(OrderFilterSet.Meta):
        exclude = ['sub_branding', ]


class GroupMerchantFilter(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        merchant_ids, sub_brand_ids = request.GET.getlist('merchant', []), request.GET.getlist('sub_branding', [])
        filter_condition = Q()
        if merchant_ids:
            filter_condition |= Q(merchant_id__in=merchant_ids, sub_branding__isnull=True)
        if sub_brand_ids:
            filter_condition |= Q(sub_branding_id__in=sub_brand_ids)
        return queryset.filter(filter_condition)
