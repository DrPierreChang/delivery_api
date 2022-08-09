import logging

from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers
from rest_framework.fields import TimeField

from drf_extra_fields.fields import RangeField
from psycopg2._range import DateTimeRange

from base.models import Member
from merchant.models import Hub
from route_optimisation.const import OPTIMISATION_TYPES, HubOptions, RoutePointKind
from route_optimisation.exceptions import OptimisationValidError
from route_optimisation.logging import EventType
from route_optimisation.models import DriverRoute, RoutePoint
from route_optimisation.utils.validation.fields import OptimisationPrimaryKeyRelatedField
from routing.serializers.fields import LatLngLocation
from tasks.models import Order

logger = logging.getLogger('optimisation')


class TimeRangeField(RangeField):
    child = TimeField()
    range_type = DateTimeRange


class JobsIdsField(OptimisationPrimaryKeyRelatedField):
    def get_queryset(self):
        ctx = self.context
        merchant = ctx.get('merchant') if 'merchant' in ctx else ctx['request'].user.current_merchant
        queryset = Order.aggregated_objects.filter_by_merchant(merchant)
        queryset = queryset.select_related('deliver_address', 'merchant').prefetch_related('skill_sets')
        return queryset


class AdvancedRouteOptimisationValidateOptionsSerializer(serializers.Serializer):
    jobs_ids = JobsIdsField(
        queryset=Order.aggregated_objects.all(), required=True, many=True, raise_not_exist=False
    )
    drivers_ids = OptimisationPrimaryKeyRelatedField(
        queryset=Member.drivers.all().select_related('car').prefetch_related('skill_sets'),
        required=False, allow_null=True, many=True, raise_not_exist=False,
    )

    working_hours = TimeRangeField(required=False, allow_null=True)
    service_time = serializers.IntegerField(required=False, allow_null=True)
    pickup_service_time = serializers.IntegerField(required=False, allow_null=True)

    start_place = serializers.ChoiceField(choices=HubOptions.START_HUB, required=False, allow_null=True)
    start_hub = OptimisationPrimaryKeyRelatedField(queryset=Hub.objects.all(), required=False, allow_null=True)
    end_place = serializers.ChoiceField(choices=HubOptions.END_HUB, required=False, allow_null=True)
    end_hub = OptimisationPrimaryKeyRelatedField(queryset=Hub.objects.all(), required=False, allow_null=True)

    re_optimise_assigned = serializers.BooleanField(required=False, allow_null=True, default=False)
    use_vehicle_capacity = serializers.BooleanField(required=False, allow_null=True, default=False)

    class Meta:
        fields = (
            'jobs_ids', 'drivers_ids', 'working_hours', 'service_time', 'pickup_service_time',
            'start_place', 'start_hub', 'end_place', 'end_hub',
            'use_vehicle_capacity', 're_optimise_assigned',
        )

    def validate_use_vehicle_capacity(self, value):
        if value is True and self.context['optimisation'].merchant.enable_job_capacity is False:
            raise serializers.ValidationError(
                'Vehicle Capacity feature is disabled, '
                'please turn this on to create {} that accounts Vehicle Capacity'.format(_('Optimisation'))
            )
        return value

    def validate_working_hours(self, value):
        if not value:
            return
        optimisation = self.context['optimisation']
        now = timezone.now().astimezone(optimisation.merchant.timezone)
        if now.date() == optimisation.day and now.time() > value.lower:
            logger.info(None, extra=dict(obj=optimisation, event=EventType.VALIDATION_ERROR,
                                         event_kwargs={'code': 'working_hours'}))
            raise OptimisationValidError('Wrong working hours')
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get('start_place') == HubOptions.START_HUB.hub_location and attrs.get('start_hub') is None:
            raise serializers.ValidationError('No start hub passed')
        if attrs.get('end_place') == HubOptions.END_HUB.hub_location and attrs.get('end_hub') is None:
            raise serializers.ValidationError('No end hub passed')
        return attrs


class SoloOptimisationDriver:
    def __init__(self):
        self.context = None

    def set_context(self, serializer_field):
        self.context = serializer_field.context

    def __call__(self):
        optimisation = self.context['optimisation']
        assert optimisation.type == OPTIMISATION_TYPES.SOLO

        drivers = self.context['optimisation'].drivers
        if not drivers:
            user = self.context['request'].user
            if user.is_driver:
                drivers = [user]

        return drivers

    def __repr__(self):
        return self.__class__.__name__


class DriverRouteLocationSerializer(serializers.Serializer):
    location = LatLngLocation(required=True)


