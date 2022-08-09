from operator import attrgetter

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from rest_framework import serializers

from base.models import Member
from merchant.models import Hub
from route_optimisation.const import OPTIMISATION_TYPES, HubOptions
from route_optimisation.models import RouteOptimisation, RoutePoint
from route_optimisation.utils.validation.fields import ContextMerchantOptimisationPrimaryKeyRelatedField
from route_optimisation.utils.validation.serializers import TimeRangeField
from schedule.models import Schedule
from tasks.models import Order


class DeliveryDayNotExpired:
    requires_context = True
    field_name = None
    keys = {}

    def set_context(self, serializer):
        self.keys = {order.pk: key for key, order in serializer.preload_items.items()}
        self.field_name = serializer.field_name

    def __call__(self, orders, *args, **kwargs):
        for order in orders:
            if order.deliver_before <= timezone.now():
                raise serializers.ValidationError(
                    'Order with {} "{}" expired'.format(self.field_name[:-1], self.keys[order.pk])
                )


class MatchingRODayWithDeliveryDay:
    timezone = None
    day = None
    field_name = None
    keys = {}

    def set_context(self, serializer):
        self.keys = {order.pk: key for key, order in serializer.preload_items.items()}
        self.timezone = serializer.context['merchant'].timezone
        self.day = serializer.context['day']
        self.field_name = serializer.field_name

    def __call__(self, orders, *args, **kwargs):
        for order in orders:
            if order.deliver_before.astimezone(self.timezone).date() != self.day:
                raise serializers.ValidationError(
                    'Order delivery day with {} "{}" does not matching with the optimisation day'.format(
                        self.field_name[:-1], self.keys[order.pk])
                )


class DeliveryDuringDriversWorkingHours:
    day = None

    def __init__(self, drivers_field, working_hours_field):
        self.drivers_field = drivers_field
        self.working_hours_field = working_hours_field

    def set_context(self, serializer):
        self.day = serializer.context['day']

    def __call__(self, attrs):
        working_hours = attrs.get(self.working_hours_field, None)
        if not working_hours:
            return
        drivers = attrs.get(self.drivers_field, [])
        for driver in drivers:
            try:
                schedule = driver.schedule.get_day_schedule(self.day)
                if schedule['day_off']:
                    continue
                if schedule['start'] >= working_hours.upper or schedule['end'] <= working_hours.lower:
                    continue
                return
            except Schedule.DoesNotExist:
                return
        raise serializers.ValidationError({self.drivers_field: 'There are no available drivers'})


class OrdersIntersectionOtherOptimisation:
    day = None

    def set_context(self, serializer):
        self.day = serializer.context['day']

    def __call__(self, attrs):
        order_ct = ContentType.objects.get_for_model(Order)
        exclude_states = (RouteOptimisation.STATE.REMOVED, RouteOptimisation.STATE.FAILED,
                          RouteOptimisation.STATE.FINISHED,)
        ids = RoutePoint.objects.filter(route__optimisation__day=self.day, point_content_type=order_ct) \
            .exclude(route__optimisation__state__in=exclude_states) \
            .values_list('point_object_id', flat=True)
        ids = list(ids)
        if ids:
            order_ids = map(attrgetter('id'), attrs.get('order_ids', []))
            external_ids = map(attrgetter('id'), attrs.get('external_ids', []))
            passed_orders = set(order_ids).union(external_ids)
            available_orders = passed_orders.difference(ids)
            if passed_orders and not available_orders:
                raise serializers.ValidationError('All orders are already in another optimisation')


class DriverDefaultHubs:
    def __init__(self, drivers_field):
        self.drivers_field = drivers_field

    def __call__(self, attrs):
        drivers = attrs.get(self.drivers_field, [])
        if attrs['start_place'] == HubOptions.EXTERNAL_START_HUB.default_hub:
            for driver in drivers:
                if driver.starting_hub_id is None:
                    raise serializers.ValidationError({
                        self.drivers_field:
                            '{} driver with {} "{}" has no default start hub'.format(
                                driver.get_full_name(), self.drivers_field[:-1], driver.member_id)
                    })
        if attrs['end_place'] == HubOptions.EXTERNAL_END_HUB.default_hub:
            for driver in drivers:
                if driver.ending_hub_id is None:
                    raise serializers.ValidationError({
                        self.drivers_field:
                            '{} driver with {} "{}" has no default end hub'.format(
                                driver.get_full_name(), self.drivers_field[:-1], driver.member_id)
                    })


