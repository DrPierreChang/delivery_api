import operator
from datetime import time

from django.test import TestCase

from rest_framework import status

from dateutil.parser import parse

from route_optimisation.const import RoutePointKind
from route_optimisation.logging import EventType
from route_optimisation.models import DriverRouteLocation, RouteOptimisation, RoutePoint
from route_optimisation.tests.test_utils.expectations import BaseExpectation, ExpectationCheck
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order


def get_all_points_ids(point):
    all_points_ids = []
    if 'objects_ids' in point:
        for ids in point['objects_ids']:
            all_points_ids.append(ids['point_object_id'])
            all_points_ids.extend(ids.get('pickup_ids', []))
    else:
        all_points_ids.append(point['point_object_id'])
        all_points_ids.extend(
            (p.get('point_object') or p)['id']
            for p in point['concatenated_objects']
        )
    return all_points_ids


class FailStateCheck(ExpectationCheck):
    def __init__(self, fail=False):
        self.fail = fail

    def check(self, test_case: TestCase, response=None, route_optimisation: RouteOptimisation = None):
        test_case.assertEqual(response.data['state'] == RouteOptimisation.STATE.FAILED, self.fail,
                              '[{}]'.format(self.__class__.__name__))


class ExpectedDistanceCheck(ExpectationCheck):
    def __init__(self, max_distance=False):
        self.max_distance = max_distance

    def check(self, test_case: TestCase, response=None, route_optimisation: RouteOptimisation = None):
        distance = 0
        for route in response.data.get('routes', []):
            distance += route['driving_distance']
        test_case.assertLess(distance, self.max_distance, '[{}]'.format(self.__class__.__name__))
        test_case.assertGreater(distance, 0, '[{}]'.format(self.__class__.__name__))


class SkippedOrdersCheck(ExpectationCheck):
    def __init__(self, skipped_orders=False):
        self.skipped_orders = skipped_orders

    def check(self, test_case: TestCase, response=None, route_optimisation: RouteOptimisation = None):
        count = 0
        for log_item in route_optimisation.optimisation_log.log.get('full', []):
            if log_item.get('event') == EventType.SKIPPED_OBJECTS \
                    and log_item['params'].get('code') in ('order', 'not_accessible_orders'):
                count += len(log_item['params'].get('objects', []))
        if count != self.skipped_orders:
            raise test_case.failureException('[{}] Skipped orders count is {}, not {}'.format(
                self.__class__.__name__, count, self.skipped_orders
            ))


class ServiceTimeCheck(ExpectationCheck):
    def __init__(self, order, service_time_minutes, is_pickup=False):
        self.is_pickup = is_pickup
        self.order_id = order.id
        self.service_time_minutes = service_time_minutes

    def check(self, test_case: TestCase, response=None, route_optimisation: RouteOptimisation = None):
        point_kind = RoutePointKind.PICKUP if self.is_pickup else RoutePointKind.DELIVERY
        for route in response.data['routes']:
            for point in route['points']:
                if point['point_kind'] != point_kind:
                    continue
                all_points_ids = get_all_points_ids(point)
                if self.order_id in all_points_ids:
                    test_case.assertEqual(
                        point['service_time'], self.service_time_minutes * 60,
                        '[{}] {} service time of order with id {} is wrong'.format(
                            self.__class__.__name__, point_kind.capitalize(), self.order_id
                        )
                    )
                    return
        raise test_case.failureException('[{}] {} order with id {} is not found'.format(
            self.__class__.__name__, point_kind.capitalize(), self.order_id)
        )


class RoutePointsCountCheck(ExpectationCheck):
    def __init__(self, driver_id, count, hubs=None, locations=None, pickups=None, deliveries=None, breaks=None):
        self.driver_id = driver_id
        self.count = count
        self.breaks = breaks
        self.hubs = hubs
        self.locations = locations
        self.pickups = pickups
        self.deliveries = deliveries

    def check(self, test_case: TestCase, response=None, route_optimisation: RouteOptimisation = None):
        for route in response.data['routes']:
            if 'driver' in route and route['driver']['id'] != self.driver_id:
                continue
            if 'driver_id' in route and route['driver_id'] != self.driver_id:
                continue
            test_case.assertEqual(len(route['points']), self.count, '[{}]'.format(self.__class__.__name__))
            counts = {
                RoutePointKind.HUB: 0, RoutePointKind.LOCATION: 0, RoutePointKind.PICKUP: 0,
                RoutePointKind.DELIVERY: 0, RoutePointKind.BREAK: 0,
            }
            for point in route['points']:
                counts[point['point_kind']] += 1
            if self.hubs is not None:
                test_case.assertEqual(
                    self.hubs, counts[RoutePointKind.HUB], '[{}]'.format(self.__class__.__name__)
                )
            if self.locations is not None:
                test_case.assertEqual(
                    self.locations, counts[RoutePointKind.LOCATION], '[{}]'.format(self.__class__.__name__)
                )
            if self.pickups is not None:
                test_case.assertEqual(
                    self.pickups, counts[RoutePointKind.PICKUP], '[{}]'.format(self.__class__.__name__)
                )
            if self.deliveries is not None:
                test_case.assertEqual(
                    self.deliveries, counts[RoutePointKind.DELIVERY], '[{}]'.format(self.__class__.__name__)
                )
            if self.breaks is not None:
                test_case.assertEqual(
                    self.breaks, counts[RoutePointKind.BREAK], '[{}]'.format(self.__class__.__name__)
                )
            return
        raise test_case.failureException('[{}] Route for driver with id {} is not found'.format(
            self.__class__.__name__, self.driver_id
        ))