class SoloRouteOptimisationValidateOptionsSerializer(serializers.Serializer):
    jobs_ids = JobsIdsField(
        queryset=Order.aggregated_objects.all(), required=False, allow_null=True, many=True, raise_not_exist=False,
    )
    drivers_ids = OptimisationPrimaryKeyRelatedField(
        queryset=Member.drivers.all().select_related('car').prefetch_related('skill_sets'),
        required=False, allow_null=True, many=True, raise_not_exist=False,
        default=SoloOptimisationDriver(),
    )

    start_place = serializers.ChoiceField(choices=HubOptions.START_HUB, required=False, allow_null=True)
    start_hub = OptimisationPrimaryKeyRelatedField(queryset=Hub.objects.all(), required=False, allow_null=True)
    start_location = DriverRouteLocationSerializer(required=False, allow_null=True)
    end_place = serializers.ChoiceField(choices=HubOptions.END_HUB, required=False, allow_null=True)
    end_hub = OptimisationPrimaryKeyRelatedField(queryset=Hub.objects.all(), required=False, allow_null=True)
    end_location = DriverRouteLocationSerializer(required=False, allow_null=True)

    re_optimise_assigned = serializers.BooleanField(required=False, allow_null=True, default=False)
    use_vehicle_capacity = serializers.BooleanField(required=False, allow_null=True, default=False)

    working_hours = TimeRangeField(required=False, allow_null=True)
    service_time = serializers.IntegerField(required=False, allow_null=True)
    pickup_service_time = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        fields = (
            'jobs_ids', 'drivers_ids',
            'start_place', 'start_hub', 'start_location',
            'end_place', 'end_hub', 'end_location',
            'use_vehicle_capacity', 're_optimise_assigned',
            'working_hours', 'service_time', 'pickup_service_time',
        )

    def validate_use_vehicle_capacity(self, value):
        if value is True and self.context['optimisation'].merchant.enable_job_capacity is False:
            raise serializers.ValidationError(
                _('Vehicle Capacity feature is disabled, '
                  'please turn this on to create {optimisation} that accounts Vehicle Capacity'
                  .format(optimisation=_('Optimisation')))
            )
        return value

    def validate_working_hours(self, value):
        if not value:
            return
        optimisation = self.context['optimisation']
        now = timezone.now().astimezone(optimisation.merchant.timezone)
        if now.date() == optimisation.day and now.time() > value.lower:
            logger.info(None, extra=dict(obj=optimisation, event=EventType.VALIDATION_ERROR,
                                         event_kwargs={'code': 'working_hours'}))
            raise OptimisationValidError(_('Wrong working hours'))
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)

        if attrs.get('start_place'):
            if attrs.get('start_place') == HubOptions.START_HUB.hub_location and attrs.get('start_hub') is None:
                raise serializers.ValidationError(_('No start hub passed'))
        else:
            attrs['start_place'] = (
                (attrs.get('start_hub') and HubOptions.START_HUB.hub_location)
                or (attrs.get('start_location') and HubOptions.START_HUB.driver_location)
                or HubOptions.START_HUB.default_hub
            )

        if attrs.get('end_place'):
            if attrs.get('end_place') == HubOptions.END_HUB.hub_location and attrs.get('end_hub') is None:
                raise serializers.ValidationError(_('No end hub passed'))
        else:
            attrs['end_place'] = (
                (attrs.get('end_hub') and HubOptions.END_HUB.hub_location)
                or (attrs.get('end_location') and HubOptions.END_HUB.driver_location)
                or HubOptions.END_HUB.default_hub
            )

        if attrs.get('jobs_ids', None) is None:
            if attrs.get('drivers_ids'):
                driver_ids = [driver.id for driver in attrs['drivers_ids']]
                jobs_qs = self.context['optimisation'].get_available_orders().filter(driver_id__in=driver_ids)
                attrs['jobs_ids'] = list(jobs_qs)
            else:
                attrs['jobs_ids'] = []

        return attrs


