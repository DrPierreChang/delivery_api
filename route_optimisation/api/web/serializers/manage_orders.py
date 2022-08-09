from datetime import datetime
from operator import attrgetter
from typing import Optional

from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from base.models import Member
from route_optimisation.const import HubOptions, RoutePointKind
from route_optimisation.exceptions import MoveOrdersError
from route_optimisation.models import DriverRoute, RouteOptimisation, RoutePoint
from route_optimisation.utils.managing import MovingPreliminaryResult
from schedule.models import Schedule
from tasks.mixins.order_status import OrderStatus


class DriverRouteValidator:
    def __init__(self):
        self.optimisation = None

    def set_context(self, serializer_field):
        self.optimisation = serializer_field.parent.instance

    def __call__(self, route):
        if route.optimisation_id != self.optimisation.id:
            raise serializers.ValidationError('Route not found in this {}'.format(_('optimisation')))
        if route.state not in (DriverRoute.STATE.CREATED, DriverRoute.STATE.RUNNING):
            raise serializers.ValidationError('Can not manage route in current state')


class OptimisationStateValidator:
    def __init__(self):
        self.optimisation = None

    def set_context(self, serializer_field):
        self.optimisation = serializer_field.instance

    def __call__(self, data):
        if self.optimisation.state not in (RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING):
            raise serializers.ValidationError('Can not manage {} in current state'.format(_('optimisation')))


class DifferentDriverValidator:
    def __call__(self, data):
        route = data['route']
        target_driver = data['target_driver']
        if route.driver_id == target_driver.id:
            raise serializers.ValidationError('Source driver and target driver are same')


class DriverWorkingValidator:
    def __init__(self):
        self.optimisation = None

    def set_context(self, serializer_field):
        self.optimisation = serializer_field.instance

    def __call__(self, data):
        target_driver = data['target_driver']
        schedule, _ = Schedule.objects.get_or_create(member_id=target_driver.id)
        schedule_item = schedule.get_day_schedule(self.optimisation.day)
        if schedule_item['day_off']:
            raise serializers.ValidationError('Target driver has day off')


class RoutePointBelongingValidator:
    def __call__(self, data):
        route = data['route']
        points = data['points']
        for point in points:
            if point.route_id != route.id:
                raise serializers.ValidationError('Point is not found in this route')


class MoveOnlyAssignedOrdersValidator:
    def __call__(self, data):
        points = data['points']
        for point in points:
            if point.point_kind != RoutePointKind.DELIVERY:
                continue
            if point.point_object.status != OrderStatus.ASSIGNED:
                raise serializers.ValidationError('You should move only assigned orders')


class SkillSetMatchingValidator:
    def __call__(self, data):
        points = data['points']
        driver = data['target_driver']
        driver_skill = set(map(attrgetter('id'), driver.skill_sets.all()))
        for point in points:
            if point.point_kind != RoutePointKind.DELIVERY:
                continue
            order_skill = set(map(attrgetter('id'), point.point_object.skill_sets.all()))
            if order_skill.difference(driver_skill):
                raise serializers.ValidationError('Target driver can not satisfy order skill set')


class CarCapacityValidator:
    def __call__(self, *args, **kwargs):
        raise NotImplementedError()

    def _validate(self, points, driver, use_vehicle_capacity, day):
        driver_capacity = 100000
        if use_vehicle_capacity:
            driver_capacity = (driver.car.get_capacity(day) if driver.car_id else None) or 1
        for point in points:
            if point.utilized_capacity > driver_capacity:
                raise serializers.ValidationError('Capacity of target driver car can not satisfy route capacity')


class ReorderCarCapacityValidator(CarCapacityValidator):
    def __call__(self, data):
        points_sequence = data['sequence']
        route = data['route']
        use_capacity = route.optimisation.optimisation_options.get('use_vehicle_capacity', False)
        self._validate(points_sequence, route.driver, use_capacity, route.optimisation.day)