class OrderIsAssignedCheck(ExpectationCheck):
    def __init__(self, order_id):
        self.order_id = order_id

    def check(self, test_case: TestCase, response=None, route_optimisation: RouteOptimisation = None):
        for route in response.data['routes']:
            for point in route['points']:
                if point['point_kind'] not in (RoutePointKind.DELIVERY, RoutePointKind.PICKUP):
                    continue
                all_points_ids = get_all_points_ids(point)
                if self.order_id not in all_points_ids:
                    continue
                order = Order.aggregated_objects.get(id=self.order_id)
                test_case.assertEqual(
                    order.status, OrderStatus.ASSIGNED,
                    '[{}] Order with id {} is not in assigned status'.format(self.__class__.__name__, self.order_id)
                )
                return
        raise test_case.failureException('[{}] Order with id {} is not found'.format(
            self.__class__.__name__, self.order_id)
        )


class NumberFieldConsecutiveCheck(ExpectationCheck):
    def check(self, test_case: TestCase, response=None, route_optimisation: RouteOptimisation = None):
        for route in response.data['routes']:
            previous = 0
            for point in route['points']:
                if point['number'] - previous != 1:
                    raise test_case.failureException(
                        '[{}] Number field in api is not increasing consecutively by 1'.format(self.__class__.__name__)
                    )
                previous = point['number']
        for route in route_optimisation.routes.all():
            previous = 0
            for point in route.points.all().order_by('number'):
                if point.number - previous != 1:
                    raise test_case.failureException(
                        '[{}] Number field in db is not increasing consecutively by 1'.format(self.__class__.__name__)
                    )
                previous = point.number


class DriverBreaksExactTime(ExpectationCheck):
    def __init__(self, driver_id, breaks):
        self.breaks = breaks
        self.driver_id = driver_id

    def check(self, test_case: TestCase, response=None, route_optimisation: RouteOptimisation = None, **kwargs):
        for driver_break in self.breaks:
            found = False
            for route in response.data['routes']:
                if 'driver' in route and route['driver']['id'] != self.driver_id:
                    continue
                if 'driver_id' in route and route['driver_id'] != self.driver_id:
                    continue
                for point in route['points']:
                    if point['point_kind'] == RoutePointKind.BREAK and self._point_break_equals(point, driver_break):
                        found = True
            if not found:
                raise test_case.failureException(
                    f'[{self.__class__.__name__}] Driver with id {self.driver_id} does not have break {driver_break}'
                )

    def _point_break_equals(self, point: dict, driver_break):
        start_tuple, end_tuple = parse(point['start_time']).timetuple(), parse(point['end_time']).timetuple()
        driver_start, driver_end = time(*driver_break[0]), time(*driver_break[1])
        return start_tuple.tm_hour == driver_start.hour and start_tuple.tm_min == driver_start.minute \
            and start_tuple.tm_sec == driver_start.second and end_tuple.tm_hour == driver_end.hour \
            and end_tuple.tm_min == driver_end.minute and end_tuple.tm_sec == driver_end.second


class DeliveryRODetailsFillCheck(ExpectationCheck):
    def check(self, test_case: TestCase, response=None, route_optimisation: RouteOptimisation = None):
        points = RoutePoint.objects.filter(
            route__optimisation_id=route_optimisation.id,
            point_kind__in=(RoutePointKind.PICKUP, RoutePointKind.DELIVERY)
        ).prefetch_related('point_object')
        for point in points:
            order_obj = point.point_object
            ro_details = order_obj.route_optimisation_details
            test_case.assertIsNotNone(ro_details, '[{}]'.format(self.__class__.__name__))
            test_case.assertIsNotNone(ro_details['delivery'], '[{}]'.format(self.__class__.__name__))
            if order_obj.is_concatenated_order:
                for sub_order in order_obj.orders.all():
                    ro_details = sub_order.route_optimisation_details
                    test_case.assertIsNotNone(ro_details, '[{}]'.format(self.__class__.__name__))
                    test_case.assertIsNotNone(ro_details['delivery'], '[{}]'.format(self.__class__.__name__))


