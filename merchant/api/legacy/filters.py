import django_filters

from tasks.models import Customer


class CustomerFilterSet(django_filters.FilterSet):
    phone = django_filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = Customer
        fields = ['phone']
