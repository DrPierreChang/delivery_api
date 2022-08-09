from django_filters import rest_framework as rest_filters

from route_optimisation.models import RouteOptimisation


class RouteOptimisationFilter(rest_filters.FilterSet):
    day = rest_filters.DateFromToRangeFilter()

    class Meta:
        model = RouteOptimisation
        fields = ('day', )
