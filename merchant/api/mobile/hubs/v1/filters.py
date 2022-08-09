from distutils.util import strtobool

from rest_framework import filters


class DriverHubsFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        try:
            wayback = request.query_params.get('wayback', '')
            bool_wayback = strtobool(wayback)

            if bool_wayback:
                return queryset.filter(drivers=request.user)

        except ValueError:
            pass

        return queryset
