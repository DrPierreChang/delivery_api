from django.db.models import Q
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from rest_framework import filters
from rest_framework.exceptions import ValidationError

from django_filters import rest_framework as rest_filters
from django_filters.constants import EMPTY_VALUES

from merchant.models import SkillSet
from radaro_utils.filters.rest_framework_filters import RadaroModelMultipleChoiceFilter
from route_optimisation.const import GroupConst
from route_optimisation.models import DriverRoute, DriverRouteLocation, OptimisationTask, RouteOptimisation
from tasks.mixins.order_status import OrderStatus


class RouteOptimisationFilter(rest_filters.FilterSet):
    day = rest_filters.DateFromToRangeFilter()

    class Meta:
        model = RouteOptimisation
        fields = ('day', )


class GroupFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        if view.action != 'list':
            return queryset
        group = request.GET.get('group', None)
        queryset = queryset.filter(delayed_task__status__in=[OptimisationTask.COMPLETED, OptimisationTask.IN_PROGRESS])
        if group is None or group == GroupConst.ALL:
            return queryset
        today = timezone.now().astimezone(request.user.current_merchant.timezone).date()
        if group == GroupConst.FAILED:
            return queryset.filter(state=RouteOptimisation.STATE.FAILED)
        elif group == GroupConst.SCHEDULED:
            return queryset.filter(state__in=[RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING],
                                   day__gt=today)
        elif group == GroupConst.CURRENT:
            return queryset.filter(state__in=[RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING],
                                   day=today)
        # TODO: some exception
        raise Exception('bad param')


class DriverRouteLocationFilter(rest_filters.FilterSet):
    id = RadaroModelMultipleChoiceFilter(to_field_name='id', queryset=DriverRouteLocation.objects.all())

    class Meta:
        model = DriverRouteLocation
        fields = ('id',)


class DriverRouteFilter(rest_filters.FilterSet):
    id = RadaroModelMultipleChoiceFilter(to_field_name='id', queryset=DriverRoute.objects.all())
    optimisation = RadaroModelMultipleChoiceFilter(to_field_name='id', queryset=RouteOptimisation.objects.all())

    class Meta:
        model = DriverRoute
        fields = ('id', 'optimisation')


class RouteFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        route = request.GET.get('route', '')
        if route in EMPTY_VALUES:
            route = None

        if route is not None:
            try:
                route = int(route)
            except ValueError:
                raise ValidationError(
                    {'route': [_('"{}" is not a valid value.').format(route)]},
                    code='invalid_pk_value',
                )

        if route is not None:
            route = view.optimisation.routes.filter(id=route).first()

        driver_ids = view.optimisation.routes.values_list('driver_id', flat=True)
        if route is not None:
            driver_ids = driver_ids.filter(id=route.id)

        driver_ids = list(driver_ids)

        jobs_filter = Q(driver_id__in=driver_ids)

        free_jobs_filter = Q(driver_id__isnull=True, status=OrderStatus.NOT_ASSIGNED)
        merchant = view.optimisation.merchant
        if merchant.enable_skill_sets:
            exclude_skills = SkillSet.objects.filter(merchant=merchant).exclude(drivers__in=driver_ids)
            free_jobs_filter &= ~Q(skill_sets__in=exclude_skills)

        return queryset.filter(jobs_filter | free_jobs_filter)
