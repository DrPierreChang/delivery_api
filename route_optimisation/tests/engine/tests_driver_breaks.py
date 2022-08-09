import contextlib
from typing import List

from django.test import TestCase, override_settings

import pytz

from route_optimisation.tests.engine.optimisation_expectation import (
    DriverBreaksExactTime,
    OptimisationExpectation,
    PickupBeforeDeliveryCheck,
)

from ...const import MerchantOptimisationFocus, RoutePointKind
from ...engine import EngineParameters, set_dima_cache
from ...engine.events import set_event_handler
from ...engine.ortools import constants
from ...engine.ortools.assignment import BalancedAssignment
from ...engine.ortools.assignment.result_parser import Break, DriverBreaksHelper
from ...engine.ortools.assignment.services.routes import Route
from ...engine.ortools.assignment.services.types import RoutePointIndex
from ...engine.ortools.context import AssignmentContextManager, GroupAssignmentContext, current_context
from ..test_utils.setting import DriverBreakSetting
from .engine_settings import EngineSettings
from .tests_engine import BaseTestEngineMixin, TestROEvents


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=2, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=2)
class TestDriverBreaksCase(BaseTestEngineMixin, TestCase):

    def test_breaks_1(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'), focus=MerchantOptimisationFocus.TIME_BALANCE)
        settings.hub('53.907175,27.449568', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=10,
                        breaks=[DriverBreakSetting((8, 28), (8, 58), 15)],)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=7,
                        breaks=[DriverBreakSetting((8, 20), (8, 50), None)],)
        settings.order(
            1, '53.906771,27.532308', driver=1,
            pickups=({'pickup_id': 1, 'pickup_address': '53.925965,27.501122'},
                     {'pickup_id': 2, 'pickup_address': '53.897700, 27.521235'},
                     {'pickup_id': 3, 'pickup_address': '53.919803,27.478715'},),
        )
        settings.order(2, '53.898275,27.503641', pickup_address='53.897700, 27.521235')
        settings.order(3, '53.881996,27.512813', pickup_address='53.919803,27.478715')
        settings.order(5, '53.889130, 27.608861')
        settings.order(7, '53.925965,27.501122')
        settings.service_time(10)
        settings.set_pickup_service_time(5)
        expectation = OptimisationExpectation(max_distance=62000, skipped_orders=0)
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=1, pickups_count=3))
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=2, pickups_count=1))
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=5, pickups_count=0))
        expectation.add_check(DriverBreaksExactTime(driver_id=1, breaks=[((8, 28), (8, 58))]))
        expectation.add_check(DriverBreaksExactTime(driver_id=2, breaks=[((8, 20), (8, 50))]))
        result = self.optimise(settings=settings, expectation=expectation)

    def test_breaks_2(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'), focus=MerchantOptimisationFocus.TIME_BALANCE)
        settings.hub('53.907175,27.449568', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=10,
                        breaks=[DriverBreakSetting((8, 30), (9, 0), 15)],)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=7,
                        breaks=[DriverBreakSetting((8, 30), (9, 0), None)],)
        settings.order(
            1, '53.906771,27.532308', driver=1,
            pickups=({'pickup_id': 1, 'pickup_address': '53.925965,27.501122'},
                     {'pickup_id': 2, 'pickup_address': '53.897700, 27.521235'},
                     {'pickup_id': 3, 'pickup_address': '53.919803,27.478715'},),
        )
        settings.order(2, '53.898275,27.503641', pickup_address='53.897700, 27.521235')
        settings.order(3, '53.881996,27.512813', pickup_address='53.919803,27.478715')
        settings.order(5, '53.889130, 27.608861')
        settings.order(7, '53.925965,27.501122')
        settings.service_time(10)
        settings.set_pickup_service_time(5)
        expectation = OptimisationExpectation(max_distance=62000, skipped_orders=0)
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=1, pickups_count=3))
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=2, pickups_count=1))
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=5, pickups_count=0))
        expectation.add_check(DriverBreaksExactTime(driver_id=1, breaks=[((8, 28, 7), (8, 58, 7))]))
        expectation.add_check(DriverBreaksExactTime(driver_id=2, breaks=[((8, 28, 40), (9, 0))]))
        result = self.optimise(settings=settings, expectation=expectation)

    def test_breaks_3(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'), focus=MerchantOptimisationFocus.OLD)
        settings.hub('53.907175,27.449568', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=10,
                        breaks=[DriverBreakSetting((8, 10), (8, 15), None), DriverBreakSetting((8, 20), (8, 25), None),
                                DriverBreakSetting((8, 30), (9, 0), 15)],)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=7,
                        breaks=[DriverBreakSetting((8, 35), (9, 0), None)],)
        settings.order(
            1, '53.906771,27.532308', driver=1,
            pickups=({'pickup_id': 1, 'pickup_address': '53.925965,27.501122'},
                     {'pickup_id': 2, 'pickup_address': '53.897700, 27.521235'},
                     {'pickup_id': 3, 'pickup_address': '53.919803,27.478715'},),
        )
        settings.order(2, '53.898275,27.503641', pickup_address='53.897700, 27.521235')
        settings.order(3, '53.881996,27.512813', pickup_address='53.919803,27.478715')
        settings.order(5, '53.889130, 27.608861')
        settings.order(7, '53.925965,27.501122')
        settings.service_time(10)
        settings.set_pickup_service_time(5)
        expectation = OptimisationExpectation(max_distance=62000, skipped_orders=0)
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=1, pickups_count=3))
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=2, pickups_count=1))
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=5, pickups_count=0))
        expectation.add_check(DriverBreaksExactTime(
            driver_id=1, breaks=[((8, 7, 18), (8, 15)), ((8, 20), (8, 25)), ((8, 30), (9, 0))]))
        expectation.add_check(DriverBreaksExactTime(driver_id=2, breaks=[((8, 28, 40), (9, 0))]))
        result = self.optimise(settings=settings, expectation=expectation)

    @override_settings(ORTOOLS_SEARCH_TIME_LIMIT=7, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=7)
    def test_breaks_4(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'), focus=MerchantOptimisationFocus.OLD)
        settings.hub('53.907175,27.449568', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=10,
                        breaks=[DriverBreakSetting((8, 15), (8, 25), None),
                                DriverBreakSetting((8, 30), (8, 35), 20)],)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=7,
                        breaks=[DriverBreakSetting((8, 35), (8, 45), 5)],)
        settings.order(
            1, '53.906771,27.532308', driver=1,
            pickups=({'pickup_id': 1, 'pickup_address': '53.925965,27.501122'},
                     {'pickup_id': 2, 'pickup_address': '53.897700, 27.521235'},
                     {'pickup_id': 3, 'pickup_address': '53.919803,27.478715'},),
        )
        settings.order(2, '53.898275,27.503641', pickup_address='53.897700, 27.521235')
        settings.order(3, '53.881996,27.512813', pickup_address='53.919803,27.478715')
        settings.order(5, '53.889130, 27.608861')
        settings.order(7, '53.925965,27.501122')
        settings.service_time(10)
        settings.set_pickup_service_time(5)
        expectation = OptimisationExpectation(max_distance=72000, skipped_orders=0)
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=1, pickups_count=3))
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=2, pickups_count=1))
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=5, pickups_count=0))
        expectation.add_check(DriverBreaksExactTime(driver_id=1, breaks=[((8, 12, 18), (8, 25)), ((8, 30), (8, 35))]))
        expectation.add_check(DriverBreaksExactTime(driver_id=2, breaks=[((8, 35, 0), (8, 45, 0))]))
        result = self.optimise(settings=settings, expectation=expectation)
        # print('result', result)
        # for tour in result.drivers_tours.values():
        #     print()
        #     print(tour.driving_time, tour.full_time)
        #     for point in tour.points:
        #         print(point.point_kind, point.start_time, point.end_time, '|', point.driving_time, point.service_time)