class OtherDriverRouteIntersectionValidator:
    def __init__(self):
        self.optimisation = None

    def set_context(self, serializer_field):
        self.optimisation = serializer_field.instance

    def __call__(self, *args, **kwargs):
        raise NotImplementedError()

    def _validate(self, route):
        exclude_states = (RouteOptimisation.STATE.REMOVED, RouteOptimisation.STATE.FAILED,
                          RouteOptimisation.STATE.FINISHED,)
        day_routes = DriverRoute.objects \
            .filter(optimisation__day=self.optimisation.day, driver_id=route.driver_id) \
            .exclude(optimisation_id=self.optimisation.id) \
            .exclude(optimisation__state__in=exclude_states) \
            .prefetch_related('points__point_object')
        for day_route in day_routes:
            if route.start_time > day_route.start_time and route.start_time >= day_route.end_time:
                continue
            if route.end_time < day_route.end_time and route.end_time <= day_route.start_time:
                continue
            if route.start_time < day_route.end_time or route.end_time > day_route.start_time:
                raise serializers.ValidationError('Updated route intersects with other route of driver')


class MovingOrdersIntersectionValidator(OtherDriverRouteIntersectionValidator):
    def __call__(self, preliminary_result: MovingPreliminaryResult, data):
        self._validate(preliminary_result.target_route)


class ReorderIntersectionValidator(OtherDriverRouteIntersectionValidator):
    def __call__(self, data):
        self._validate(data['route'])


class UpdatedRouteTimeWindowValidator:
    def __call__(self, *args, **kwargs):
        raise NotImplementedError()

    def _validate(self, points, start_from=0):
        errors = []
        for idx, point in enumerate(points):
            if idx + 1 < start_from:
                continue
            if point.point_kind == RoutePointKind.PICKUP:
                pickup_after, pickup_before = point.point_object.pickup_after, point.point_object.pickup_before
                if pickup_after is not None and point.start_time < pickup_after:
                    errors.append('Point {} is out of pickup window'.format(point.point_object.title))
                elif pickup_before is not None and point.end_time > pickup_before:
                    errors.append('Point {} is out of pickup window'.format(point.point_object.title))
            if point.point_kind == RoutePointKind.DELIVERY:
                deliver_after, deliver_before = point.point_object.deliver_after, point.point_object.deliver_before
                if deliver_after is not None and point.start_time < deliver_after:
                    errors.append('Point {} is out of delivery window'.format(point.point_object.title))
                elif point.end_time > deliver_before:
                    errors.append('Point {} is out of delivery window'.format(point.point_object.title))
        return errors


class SourceRouteTimeWindowValidator(UpdatedRouteTimeWindowValidator):
    def __call__(self, preliminary_result: MovingPreliminaryResult, data):
        return self._validate(preliminary_result.result_source_points)


class TargetRouteTimeWindowValidator(UpdatedRouteTimeWindowValidator):
    def __call__(self, preliminary_result: MovingPreliminaryResult, data):
        return self._validate(preliminary_result.result_target_points)


class ReorderedRouteTimeWindowValidator(UpdatedRouteTimeWindowValidator):
    def __call__(self, data):
        route = data['route']
        points_sequence = data['sequence']
        existing_route = list(route.points.all().order_by('number'))
        changing_from_number = 0
        for from_existing, from_new in zip(existing_route, points_sequence):
            if from_existing.id != from_new.id:
                changing_from_number = from_existing.number
                break
        return self._validate(points_sequence, changing_from_number)


class UpdatedRouteDriverScheduleValidator:
    def __init__(self):
        self.optimisation = None

    def set_context(self, serializer_field):
        self.optimisation = serializer_field.instance

    def __call__(self, *args, **kwargs):
        raise NotImplementedError()

    def _validate(self, route):
        schedule, _ = Schedule.objects.get_or_create(member_id=route.driver_id)
        schedule_item = schedule.get_day_schedule(self.optimisation.day)
        if schedule_item['day_off']:
            return
        period = (
            datetime.combine(self.optimisation.day, schedule_item['start']),
            datetime.combine(self.optimisation.day, schedule_item['end']),
        )
        driver_after, driver_before = list(map(self.optimisation.merchant.timezone.localize, period))
        if route.start_time < driver_after or route.end_time > driver_before:
            return ['Route time is out of schedule of driver']
        return []


