from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from rest_framework import serializers

from base.models import Member
from merchant.models import Hub
from route_optimisation.const import CONTEXT_HELP_ITEM, RoutePointKind
from route_optimisation.engine.base_classes.parameters import JobKind
from route_optimisation.models import RoutePoint
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order


class PickupSerializer(serializers.ModelSerializer):
    pickup_id = serializers.IntegerField(source='id')
    pickup_address = serializers.SerializerMethodField()
    pickup_after = serializers.SerializerMethodField()
    pickup_before = serializers.SerializerMethodField()
    capacity = serializers.FloatField()
    service_time = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            'pickup_id',
            'pickup_address', 'pickup_after', 'pickup_before',
            'capacity', 'service_time',
        )

    def get_pickup_address(self, order):
        return order.pickup_address_id and order.pickup_address.location

    def get_pickup_after(self, order):
        if not order.pickup_after:
            return
        return order.pickup_after.astimezone(order.merchant.timezone).isoformat()

    def get_pickup_before(self, order):
        if not order.pickup_before:
            return
        return order.pickup_before.astimezone(order.merchant.timezone).isoformat()

    def get_service_time(self, order):
        return None


class JobSerializer(serializers.ModelSerializer):
    deliver_address = serializers.CharField(source='deliver_address.location')
    deliver_after = serializers.SerializerMethodField()
    deliver_before = serializers.SerializerMethodField()
    pickups = serializers.SerializerMethodField()
    driver_member_id = serializers.SerializerMethodField()
    capacity = serializers.SerializerMethodField()
    service_time = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            'id', 'order_id',
            'deliver_after', 'deliver_before', 'deliver_address',
            'pickups',
            'driver_member_id', 'skill_set', 'capacity',
            'service_time',
        )
        extra_kwargs = {
            'skill_set': {'source': 'skill_sets'}
        }

    def get_deliver_after(self, order):
        if not order.deliver_after:
            return
        return order.deliver_after.astimezone(order.merchant.timezone).isoformat()

    def get_deliver_before(self, order):
        return order.deliver_before.astimezone(order.merchant.timezone).isoformat()

    def get_pickups(self, order):
        if not order.merchant.use_pick_up_status:
            return []
        if order.is_concatenated_order:
            return PickupSerializer(order.orders.all().exclude(pickup_address_id__isnull=True), many=True).data
        else:
            if order.pickup_address_id:
                return PickupSerializer([order], many=True).data
        return []

    def get_driver_member_id(self, order):
        return order.driver.member_id if order.driver else None

    def get_service_time(self, order):
        skill_service_times = [skill.service_time for skill in order.skill_sets.all() if skill.service_time is not None]
        if len(skill_service_times):
            return max(skill_service_times)

    def get_capacity(self, order):
        if order.is_concatenated_order:
            orders = order.orders.all().exclude(Q(capacity__isnull=True) | Q(capacity=0),
                                                pickup_address_id__isnull=True)
            return sum(order.capacity or 1 for order in orders) or None
        return order.capacity


class MoveOrdersJobSerializer(JobSerializer):
    def get_driver_member_id(self, order):
        return None


class HubSerializer(serializers.ModelSerializer):
    location = serializers.CharField(source='location.location')

    class Meta:
        model = Hub
        fields = ('id', 'location')


class LocationSerializer(serializers.Serializer):
    location = serializers.CharField()
    address = serializers.CharField(required=False)
    id = serializers.IntegerField(required=False)


class BreakSerializer(serializers.Serializer):
    start_time = serializers.TimeField(required=True, source='start')
    end_time = serializers.TimeField(required=True, source='end')
    diff_allowed = serializers.SerializerMethodField()

    def get_diff_allowed(self, data):
        start = data['start']
        start = timedelta(hours=start.hour, minutes=start.minute, seconds=start.second, microseconds=start.microsecond)

        end = data['end']
        end = timedelta(hours=end.hour, minutes=end.minute, seconds=end.second, microseconds=end.microsecond)

        diff_allowed = abs(end - start) / 2  # diff_allowed is half the break time
        return int(diff_allowed.total_seconds() / 60)  # in minutes


class DriverSerializer(serializers.ModelSerializer):
    start_time = serializers.SerializerMethodField()
    end_time = serializers.SerializerMethodField()
    start_hub = serializers.SerializerMethodField()
    end_hub = serializers.SerializerMethodField()
    start_location = serializers.SerializerMethodField()
    end_location = serializers.SerializerMethodField()
    capacity = serializers.SerializerMethodField()
    breaks = serializers.SerializerMethodField()

    class Meta:
        model = Member
        fields = (
            'id', 'member_id', 'start_time', 'end_time',
            'start_hub', 'end_hub', 'start_location', 'end_location',
            'skill_set', 'capacity', 'breaks',
        )
        extra_kwargs = {
            'skill_set': {'source': 'skill_sets'},
        }

    def get_start_time(self, driver):
        return str(driver.allowed_period[0].time())

    def get_end_time(self, driver):
        return str(driver.allowed_period[1].time())

    def get_start_hub(self, driver):
        return HubSerializer(driver.start_point).data \
            if (driver.start_point and isinstance(driver.start_point, Hub)) else None

    def get_end_hub(self, driver):
        return HubSerializer(driver.end_point).data \
            if (driver.end_point and isinstance(driver.end_point, Hub)) else None

    def get_start_location(self, driver):
        if driver.start_point and not isinstance(driver.start_point, Hub):
            return LocationSerializer(driver.start_point).data

    def get_end_location(self, driver):
        if driver.end_point and not isinstance(driver.end_point, Hub):
            return LocationSerializer(driver.end_point).data

    def get_capacity(self, driver):
        day = self.context['optimisation'].day
        return driver.car.get_capacity(day) if driver.car_id else None

    def get_breaks(self, driver):
        day = self.context['optimisation'].day

        if driver.schedule is None:
            return None
        one_time = driver.schedule.schedule['one_time'].get(day, None)
        if one_time is None:
            return None
        breaks = one_time.get('breaks', [])
        if hasattr(driver, 'allowed_period'):
            breaks = [
                br for br in breaks
                if not (br['end'] <= driver.allowed_period[0].time() or br['start'] >= driver.allowed_period[1].time())
            ]
        return BreakSerializer(breaks, many=True).data