class LogCheck(ExpectationCheck):
    def __init__(self, text, partly=False):
        self.text = text
        self.partly = partly

    def check(self, test_case: TestCase, response=None, route_optimisation: RouteOptimisation = None):
        log_messages = response.data['log']['messages']
        operation = operator.contains if self.partly else operator.eq
        for message in log_messages:
            if operation(message['text'], self.text):
                return
        raise test_case.failureException('[{}] Message "{}" is not in optimisation log'.format(
            self.__class__.__name__, self.text
        ))


class PointIsDriverLocationCheck(ExpectationCheck):
    def __init__(self, driver_id, location):
        self.driver_id = driver_id
        self.location = location

    def check(self, test_case: TestCase, response=None, route_optimisation: RouteOptimisation = None):
        point = self._get_point(test_case, response)
        test_case.assertEqual(
            point['point_kind'], 'location', '[{}]'.format(self.__class__.__name__)
        )
        location_resp = test_case.client.get(f'/api/web/ro/locations/{point["objects_ids"][0]["point_object_id"]}')
        test_case.assertEqual(
            location_resp.json()['location'],
            {key: round(value, 6) for key, value in self.location.items()},
            '[{}]'.format(self.__class__.__name__)
        )

    def _get_point(self, test_case: TestCase, response=None):
        point = None
        for route in response.data['routes']:
            if 'driver' in route and route['driver']['id'] != self.driver_id:
                continue
            if 'driver_id' in route and route['driver_id'] != self.driver_id:
                continue
            point = self._get_point_from_route(route)
        if not point:
            raise test_case.failureException(
                '[{}] Driver route not found in completed optimisation'.format(self.__class__.__name__)
            )
        return point

    def _get_point_from_route(self, route):
        raise NotImplementedError()


class StartPointIsDriverLocationCheck(PointIsDriverLocationCheck):
    def _get_point_from_route(self, route):
        return route['points'][0]


class EndPointIsDriverLocationCheck(PointIsDriverLocationCheck):
    def _get_point_from_route(self, route):
        return route['points'][-1]


class EndPointIsDefaultLocationCheck(PointIsDriverLocationCheck):
    def _get_point_from_route(self, route):
        return route['points'][-1]

    def check(self, test_case: TestCase, response=None, route_optimisation: RouteOptimisation = None):
        point = self._get_point(test_case, response)
        test_case.assertEqual(
            point['point_kind'], 'location', '[{}]'.format(self.__class__.__name__)
        )
        location_resp = test_case.client.get(f'/api/web/ro/locations/{point["objects_ids"][0]["point_object_id"]}')
        test_case.assertEqual(
            location_resp.json()['location'],
            {key: round(value, 6) for key, value in self.location['location'].items()},
            '[{}]'.format(self.__class__.__name__)
        )
        test_case.assertEqual(location_resp.json()['address'], self.location['address'])


class EndPointIsOrderCheck(ExpectationCheck):
    def __init__(self, driver_id):
        self.driver_id = driver_id

    def check(self, test_case: TestCase, response=None, route_optimisation: RouteOptimisation = None):
        point = self._get_point(test_case, response)
        test_case.assertEqual(
            point['point_kind'], 'delivery', '[{}]'.format(self.__class__.__name__)
        )

    def _get_point(self, test_case: TestCase, response=None):
        point = None
        for route in response.data['routes']:
            if 'driver' in route and route['driver']['id'] != self.driver_id:
                continue
            if 'driver_id' in route and route['driver_id'] != self.driver_id:
                continue
            point = route['points'][-1]
        if not point:
            raise test_case.failureException(
                '[{}] Driver route not found in completed optimisation'.format(self.__class__.__name__)
            )
        return point


class OptimisationExpectation(BaseExpectation):
    def __init__(self, fail=False, response_status=status.HTTP_201_CREATED, max_distance=None, skipped_orders=None):
        super().__init__()
        self.response_status = response_status
        self.checklist.append(FailStateCheck(fail))
        if max_distance is not None:
            self.checklist.append(ExpectedDistanceCheck(max_distance))
        if skipped_orders is not None:
            self.checklist.append(SkippedOrdersCheck(skipped_orders))

    def check(self, test_case: TestCase, response=None, route_optimisation: RouteOptimisation = None):
        super(OptimisationExpectation, self).check(test_case, response=response, route_optimisation=route_optimisation)
