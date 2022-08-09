from django.test import TestCase, override_settings

import pytz

from route_optimisation.tests.engine.optimisation_expectation import (
    OptimisationExpectation,
    PickupBeforeDeliveryCheck,
    ServiceTimeCheck,
)

from .engine_settings import EngineSettings
from .tests_engine import BaseTestEngineMixin


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class TestEngineCase(BaseTestEngineMixin, TestCase):

    def test_multi_pickup_no_capacity(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'))
        settings.hub('53.907175,27.449568', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=10)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=7)
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
        expectation = OptimisationExpectation(max_distance=62000, skipped_orders=0)
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=1, pickups_count=3))
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=2, pickups_count=1))
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=5, pickups_count=0))
        result = self.optimise(settings=settings, expectation=expectation)
        print('result', result)

    def test_multi_pickup_with_capacity(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'))
        settings.hub('53.907175,27.449568', hub_id=1)

        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=10)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=7)

        settings.order(
            1, '53.906771,27.532308', driver=1, capacity=6,
            pickups=({'pickup_id': 1, 'pickup_address': '53.925965,27.501122', 'capacity': 1, 'service_time': 2},
                     {'pickup_id': 2, 'pickup_address': '53.897700, 27.521235', 'capacity': 2},
                     {'pickup_id': 3, 'pickup_address': '53.919803,27.478715', 'capacity': 3},),
        )
        settings.order(2, '53.898275,27.503641', pickup_address='53.897700, 27.521235', capacity=3)
        settings.order(3, '53.881996,27.512813', pickup_address='53.919803,27.478715', capacity=3)
        settings.order(5, '53.889130, 27.608861', capacity=3)
        settings.order(7, '53.925965,27.501122', capacity=3)
        settings.service_time(10)
        settings.set_pickup_service_time(5)
        settings.use_vehicle_capacity = True
        expectation = OptimisationExpectation(max_distance=64000, skipped_orders=0)
        expectation.add_check(ServiceTimeCheck(order_id=1, service_time_minutes=10))
        expectation.add_check(ServiceTimeCheck(order_id=1, service_time_minutes=2, is_pickup=True, pickup_id=1))
        expectation.add_check(ServiceTimeCheck(order_id=1, service_time_minutes=5, is_pickup=True, pickup_id=2))
        expectation.add_check(ServiceTimeCheck(order_id=2, service_time_minutes=5, is_pickup=True))
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=1, pickups_count=3))
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=2, pickups_count=1))
        expectation.add_check(PickupBeforeDeliveryCheck(order_id=5, pickups_count=0))
        result = self.optimise(settings=settings, expectation=expectation)
        print('result', result)
