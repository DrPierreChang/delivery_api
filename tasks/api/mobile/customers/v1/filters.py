import re

import django_filters
from django_filters.constants import EMPTY_VALUES
from django_filters.rest_framework import FilterSet

from tasks.models import Customer, Pickup


class PhoneFilter(django_filters.CharFilter):
    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs

        # Converts the phone number to e164 format, in which numbers are stored in db
        value = re.sub('[-_() ]', '', value)
        return super().filter(qs, value)


class CustomerFilterSet(FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    phone_number = PhoneFilter(field_name='phone', lookup_expr='icontains')

    class Meta:
        model = Customer
        fields = ['name', 'phone_number']


class PickupCustomerFilterSet(FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    phone_number = PhoneFilter(field_name='phone', lookup_expr='icontains')

    class Meta:
        model = Pickup
        fields = ['name', 'phone_number']
