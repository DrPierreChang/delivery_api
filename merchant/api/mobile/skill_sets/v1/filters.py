from distutils.util import strtobool

from django.db.models import Q

from rest_framework import filters


class SkillSetAssignedFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        try:
            assigned = request.query_params.get('assigned', '')
            bool_assigned = strtobool(assigned)
            if bool_assigned:
                return queryset.filter(drivers=request.user)
            else:
                return queryset.filter(is_secret=False).exclude(drivers=request.user)
        except ValueError:
            return queryset.filter(Q(is_secret=False) | Q(drivers=request.user)).distinct()
