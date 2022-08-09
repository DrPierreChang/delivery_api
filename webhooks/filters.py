from django.contrib import admin

import django_filters

from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

from .models import MerchantAPIKey


class BaseMerchantAPIKeyFilter(admin.SimpleListFilter):
    title = "Merchant's apikey"

    def lookups(self, request, model_admin):
        return [(key.id, '%s (%s)' % (key.name, key.key)) for key in MerchantAPIKey.objects.all()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{self.parameter_name: self.value()})
        else:
            return queryset


class OrderMerchantAPIKeyFilter(BaseMerchantAPIKeyFilter):
    parameter_name = 'external_job__source_id'


class ExternalOrderMerchantAPIKeyFilter(BaseMerchantAPIKeyFilter):
    parameter_name = 'source_id'


class OrderFilterSet(django_filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(choices=OrderStatus._status)
    # ?status=failed&status=delivered
    deliver_before = django_filters.IsoDateTimeFromToRangeFilter()
    # ?deliver_before_after=2015-01-08T21:00:00.000Z&deliver_before_before=2025-01-05T21:00:00.000Z

    class Meta:
        model = Order
        fields = ['status', 'deliver_before']