class TestBreaksHelperCase(TestCase):
    def test_breaks_helper(self):
        breaks = [Break(0, 100), Break(90, 110), Break(130, 150), Break(120, 160)]
        breaks = DriverBreaksHelper.merge_intersected(breaks)
        self.assertBreaks(breaks, ((0, 110), (120, 160)))

        breaks = [Break(90, 110), Break(120, 160), Break(0, 100), Break(130, 150)]
        breaks = DriverBreaksHelper.merge_intersected(breaks)
        self.assertBreaks(breaks, ((0, 110), (120, 160)))

        breaks = DriverBreaksHelper.additional_break_time(breaks, start_transit=0, end_transit=200, break_time_left=10)
        self.assertBreaks(breaks, ((0, 120), (120, 160)))
        breaks = DriverBreaksHelper.merge_intersected(breaks)
        self.assertBreaks(breaks, ((0, 160),))

        breaks = [Break(0, 100), Break(90, 110), Break(130, 150), Break(120, 160)]
        breaks = DriverBreaksHelper.clean_breaks(breaks, start_transit=0, end_transit=200, break_duration=170)
        self.assertBreaks(breaks, ((0, 170),))

        breaks = [
            Break(50, 100), Break(50, 60), Break(60, 70), Break(70, 80), Break(80, 90),
            Break(90, 100), Break(100, 110), Break(90, 110),
            Break(130, 150), Break(120, 160), Break(140, 170),
        ]
        breaks = DriverBreaksHelper.merge_intersected(breaks)
        self.assertBreaks(breaks, ((50, 110), (120, 170)))

        breaks = [
            Break(50, 100), Break(50, 60), Break(60, 70), Break(70, 80), Break(80, 90),
            Break(90, 100), Break(100, 110), Break(90, 110),
            Break(130, 150), Break(120, 160), Break(140, 170),
        ]
        breaks = DriverBreaksHelper.clean_breaks(breaks, start_transit=0, end_transit=200, break_duration=130)
        self.assertBreaks(breaks, ((30, 110), (120, 170)))

        breaks = [
            Break(50, 100), Break(50, 60), Break(60, 70), Break(70, 80), Break(80, 90),
            Break(90, 100), Break(100, 110), Break(90, 110),
            Break(130, 150), Break(120, 160), Break(140, 170),
        ]
        breaks = DriverBreaksHelper.clean_breaks(breaks, start_transit=0, end_transit=200, break_duration=165)
        self.assertBreaks(breaks, ((0, 115), (120, 170)))

        breaks = [
            Break(50, 100), Break(50, 60), Break(60, 70), Break(70, 80), Break(80, 90),
            Break(90, 100), Break(100, 110), Break(90, 110),
            Break(130, 150), Break(120, 160), Break(140, 170),
        ]
        breaks = DriverBreaksHelper.clean_breaks(breaks, start_transit=0, end_transit=200, break_duration=190)
        self.assertBreaks(breaks, ((0, 190),))

        breaks = [
            Break(50, 100), Break(50, 60), Break(60, 70), Break(70, 80), Break(80, 90),
            Break(90, 100), Break(100, 110), Break(90, 110),
            Break(130, 150), Break(120, 160), Break(140, 170),
        ]
        breaks = DriverBreaksHelper.clean_breaks(breaks, start_transit=30, end_transit=300, break_duration=190)
        self.assertBreaks(breaks, ((30, 220),))

    def assertBreaks(self, breaks: List[Break], expected_breaks):
        self.assertEqual(len(breaks), len(expected_breaks))
        for result_break, expected_break in zip(breaks, expected_breaks):
            self.assertEqual((result_break.start_time, result_break.end_time), expected_break)


