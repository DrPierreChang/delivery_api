from rest_framework import filters

from django_filters import rest_framework

from route_optimisation.models import DriverRoute, OptimisationTask, RouteOptimisation


class DriverRouteFilter(rest_framework.FilterSet):
    day = rest_framework.DateFilter(field_name='optimisation__day')

    class Meta:
        model = DriverRoute
        fields = ('day',)


class RouteOptimisationFilter(rest_framework.FilterSet):

    class Meta:
        model = RouteOptimisation
        fields = ('day',)


class LegacyStatusFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        if view.action != 'list' or request.GET.get('status', None) != 'in_progress':
            return queryset
        return queryset.filter(delayed_task__status=OptimisationTask.IN_PROGRESS)
