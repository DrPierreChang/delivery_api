from datetime import time

from django.test import TestCase

from route_optimisation.const import RoutePointKind
from route_optimisation.engine.base_classes.parameters import EngineParameters
from route_optimisation.engine.base_classes.result import AssignmentResult, Point
from route_optimisation.tests.test_utils.expectations import BaseExpectation, ExpectationCheck
from tasks.models import Order


class FailStateCheck(ExpectationCheck):
    def __init__(self, fail=False):
        self.fail = fail

    def check(self, test_case: TestCase, result: AssignmentResult = None,
              input_params: EngineParameters = None, **kwargs):
        test_case.assertEqual(result.good, not self.fail, '[{}]'.format(self.__class__.__name__))


class ExpectedDistanceCheck(ExpectationCheck):
    def __init__(self, max_distance=False):
        self.max_distance = max_distance

    def check(self, test_case: TestCase, result: AssignmentResult = None,
              input_params: EngineParameters = None, **kwargs):
        test_case.assertLess(result.driving_distance, self.max_distance, '[{}]'.format(self.__class__.__name__))
        test_case.assertGreater(result.driving_distance, 0, '[{}]'.format(self.__class__.__name__))


class SkippedOrdersCheck(ExpectationCheck):
    def __init__(self, skipped_orders=False):
        self.skipped_orders = skipped_orders

    def check(self, test_case: TestCase, result: AssignmentResult = None,
              input_params: EngineParameters = None, **kwargs):
        test_case.assertEqual(len(result.skipped_orders), self.skipped_orders, '[{}]'.format(self.__class__.__name__))


class SkippedOrdersMaxCheck(ExpectationCheck):
    def __init__(self, skipped_orders_max=False):
        self.skipped_orders_max = skipped_orders_max

    def check(self, test_case: TestCase, result: AssignmentResult = None,
              input_params: EngineParameters = None, **kwargs):
        test_case.assertLess(len(result.skipped_orders), self.skipped_orders_max,
                             '[{}]'.format(self.__class__.__name__))


class SkippedDriversCheck(ExpectationCheck):
    def __init__(self, skipped_drivers=False):
        self.skipped_drivers = skipped_drivers

    def check(self, test_case: TestCase, result: AssignmentResult = None,
              input_params: EngineParameters = None, **kwargs):
        test_case.assertEqual(len(result.skipped_drivers), self.skipped_drivers)


def collect_driver_to_order_mapping(result: AssignmentResult):
    mapping = {}  # {order.id: driver} (driver that assigned after RO)
    for driver_member_id, tour in result.drivers_tours.items():
        for point in tour.points:
            if point.model_class is Order:
                order_id = point.point_prototype['id']
                mapping[order_id] = driver_member_id
    return mapping


class RightSkillsCheck(ExpectationCheck):
    def check(self, test_case: TestCase, result: AssignmentResult = None,
              input_params: EngineParameters = None, **kwargs):
        if not result.good:
            return
        drivers_skills = {driver.member_id: driver.skill_set for driver in input_params.drivers}
        drivers_mapping = collect_driver_to_order_mapping(result)
        for job in input_params.jobs:
            driver_from_ro = drivers_mapping.get(job.id)
            if driver_from_ro is None:
                continue
            if not self._skill_set_valid(job.skill_set, drivers_skills[driver_from_ro] or set()):
                raise test_case.failureException('[{}] RO assigned wrong driver {} by skill set for order with id {}'
                                                 .format(self.__class__.__name__, driver_from_ro, job.id))

    def _skill_set_valid(self, job_skill_set, driver_skill_set):
        return job_skill_set is None or not set(job_skill_set).difference(driver_skill_set)


class PreAssignedDriverCheck(ExpectationCheck):
    def check(self, test_case: TestCase, result: AssignmentResult = None,
              input_params: EngineParameters = None, **kwargs):
        if not result.good:
            return
        drivers_mapping = collect_driver_to_order_mapping(result)
        for job in input_params.jobs:
            driver_from_ro = drivers_mapping.get(job.id)
            if driver_from_ro is None:
                continue
            if not self._driver_is_valid(job.driver_member_id, driver_from_ro):
                raise test_case.failureException('[{}] RO assigned wrong driver {} to order with id {}'
                                                 .format(self.__class__.__name__, driver_from_ro, job.id))

    def _driver_is_valid(self, pre_assigned_driver_id, assigned_driver_id_by_ro):
        return pre_assigned_driver_id is None or pre_assigned_driver_id == assigned_driver_id_by_ro


