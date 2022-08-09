from functools import wraps

from django.test import override_settings

from rest_framework import status
from rest_framework.test import APITestCase

import mock

from route_optimisation.const import OPTIMISATION_TYPES

from .api_settings import APISettings, SoloAPISettings
from .mixins import ORToolsMixin
from .optimisation_expectation import (
    LogCheck,
    NumberFieldConsecutiveCheck,
    OptimisationExpectation,
    RoutePointsCountCheck,
    ServiceTimeCheck,
)


def enable_pickup_for_merchant(func):
    @wraps(func)
    def patched(self, *args, **kwargs):
        prev_value = self.merchant.use_pick_up_status
        if not prev_value:
            self.merchant.use_pick_up_status = True
            self.merchant.save(update_fields=('use_pick_up_status',))
        try:
            result = func(self, *args, **kwargs)
            return result
        finally:
            if not prev_value:
                self.merchant.use_pick_up_status = prev_value
                self.merchant.save(update_fields=('use_pick_up_status',))
    return patched


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class PickupInOptimisationDataTestCase(ORToolsMixin, APITestCase):
    @enable_pickup_for_merchant
    def test_create_ro_and_return_legacy_routes(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)
        settings.skill(1, service_time=5)
        settings.skill(2, service_time=3)
        settings.skill(3, service_time=0)
        settings.skill(4)
        settings.driver(member_id=2, start_hub=1, end_hub=1, skill_set=(1, 2, 3, 4), end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743', pickup_address='-37.755938,145.706767', skill_set=(1, 2, 3, 4),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881', pickup_address='-37.755938,145.706767', skill_set=(1, 2),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(3, '-37.8238154,145.0108082', pickup_address='-37.5795883,143.8387151', skill_set=(3, 4),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(4, '-37.698763,145.054753', skill_set=(4,),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.service_time(12)
        settings.set_pickup_service_time(11)
        settings.set_start_place(hub=1)
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(ServiceTimeCheck(settings.orders_map[1], 5))
        expected.add_check(ServiceTimeCheck(settings.orders_map[2], 5))
        expected.add_check(ServiceTimeCheck(settings.orders_map[3], 0))
        expected.add_check(ServiceTimeCheck(settings.orders_map[4], 12))
        expected.add_check(ServiceTimeCheck(settings.orders_map[3], 11, is_pickup=True))
        expected.add_check(RoutePointsCountCheck(settings.drivers_map[2].id, 8, hubs=2, pickups=2, deliveries=4))
        expected.add_check(LogCheck('4 new jobs were assigned to', partly=True))
        self.run_optimisation(settings, expected)

        self.client.force_authenticate(settings.drivers_map[2])
        get = self.get_legacy_driver_routes(self._day)
        self.assertEqual(len(get.data['results'][0]['route_points_orders']), 4)
        self.assertEqual(get.data['results'][0]['route_points_orders'][0]['number'], 2)
        self.assertEqual(get.data['results'][0]['route_points_orders'][1]['number'], 3)
        self.assertEqual(get.data['results'][0]['route_points_orders'][2]['number'], 4)
        self.assertEqual(get.data['results'][0]['route_points_orders'][3]['number'], 5)
        self.assertEqual(get.data['results'][0]['route_points_hubs'][0]['number'], 1)
        self.assertEqual(get.data['results'][0]['route_points_hubs'][1]['number'], 6)

    def test_create_ro_with_disabled_pickup_feature(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)
        settings.driver(member_id=2, start_hub=1, end_hub=1, end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743', pickup_address='-37.755938,145.706767',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881', pickup_address='-37.755938,145.706767',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(3, '-37.8238154,145.0108082', pickup_address='-37.5795883,143.8387151',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(4, '-37.698763,145.054753', skill_set=(4,),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.service_time(12)
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(RoutePointsCountCheck(settings.drivers_map[2].id, 6, hubs=2, deliveries=4))
        expected.add_check(LogCheck('4 new jobs were assigned to', partly=True))
        self.run_optimisation(settings, expected)

    @enable_pickup_for_merchant
    def test_create_solo_correct_log(self):
        settings = SoloAPISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)
        settings.driver(member_id=2, start_hub=1, end_hub=1, end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743', pickup_address='-37.755938,145.706767', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881', pickup_address='-37.755938,145.706767', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(3, '-37.8238154,145.0108082', pickup_address='-37.5795883,143.8387151', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(4, '-37.698763,145.054753', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.initiator_driver = settings.drivers_map[2]
        settings.initiator_driver_setting = settings.drivers_setting_map[2]
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(LogCheck('4 jobs were included into Optimisation', partly=True))
        expected.add_check(RoutePointsCountCheck(settings.drivers_map[2].id, 8, hubs=2, pickups=2, deliveries=4))
        opt_id = self.run_solo_optimisation(settings, expected)
        with mock.patch('tasks.models.Order.notify_customer') as notify_mock:
            resp = self.client.post('{}{}/notify_customers'.format(self.api_url, opt_id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(notify_mock.call_count, 4)

    @enable_pickup_for_merchant
    def test_create_ro_and_return_legacy_routes_mobile_api_v1(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)
        settings.skill(1, service_time=5)
        settings.skill(2, service_time=3)
        settings.skill(3, service_time=0)
        settings.skill(4)
        settings.driver(member_id=2, start_hub=1, end_hub=1, skill_set=(1, 2, 3, 4), end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743', pickup_address='-37.755938,145.706767', skill_set=(1, 2, 3, 4),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881', pickup_address='-37.755938,145.706767', skill_set=(2, 3),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(3, '-37.8238154,145.0108082', pickup_address='-37.5795883,143.8387151', skill_set=(3, 4),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(4, '-37.698763,145.054753', skill_set=(4,),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.service_time(12)
        settings.set_pickup_service_time(11)
        settings.set_start_place(hub=1)
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(ServiceTimeCheck(settings.orders_map[1], 5))
        expected.add_check(ServiceTimeCheck(settings.orders_map[2], 3))
        expected.add_check(ServiceTimeCheck(settings.orders_map[3], 0))
        expected.add_check(ServiceTimeCheck(settings.orders_map[4], 12))
        expected.add_check(ServiceTimeCheck(settings.orders_map[3], 11, is_pickup=True))
        expected.add_check(RoutePointsCountCheck(settings.drivers_map[2].id, 8, hubs=2, pickups=2, deliveries=4))
        self.run_optimisation(settings, expected)

        self.client.force_authenticate(settings.drivers_map[2])
        get = self.get_legacy_driver_routes_v1(self._day)
        self.assertEqual(len(get.data['results'][0]['route_points_orders']), 7)