class TargetRouteDriverScheduleValidator(UpdatedRouteDriverScheduleValidator):
    def __call__(self, preliminary_result: MovingPreliminaryResult, data):
        return self._validate(preliminary_result.target_route)


class ReorderedRouteDriverScheduleValidator(UpdatedRouteDriverScheduleValidator):
    def __call__(self, data):
        return self._validate(data['route'])


class SequenceValidator:
    def __call__(self, data):
        route = data['route']
        sequence = data['sequence']
        for point in sequence:
            if point.route_id != route.id:
                raise serializers.ValidationError('Point is not found in this route')
        existing_matter_points = route.points.exclude(point_kind=RoutePointKind.BREAK).order_by('number')
        if len(sequence) != existing_matter_points.count():
            raise serializers.ValidationError('Count of points in new sequence is not right')
        if list(map(attrgetter('id'), sequence)) == list(map(attrgetter('id'), existing_matter_points)):
            raise serializers.ValidationError('Route sequence is not changed')


class CanReorderOnlyOrdersValidator:
    def __call__(self, data):
        start_point, end_point = data['sequence'][0], data['sequence'][-1]
        valid_point_kinds = (RoutePointKind.HUB, RoutePointKind.LOCATION)

        if start_point.point_kind not in valid_point_kinds:
            raise serializers.ValidationError('Route must start at hub or specific location but not order')

        end_place = end_point.route.optimisation.options.get('end_place')
        if end_point.point_kind in valid_point_kinds or end_place == HubOptions.END_HUB.job_location:
            return
        raise serializers.ValidationError('Route must finish at hub or specific location but not order')


class CanReorderOnlyNotFinishedOrdersValidator:
    def __call__(self, data):
        points_sequence = data['sequence']
        route = data['route']
        existing_route = list(route.points.all().order_by('number'))
        changing_from_number = 0
        for from_existing, from_new in zip(existing_route, points_sequence):
            if from_existing.id != from_new.id:
                changing_from_number = from_existing.number
                break
        for idx, point in enumerate(points_sequence):
            if idx + 1 < changing_from_number:
                continue
            if point.point_kind == RoutePointKind.PICKUP and point.point_object.status \
                    not in (OrderStatus.NOT_ASSIGNED, OrderStatus.ASSIGNED, OrderStatus.PICK_UP):
                raise serializers.ValidationError('Can not reorder passed pickup')
            if point.point_kind == RoutePointKind.DELIVERY and point.point_object.status \
                    in (OrderStatus.FAILED, OrderStatus.WAY_BACK, OrderStatus.DELIVERED):
                raise serializers.ValidationError('Can not reorder finished order')


class PickupBeforeDeliveryValidator:
    def __call__(self, data):
        points_sequence = data['sequence']
        delivery_index = set()
        for point in points_sequence:
            if point.point_kind == RoutePointKind.DELIVERY:
                delivery_index.add(point.point_object_id)
            if point.point_kind == RoutePointKind.PICKUP:
                object_id = point.point_object_id if point.point_object.concatenated_order_id is None \
                    else point.point_object.concatenated_order_id
                if object_id in delivery_index:
                    raise serializers.ValidationError('Pickup can not be after delivery')