class ServiceTimeCheck(ExpectationCheck):
    def __init__(self, order_id, service_time_minutes, is_pickup=False, pickup_id=None):
        self.pickup_id = pickup_id
        self.is_pickup = is_pickup
        self.order_id = order_id
        self.service_time_minutes = service_time_minutes

    def check(self, test_case: TestCase, result: AssignmentResult = None,
              input_params: EngineParameters = None, **kwargs):
        for route in result.drivers_tours.values():
            for point in route.points:
                if point.point_kind not in (RoutePointKind.DELIVERY, RoutePointKind.PICKUP):
                    continue
                order_id_field = \
                    {RoutePointKind.DELIVERY: 'id', RoutePointKind.PICKUP: 'parent_order_id'}[point.point_kind]
                if point.point_prototype[order_id_field] != self.order_id:
                    continue
                if self._check_delivery_point(point, test_case):
                    return
                if self._check_pickup_point(point, test_case):
                    return
        point_kind = RoutePointKind.PICKUP if self.is_pickup else RoutePointKind.DELIVERY
        raise test_case.failureException('[{}] {} order with id {} is not found'.format(
            self.__class__.__name__, point_kind.capitalize(), self.order_id)
        )

    def _check_delivery_point(self, point, test_case):
        if not self.is_pickup and point.point_kind == RoutePointKind.DELIVERY:
            test_case.assertEqual(
                point.service_time, self.service_time_minutes * 60,
                '[{}] {} service time of order with id {} is wrong'.format(
                    self.__class__.__name__, point.point_kind.capitalize(), self.order_id)
            )
            return True

    def _check_pickup_point(self, point, test_case):
        if self.is_pickup and point.point_kind == RoutePointKind.PICKUP:
            if self.pickup_id is not None and self.pickup_id != point.point_prototype.get('id'):
                return
            test_case.assertEqual(
                point.service_time, self.service_time_minutes * 60,
                '[{}] {} service time of order with id {} is wrong. Pickup id: {}'.format(
                    self.__class__.__name__, point.point_kind.capitalize(), self.order_id, self.pickup_id)
            )
            return True


class PickupBeforeDeliveryCheck(ExpectationCheck):
    def __init__(self, order_id, pickups_count=1):
        self.pickups_count = pickups_count
        self.order_id = order_id

    def check(self, test_case: TestCase, result: AssignmentResult = None,
              input_params: EngineParameters = None, **kwargs):
        for route in result.drivers_tours.values():
            counter = 0
            for point in route.points:
                if point.point_kind == RoutePointKind.PICKUP \
                        and point.point_prototype['parent_order_id'] == self.order_id:
                    counter += 1
                    continue
                if point.point_kind == RoutePointKind.DELIVERY and point.point_prototype['id'] == self.order_id:
                    test_case.assertEqual(
                        counter, self.pickups_count,
                        '[{}] Wrong count of pickups before delivery {}'.format(self.__class__.__name__, self.order_id)
                    )
                    return
        raise test_case.failureException('[{}] Order with id {} is not found'.format(
            self.__class__.__name__, self.order_id)
        )


class OrderExistsInRoute(ExpectationCheck):
    def __init__(self, order_id):
        self.order_id = order_id

    def check(self, test_case: TestCase, result: AssignmentResult = None,
              input_params: EngineParameters = None, **kwargs):
        for route in result.drivers_tours.values():
            for point in route.points:
                if point.point_kind == RoutePointKind.DELIVERY and point.point_prototype['id'] == self.order_id:
                    return
        raise test_case.failureException('[{}] Order with id {} does not exist in any route'.format(
            self.__class__.__name__, self.order_id
        ))


class DriverBreaksExactTime(ExpectationCheck):
    def __init__(self, driver_id, breaks):
        self.breaks = breaks
        self.driver_id = driver_id

    def check(self, test_case: TestCase, result: AssignmentResult = None,
              input_params: EngineParameters = None, **kwargs):
        for driver_break in self.breaks:
            found = False
            for driver, route in result.drivers_tours.items():
                if driver != self.driver_id:
                    continue
                for point in route.points:
                    if point.point_kind == RoutePointKind.BREAK and self._point_break_equals(point, driver_break):
                        found = True
            if not found:
                raise test_case.failureException(
                    f'[{self.__class__.__name__}] Driver with id {self.driver_id} does not have break {driver_break}'
                )

    @staticmethod
    def _point_break_equals(point: Point, driver_break):
        start_tuple, end_tuple = point.start_time.timetuple(), point.end_time.timetuple()
        driver_start, driver_end = time(*driver_break[0]), time(*driver_break[1])
        return start_tuple.tm_hour == driver_start.hour and start_tuple.tm_min == driver_start.minute \
            and start_tuple.tm_sec == driver_start.second and end_tuple.tm_hour == driver_end.hour \
            and end_tuple.tm_min == driver_end.minute and end_tuple.tm_sec == driver_end.second


class OptimisationExpectation(BaseExpectation):
    def __init__(self, fail=False, max_distance=None, skipped_orders=None,
                 skipped_orders_max=None, skipped_drivers=None):
        super().__init__()
        self.checklist.extend((FailStateCheck(fail), RightSkillsCheck(), PreAssignedDriverCheck()))
        if max_distance is not None:
            self.checklist.append(ExpectedDistanceCheck(max_distance))
        if skipped_orders is not None:
            self.checklist.append(SkippedOrdersCheck(skipped_orders))
        if skipped_orders_max is not None:
            self.checklist.append(SkippedOrdersMaxCheck(skipped_orders_max))
        if skipped_drivers is not None:
            self.checklist.append(SkippedDriversCheck(skipped_drivers))

    def check(self, test_case: TestCase, result: AssignmentResult = None,
              input_params: EngineParameters = None, **kwargs):
        super(OptimisationExpectation, self).check(test_case, result=result, input_params=input_params, **kwargs)