class TestRouteTimeHelperCase(BaseTestEngineMixin, TestCase):
    def test_no_breaks(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'), focus=MerchantOptimisationFocus.TIME_BALANCE)
        settings.hub('53.907175,27.449568', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=10,)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=7,)
        settings.order(
            1, '53.906771,27.532308', driver=1,
            pickups=({'pickup_id': 1, 'pickup_address': '53.925965,27.501122'},
                     {'pickup_id': 2, 'pickup_address': '53.897700, 27.521235'},
                     {'pickup_id': 3, 'pickup_address': '53.919803,27.478715'},),
        )
        settings.order(2, '53.898275,27.503641', pickup_address='53.897700, 27.521235')
        settings.order(3, '53.881996,27.512813', pickup_address='53.919803,27.478715')
        settings.order(5, '53.889130, 27.608861')
        settings.order(7, '53.925965,27.501122')
        settings.service_time(10)
        settings.set_pickup_service_time(5)
        with self.setup_assignment(settings) as assignment:
            route0 = Route(
                0, list(map(RoutePointIndex, [7, 3, 10, 1, 5, 2, 8, 6, 4])),
                current_context, assignment.routing_manager, None
            )
            self.assertEqual(route0.get_route_finish_time(), 36953)
            route1 = Route(
                1, list(map(RoutePointIndex, [9])),
                current_context, assignment.routing_manager, None
            )
            self.assertEqual(route1.get_route_finish_time(), 32607)

    def test_break_in_transit_part(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'), focus=MerchantOptimisationFocus.TIME_BALANCE)
        settings.hub('53.907175,27.449568', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=10,
                        breaks=[DriverBreakSetting((8, 28), (8, 58), 15)],)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=7,
                        breaks=[DriverBreakSetting((8, 20), (8, 50), None)],)
        settings.order(
            1, '53.906771,27.532308', driver=1,
            pickups=({'pickup_id': 1, 'pickup_address': '53.925965,27.501122'},
                     {'pickup_id': 2, 'pickup_address': '53.897700, 27.521235'},
                     {'pickup_id': 3, 'pickup_address': '53.919803,27.478715'},),
        )
        settings.order(2, '53.898275,27.503641', pickup_address='53.897700, 27.521235')
        settings.order(3, '53.881996,27.512813', pickup_address='53.919803,27.478715')
        settings.order(5, '53.889130, 27.608861')
        settings.order(7, '53.925965,27.501122')
        settings.service_time(10)
        settings.set_pickup_service_time(5)
        with self.setup_assignment(settings) as assignment:
            route0 = Route(
                0, list(map(RoutePointIndex, [7, 3, 10, 1, 5, 2, 8, 6, 4])),
                current_context, assignment.routing_manager, None
            )
            self.assertEqual(route0.get_route_finish_time(), 38753)
            route1 = Route(
                1, list(map(RoutePointIndex, [9])),
                current_context, assignment.routing_manager, None
            )
            self.assertEqual(route1.get_route_finish_time(), 34407)

    def test_break_in_service_part(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'), focus=MerchantOptimisationFocus.TIME_BALANCE)
        settings.hub('53.907175,27.449568', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=10,
                        breaks=[DriverBreakSetting((8, 30), (9, 0), 15)],)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=7,
                        breaks=[DriverBreakSetting((8, 30), (9, 0), None)],)
        settings.order(
            1, '53.906771,27.532308', driver=1,
            pickups=({'pickup_id': 1, 'pickup_address': '53.925965,27.501122'},
                     {'pickup_id': 2, 'pickup_address': '53.897700, 27.521235'},
                     {'pickup_id': 3, 'pickup_address': '53.919803,27.478715'},),
        )
        settings.order(2, '53.898275,27.503641', pickup_address='53.897700, 27.521235')
        settings.order(3, '53.881996,27.512813', pickup_address='53.919803,27.478715')
        settings.order(5, '53.889130, 27.608861')
        settings.order(7, '53.925965,27.501122')
        settings.service_time(10)
        settings.set_pickup_service_time(5)
        with self.setup_assignment(settings) as assignment:
            route0 = Route(
                0, list(map(RoutePointIndex, [7, 3, 10, 1, 5, 2, 8, 6, 4])),
                current_context, assignment.routing_manager, None
            )
            self.assertEqual(route0.get_route_finish_time(), 38753)
            route1 = Route(
                1, list(map(RoutePointIndex, [9])),
                current_context, assignment.routing_manager, None
            )
            self.assertEqual(route1.get_route_finish_time(), 34487)

    def test_many_breaks(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'), focus=MerchantOptimisationFocus.TIME_BALANCE)
        settings.hub('53.907175,27.449568', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=10,
                        breaks=[DriverBreakSetting((8, 10), (8, 15), None), DriverBreakSetting((8, 20), (8, 25), None),
                                DriverBreakSetting((8, 30), (9, 0), 15)],)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=7,
                        breaks=[DriverBreakSetting((8, 35), (9, 0), None)],)
        settings.order(
            1, '53.906771,27.532308', driver=1,
            pickups=({'pickup_id': 1, 'pickup_address': '53.925965,27.501122'},
                     {'pickup_id': 2, 'pickup_address': '53.897700, 27.521235'},
                     {'pickup_id': 3, 'pickup_address': '53.919803,27.478715'},),
        )
        settings.order(2, '53.898275,27.503641', pickup_address='53.897700, 27.521235')
        settings.order(3, '53.881996,27.512813', pickup_address='53.919803,27.478715')
        settings.order(5, '53.889130, 27.608861')
        settings.order(7, '53.925965,27.501122')
        settings.service_time(10)
        settings.set_pickup_service_time(5)
        with self.setup_assignment(settings) as assignment:
            route0 = Route(
                0, list(map(RoutePointIndex, [7, 3, 10, 1, 5, 2, 8, 6, 4])),
                current_context, assignment.routing_manager, None
            )
            self.assertEqual(route0.get_route_finish_time(), 39515)
            route1 = Route(
                1, list(map(RoutePointIndex, [9])),
                current_context, assignment.routing_manager, None
            )
            self.assertEqual(route1.get_route_finish_time(), 34487)

    def test_dont_use_late_break(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'), focus=MerchantOptimisationFocus.TIME_BALANCE)
        settings.hub('53.907175,27.449568', hub_id=1)
        settings.driver(member_id=0, start_hub=1, end_hub=1, capacity=7,
                        breaks=[DriverBreakSetting((8, 35), (9, 0), None),
                                DriverBreakSetting((10, 35), (11, 0), 20)],)
        settings.order(5, '53.889130, 27.608861')
        settings.service_time(10)
        settings.set_pickup_service_time(5)
        with self.setup_assignment(settings) as assignment:
            route = Route(
                0, list(map(RoutePointIndex, [1])),
                current_context, assignment.routing_manager, None
            )
            self.assertEqual(route.get_route_finish_time(), 34487)

    def test_cant_place_break(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'), focus=MerchantOptimisationFocus.TIME_BALANCE)
        settings.hub('53.907175,27.449568', hub_id=1)
        settings.driver(member_id=0, start_hub=1, end_hub=1, capacity=10,
                        breaks=[DriverBreakSetting((8, 10), (8, 15), None), DriverBreakSetting((8, 20), (8, 25), None),
                                DriverBreakSetting((8, 30), (9, 0), 15)],)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=7,
                        breaks=[DriverBreakSetting((8, 35), (8, 55), 30)],)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=10,
                        breaks=[DriverBreakSetting((9, 10), (9, 15), None), DriverBreakSetting((9, 20), (9, 25), None),
                                DriverBreakSetting((9, 30), (10, 0), 15)],)
        settings.driver(member_id=3, start_hub=1, end_hub=1, capacity=7,
                        breaks=[DriverBreakSetting((8, 35), (8, 55), None)],)
        settings.driver(member_id=4, start_hub=1, end_hub=1, capacity=7,
                        breaks=[DriverBreakSetting((8, 35), (8, 55), 10)],)
        settings.driver(member_id=5, start_hub=1, end_hub=1, capacity=10,
                        breaks=[DriverBreakSetting((8, 10), (8, 15), None), DriverBreakSetting((8, 20), (8, 25), None),
                                DriverBreakSetting((8, 30), (9, 0), None)],)
        settings.order(
            1, '53.906771,27.532308',
            pickups=({'pickup_id': 1, 'pickup_address': '53.925965,27.501122'},
                     {'pickup_id': 2, 'pickup_address': '53.897700, 27.521235'},
                     {'pickup_id': 3, 'pickup_address': '53.919803,27.478715'},),
        )
        settings.order(2, '53.898275,27.503641', pickup_address='53.897700, 27.521235')
        settings.order(3, '53.881996,27.512813', pickup_address='53.919803,27.478715')
        settings.order(5, '53.889130, 27.608861', service_time=30,
                       deliver_after_time=(8, 20), deliver_before_time=(9, 0))
        settings.order(7, '53.925965,27.501122')
        settings.service_time(10)
        settings.set_pickup_service_time(5)
        with self.setup_assignment(settings) as assignment:
            route = Route(
                0, list(map(RoutePointIndex, [7, 3, 10, 1, 5, 2, 8, 6, 4])),
                current_context, assignment.routing_manager, None
            )
            self.assertEqual(route.get_route_finish_time(), 39515)
            route = Route(
                1, list(map(RoutePointIndex, [9])),
                current_context, assignment.routing_manager, None
            )
            self.assertEqual(route.get_route_finish_time(), 35007)
            route = Route(
                2, list(map(RoutePointIndex, [9, 7, 3, 10, 1, 5, 2, 8, 6, 4])),
                current_context, assignment.routing_manager, None
            )
            self.assertEqual(route.get_route_finish_time(), 43608)
            # Can't place breaks on next routes
            route = Route(
                3, list(map(RoutePointIndex, [9])),
                current_context, assignment.routing_manager, None
            )
            self.assertEqual(route.get_route_finish_time(), constants.TWO_DAYS)
            route = Route(
                4, list(map(RoutePointIndex, [9])),
                current_context, assignment.routing_manager, None
            )
            self.assertEqual(route.get_route_finish_time(), constants.TWO_DAYS)
            route = Route(
                5, list(map(RoutePointIndex, [9, 7, 3, 10, 1, 5, 2, 8, 6, 4])),
                current_context, assignment.routing_manager, None
            )
            self.assertEqual(route.get_route_finish_time(), constants.TWO_DAYS)

    @contextlib.contextmanager
    def setup_assignment(self, settings):
        params = EngineParameters(
            timezone=settings.timezone,
            day=settings.day,
            focus=settings.focus,
            default_job_service_time=settings.job_service_time,
            default_pickup_service_time=settings.pickup_service_time,
            optimisation_options=dict(
                jobs=[order.to_dict() for order in settings.orders],
                drivers=[driver.to_dict() for driver in settings.drivers],
                use_vehicle_capacity=settings.use_vehicle_capacity,
                required_start_sequence=settings.start_sequences,
            ),
        )
        with set_event_handler(TestROEvents()), set_dima_cache(self.distance_matrix_cache), \
                AssignmentContextManager(params, GroupAssignmentContext):
            assignment = BalancedAssignment(None, 10)
            assignment.setup()
            yield assignment