class ManageSerializer(serializers.Serializer):
    def run_preliminary_result_validators(self, *args, **kwargs):
        meta = getattr(self, 'Meta', None)
        preliminary_result_validators = getattr(meta, 'preliminary_validators', None)
        if not preliminary_result_validators:
            return
        for validator in preliminary_result_validators:
            if hasattr(validator, 'set_context'):
                validator.set_context(self)
            validator(*args, **kwargs)

    def run_preliminary_result_soft_validators(self, *args, **kwargs):
        meta = getattr(self, 'Meta', None)
        preliminary_result_soft_validators = getattr(meta, 'preliminary_soft_validators', None)
        if not preliminary_result_soft_validators:
            return
        errors = []
        for validator in preliminary_result_soft_validators:
            if hasattr(validator, 'set_context'):
                validator.set_context(self)
            errors.extend(validator(*args, **kwargs) or [])
        if errors:
            raise serializers.ValidationError({'can_force': errors})


class MoveOrdersSerializer(ManageSerializer):
    route = serializers.PrimaryKeyRelatedField(queryset=DriverRoute.objects.all(), required=True,
                                               validators=(DriverRouteValidator(),))
    points = serializers.PrimaryKeyRelatedField(
        queryset=RoutePoint.objects.filter(point_kind=RoutePointKind.DELIVERY),
        many=True, required=True
    )
    target_driver = serializers.PrimaryKeyRelatedField(queryset=Member.drivers.all(), required=True)
    force = serializers.BooleanField(default=False, required=False)

    class Meta:
        validators = (
            OptimisationStateValidator(),
            DifferentDriverValidator(),
            RoutePointBelongingValidator(),
            MoveOnlyAssignedOrdersValidator(),
            SkillSetMatchingValidator(),
            DriverWorkingValidator(),
        )
        preliminary_validators = (
            MovingOrdersIntersectionValidator(),
        )
        preliminary_soft_validators = (
            SourceRouteTimeWindowValidator(),
            TargetRouteTimeWindowValidator(),
            TargetRouteDriverScheduleValidator(),
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.preliminary_result: Optional[MovingPreliminaryResult] = None

    def validate(self, attrs):
        source_route, moved_points, target_driver = attrs['route'], attrs['points'], attrs['target_driver']
        try:
            preliminary_result = self.instance.backend.prepare_move_orders(
                moved_points, source_route, target_driver,
                initiator=self.context['request'].user, context=self.context
            )
        except MoveOrdersError as exc:
            raise serializers.ValidationError(exc.args[0])
        self.run_preliminary_result_validators(preliminary_result, attrs)
        if not attrs.get('force'):
            self.run_preliminary_result_soft_validators(preliminary_result, attrs)
        self.preliminary_result = preliminary_result
        return attrs

    def save(self, **kwargs):
        self.instance.backend.on_move_orders(
            self.preliminary_result, initiator=self.context['request'].user
        )


class ChangeSequenceSerializer(ManageSerializer):
    route = serializers.PrimaryKeyRelatedField(queryset=DriverRoute.objects.all(), required=True,
                                               validators=(DriverRouteValidator(),))
    sequence = serializers.PrimaryKeyRelatedField(queryset=RoutePoint.objects.all(), many=True, required=True)
    force = serializers.BooleanField(default=False, required=False)

    class Meta:
        validators = (
            OptimisationStateValidator(),
            SequenceValidator(),
            CanReorderOnlyOrdersValidator(),
            CanReorderOnlyNotFinishedOrdersValidator(),
            PickupBeforeDeliveryValidator(),
        )
        preliminary_validators = (
            ReorderCarCapacityValidator(),
            ReorderIntersectionValidator(),
        )
        preliminary_soft_validators = (
            ReorderedRouteTimeWindowValidator(),
            ReorderedRouteDriverScheduleValidator(),
        )

    def validate(self, attrs):
        self.instance.backend.sequence_reorder_service.prepare(attrs['route'], attrs['sequence'])
        self.run_preliminary_result_validators(attrs)
        if not attrs.get('force'):
            self.run_preliminary_result_soft_validators(attrs)
        return attrs

    def save(self, **kwargs):
        self.instance.backend.sequence_reorder_service.save(
            self.validated_data['route'], self.validated_data['sequence'],
            initiator=self.context['request'].user
        )