class DriversFromAssignedOrders:
    keys = {}

    def __init__(self, drivers_field, orders_field):
        self.drivers_field = drivers_field
        self.orders_field = orders_field

    def set_context(self, serializer):
        self.keys = {order.pk: key for key, order in serializer.fields[self.orders_field].preload_items.items()}

    def __call__(self, attrs):
        orders = attrs.get(self.orders_field, [])
        drivers = attrs.get(self.drivers_field, [])
        driver_ids = [driver.id for driver in drivers]

        for order in orders:
            if order.status == order.ASSIGNED and order.driver_id not in driver_ids:
                raise serializers.ValidationError({
                    self.orders_field:
                        'No driver assigned to order with {} "{}"'.format(self.orders_field[:-1], self.keys[order.pk])
                })


class SkillSetMatching:
    keys = {}

    def __init__(self, drivers_field, orders_field):
        self.drivers_field = drivers_field
        self.orders_field = orders_field

    def set_context(self, serializer):
        self.keys = {order.pk: key for key, order in serializer.fields[self.orders_field].preload_items.items()}

    def __call__(self, attrs):
        orders = attrs.get(self.orders_field, [])
        orders_skill_sets = {order.id: {skill_set.id for skill_set in order.skill_sets.all()} for order in orders}
        drivers = attrs.get(self.drivers_field, [])
        drivers_skill_sets = [{skill_set.id for skill_set in driver.skill_sets.all()} for driver in drivers]

        for order_id, order_skill_sets in orders_skill_sets.items():
            if not any(not (order_skill_sets - driver_skill_sets) for driver_skill_sets in drivers_skill_sets):
                raise serializers.ValidationError({
                    self.orders_field:
                        'No drivers with skills matching order with {} "{}"'.format(
                            self.orders_field[:-1], self.keys[order_id])
                })


class ExternalOptionsOptimisationSerializer(serializers.Serializer):
    start_place = serializers.ChoiceField(choices=HubOptions.EXTERNAL_START_HUB, required=True)
    start_hub = ContextMerchantOptimisationPrimaryKeyRelatedField(queryset=Hub.objects.all(), required=False, allow_null=True)
    end_place = serializers.ChoiceField(choices=HubOptions.EXTERNAL_END_HUB, required=True)
    end_hub = ContextMerchantOptimisationPrimaryKeyRelatedField(queryset=Hub.objects.all(), required=False, allow_null=True)

    order_ids = ContextMerchantOptimisationPrimaryKeyRelatedField(
        queryset=Order.objects.all().prefetch_related('skill_sets'),
        lookup_field='order_id', required=False, many=True, raise_not_exist=True,
        validators=[DeliveryDayNotExpired(), MatchingRODayWithDeliveryDay()], pk_field=serializers.IntegerField(),
    )
    external_ids = ContextMerchantOptimisationPrimaryKeyRelatedField(
        queryset=Order.objects.all().select_related('external_job').prefetch_related('skill_sets'),
        lookup_field='external_job__external_id', required=False, many=True, raise_not_exist=True,
        validators=[DeliveryDayNotExpired(), MatchingRODayWithDeliveryDay()], pk_field=serializers.CharField(),
    )
    member_ids = ContextMerchantOptimisationPrimaryKeyRelatedField(
        queryset=Member.drivers.all().prefetch_related('skill_sets'),
        lookup_field='member_id', required=True, many=True, raise_not_exist=True, pk_field=serializers.IntegerField()
    )
    working_hours = TimeRangeField(required=True)

    def validate_working_hours(self, value):
        if not value.lower or not value.upper:
            raise serializers.ValidationError('Keys \'lower\' and \'upper\' are required')
        if value.lower >= value.upper:
            raise serializers.ValidationError('Invalid range')

        day = self.context['day']
        merchant_tz = self.context['merchant'].timezone
        now = timezone.now().astimezone(merchant_tz)
        if now.date() == day and now.time() > value.lower:
            raise serializers.ValidationError('Working hours includes the time in the past')

        return value

    def validate_member_ids(self, members):
        if not members:
            raise serializers.ValidationError('No drivers passed')
        if self.context['type'] == OPTIMISATION_TYPES.SOLO:
            if len(members) != 1:
                raise serializers.ValidationError('There must be one driver')
        return members

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get('start_place') == HubOptions.EXTERNAL_START_HUB.hub_location and attrs.get('start_hub') is None:
            raise serializers.ValidationError('No start hub passed')
        if attrs.get('end_place') == HubOptions.EXTERNAL_END_HUB.hub_location and attrs.get('end_hub') is None:
            raise serializers.ValidationError('No end hub passed')
        if not attrs.get('order_ids') and not attrs.get('external_ids'):
            raise serializers.ValidationError('No orders passed')
        return attrs

    class Meta:
        validators = [
            DeliveryDuringDriversWorkingHours('member_ids', 'working_hours'),
            DriverDefaultHubs('member_ids'),
            DriversFromAssignedOrders('member_ids', 'order_ids'),
            DriversFromAssignedOrders('member_ids', 'external_ids'),
            SkillSetMatching('member_ids', 'order_ids'),
            SkillSetMatching('member_ids', 'external_ids'),
            OrdersIntersectionOtherOptimisation(),
        ]