class RefreshSoloRouteOptimisationValidateOptionsSerializer(SoloRouteOptimisationValidateOptionsSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        dummy_optimisation = self.context['optimisation']

        new_job_ids = [job.id for job in attrs['jobs_ids']]
        optimised_job_ids = RoutePoint.objects.filter(
            route__optimisation_id=dummy_optimisation.source_optimisation.id,
            point_kind=RoutePointKind.DELIVERY
        ).values_list('point_object_id', flat=True)
        order_ids = list(set(new_job_ids) | set(optimised_job_ids))

        orders = Order.aggregated_objects.filter_by_merchant(dummy_optimisation.merchant).filter(id__in=order_ids)
        attrs['jobs_ids'] = list(orders)

        if attrs.get('start_location', None) is not None:
            attrs['start_location']['id'] = RoutePoint.objects.filter(
                route__optimisation_id=dummy_optimisation.source_optimisation.id,
                point_kind=RoutePointKind.LOCATION
            ).order_by('number').values_list('point_object_id', flat=True).first()

        if attrs.get('end_location', None) is not None:
            attrs['end_location']['id'] = RoutePoint.objects.filter(
                route__optimisation_id=dummy_optimisation.source_optimisation.id,
                point_kind=RoutePointKind.LOCATION
            ).order_by('number').values_list('point_object_id', flat=True).last()

        return attrs


class RefreshAdvancedRouteOptimisationValidateOptionsSerializer(AdvancedRouteOptimisationValidateOptionsSerializer):
    jobs_ids = JobsIdsField(
        queryset=Order.aggregated_objects.all(), required=False, many=True, raise_not_exist=False
    )
    route = serializers.PrimaryKeyRelatedField(queryset=DriverRoute.objects.all(), required=True)

    def validate(self, attrs):
        # At this stage, the refresh only works for one route.
        # Therefore, only orders and drivers of this route are used.
        attrs = super().validate(attrs)
        dummy_optimisation = self.context['optimisation']
        route = attrs.pop('route')

        if attrs.get('jobs_ids', None) is None:
            new_job_qs = self.context['optimisation'].get_available_orders().filter(driver_id=route.driver_id)
            new_job_ids = list(new_job_qs.values_list('id', flat=True))
        else:
            new_job_ids = [job.id for job in attrs['jobs_ids']]

        optimised_job_ids = RoutePoint.objects.filter(
            route=route,
            point_kind=RoutePointKind.DELIVERY
        ).values_list('point_object_id', flat=True)
        order_ids = list(set(new_job_ids) | set(optimised_job_ids))

        orders = Order.aggregated_objects.filter_by_merchant(dummy_optimisation.merchant).filter(id__in=order_ids)
        attrs['jobs_ids'] = list(orders)

        attrs['drivers_ids'] = [route.driver]

        return attrs


class MoveOrdersValidateOptionsSerializer(serializers.Serializer):
    jobs_ids = JobsIdsField(
        queryset=Order.aggregated_objects.all(), required=False, allow_null=True, many=True, raise_not_exist=False,
    )
    drivers_ids = OptimisationPrimaryKeyRelatedField(
        queryset=Member.drivers.all().select_related('car').prefetch_related('skill_sets'),
        required=False, allow_null=True, many=True, raise_not_exist=False,
    )

    working_hours = TimeRangeField(required=False, allow_null=True)
    service_time = serializers.IntegerField(required=False, allow_null=True)
    pickup_service_time = serializers.IntegerField(required=False, allow_null=True)

    start_place = serializers.ChoiceField(choices=HubOptions.START_HUB, required=False, allow_null=True)
    start_hub = OptimisationPrimaryKeyRelatedField(queryset=Hub.objects.all(), required=False, allow_null=True)
    start_location = DriverRouteLocationSerializer(required=False, allow_null=True)
    end_place = serializers.ChoiceField(choices=HubOptions.END_HUB, required=False, allow_null=True)
    end_hub = OptimisationPrimaryKeyRelatedField(queryset=Hub.objects.all(), required=False, allow_null=True)
    end_location = DriverRouteLocationSerializer(required=False, allow_null=True)

    re_optimise_assigned = serializers.BooleanField(required=False, allow_null=True, default=False)
    use_vehicle_capacity = serializers.BooleanField(required=False, allow_null=True, default=False)

    class Meta:
        fields = (
            'jobs_ids', 'drivers_ids',
            'start_place', 'start_hub', 'start_location',
            'end_place', 'end_hub', 'end_location',
            'use_vehicle_capacity', 're_optimise_assigned',
            'working_hours', 'service_time', 'pickup_service_time',
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs.get('start_place'):
            attrs['start_place'] = (attrs.get('start_hub') and HubOptions.START_HUB.hub_location) \
                                   or (attrs.get('start_location') and HubOptions.START_HUB.driver_location) \
                                   or HubOptions.START_HUB.default_hub
        if not attrs.get('end_place'):
            attrs['end_place'] = (attrs.get('end_hub') and HubOptions.END_HUB.hub_location) \
                                 or (attrs.get('end_location') and HubOptions.END_HUB.driver_location) \
                                 or HubOptions.END_HUB.default_hub
        return attrs