class OptimisationOptionsSerializer(serializers.Serializer):
    use_vehicle_capacity = serializers.BooleanField(required=False, allow_null=True)
    jobs = JobSerializer(many=True, source='jobs_ids')
    drivers = DriverSerializer(many=True, source='drivers_ids')
    service_time = serializers.SerializerMethodField(required=False, allow_null=True)
    pickup_service_time = serializers.SerializerMethodField(required=False, allow_null=True)

    class Meta:
        fields = (
            'use_vehicle_capacity', 'jobs', 'drivers', 'service_time', 'pickup_service_time',
        )

    def get_service_time(self, params):
        return params.get('service_time', self.context['optimisation'].merchant.job_service_time)

    def get_pickup_service_time(self, params):
        return params.get('pickup_service_time', self.context['optimisation'].merchant.pickup_service_time)


class MoveOrdersOptimisationOptionsSerializer(OptimisationOptionsSerializer):
    jobs = MoveOrdersJobSerializer(many=True, source='jobs_ids')


point_kind_map = {
    RoutePointKind.PICKUP: JobKind.PICKUP,
    RoutePointKind.DELIVERY: JobKind.DELIVERY,
    RoutePointKind.HUB: JobKind.HUB,
    RoutePointKind.LOCATION: JobKind.LOCATION,
}


class TransformForReOptimiseMixin(serializers.Serializer):
    def get_optimisation(self):
        raise NotImplementedError()

    def to_representation(self, instance):
        result = super().to_representation(instance)
        optimisation = self.get_optimisation()
        order_ct = ContentType.objects.get_for_model(Order)

        used_orders = set()
        required_start_sequence = []
        for driver in result['drivers']:
            passed_points = []
            existing_points = RoutePoint.objects\
                .filter(route__optimisation=optimisation, route__driver_id=driver['id'])\
                .prefetch_related('point_object').order_by('number')
            for point in existing_points:
                if point.point_content_type != order_ct:
                    continue
                used_orders.add(point.point_object_id)
                if self.is_point_passed(point):
                    passed_points.append(point)
            if passed_points:
                required_start_sequence.append(self.get_required_start_sequence(optimisation, driver, passed_points))
        result['required_start_sequence'] = required_start_sequence
        for job in result['jobs']:
            if job['id'] in used_orders:
                job['allow_skip'] = False
        return result

    @staticmethod
    def get_required_start_sequence(optimisation, driver_data, passed_points):
        last_passed_point = passed_points[-1]
        allowed_point_kinds = (
            RoutePointKind.PICKUP, RoutePointKind.DELIVERY, RoutePointKind.HUB, RoutePointKind.LOCATION
        )
        all_passed_points = RoutePoint.objects \
            .filter(route__optimisation=optimisation, route__driver_id=driver_data['id']) \
            .order_by('number') \
            .filter(number__lte=last_passed_point.number, point_kind__in=allowed_point_kinds)
        sequence = [
            {'point_kind': point_kind_map[p.point_kind], 'point_id': p.point_object_id}
            for p in all_passed_points
        ]
        return {
            'driver_member_id': driver_data['member_id'],
            'sequence': sequence,
        }

    @staticmethod
    def is_point_passed(point):
        if point.point_kind == RoutePointKind.PICKUP \
                and point.point_object.status in [OrderStatus.PICKED_UP, OrderStatus.IN_PROGRESS,
                                                  OrderStatus.DELIVERED, OrderStatus.WAY_BACK,
                                                  OrderStatus.FAILED]:
            return True
        if point.point_kind == RoutePointKind.DELIVERY:
            return point.point_object.status in [OrderStatus.DELIVERED, OrderStatus.WAY_BACK, OrderStatus.FAILED]


class MoveOrdersExistingOptimisationOptionsSerializer(TransformForReOptimiseMixin,
                                                      MoveOrdersOptimisationOptionsSerializer):
    def get_optimisation(self):
        return self.context[CONTEXT_HELP_ITEM]['source_optimisation']


class RefreshOptimisationOptionsSerializer(TransformForReOptimiseMixin, OptimisationOptionsSerializer):
    def get_optimisation(self):
        return self.context[CONTEXT_HELP_ITEM]['source_optimisation']
