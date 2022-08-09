from datetime import timedelta
from functools import wraps
from operator import itemgetter

from django.test import override_settings

from rest_framework.test import APITestCase

from notification.tests.mixins import NotificationTestMixin
from route_optimisation.const import OPTIMISATION_TYPES
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

from ...push_messages.composers import SoloOptimisationStatusChangeMessage
from ..test_utils.setting import DriverBreakSetting
from ..web.api_settings import SoloAPISettings
from ..web.mixins import ORToolsMixin
from ..web.optimisation_expectation import (
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
        result = func(self, *args, **kwargs)
        if not prev_value:
            self.merchant.use_pick_up_status = prev_value
            self.merchant.save(update_fields=('use_pick_up_status',))
        return result
    return patched


def enable_concatenated_orders_for_merchant(func):
    @wraps(func)
    def patched(self, *args, **kwargs):
        prev_value = self.merchant.enable_concatenated_orders
        if not prev_value:
            self.merchant.enable_concatenated_orders = True
            self.merchant.save(update_fields=('enable_concatenated_orders',))
        result = func(self, *args, **kwargs)
        if not prev_value:
            self.merchant.enable_concatenated_orders = prev_value
            self.merchant.save(update_fields=('enable_concatenated_orders',))
        return result
    return patched


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class OptimisationConcatenatedOrdersTestCase(NotificationTestMixin, ORToolsMixin, APITestCase):
    @enable_pickup_for_merchant
    @enable_concatenated_orders_for_merchant
    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_create_ro_with_concatenated_order(self, push_mock):
        settings = SoloAPISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, end_time=(18, 0), capacity=15,
                        breaks=[DriverBreakSetting((10, 0), (10, 20), 10)])
        settings.order(1, '-37.8421644,144.9399743', pickup_address='-37.755938,145.706767',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0), driver=1)
        settings.order(2, '-37.8421644,144.9399743', pickup_address='-37.755938,145.706767',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0), driver=1)
        settings.order(3, '-37.8421644,144.9399743', pickup_address='-37.698763,145.054753',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0), driver=1)
        settings.concatenated_order(4, (1, 2, 3))
        settings.order(5, '-37.8485871,144.6670881', pickup_address='-37.755938,145.706767',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0), driver=1)
        settings.order(6, '-37.698763,145.054753',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0), driver=1)
        settings.skip_day = True
        settings.set_initiator_driver(1)
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(ServiceTimeCheck(settings.orders_map[1], 10*3, is_pickup=True))  # Also 2 other pickups here
        expected.add_check(ServiceTimeCheck(settings.orders_map[2], 10*3, is_pickup=True))  # Also 2 other pickups here
        expected.add_check(ServiceTimeCheck(settings.orders_map[3], 10, is_pickup=True))
        expected.add_check(ServiceTimeCheck(settings.orders_map[4], 10))
        expected.add_check(ServiceTimeCheck(settings.orders_map[5], 10))
        expected.add_check(ServiceTimeCheck(settings.orders_map[5], 10*3, is_pickup=True))  # Also 2 other pickups here
        expected.add_check(ServiceTimeCheck(settings.orders_map[6], 10))
        expected.add_check(
            RoutePointsCountCheck(settings.drivers_map[1].id, 8, hubs=2, pickups=2, deliveries=3, breaks=1)
        )
        expected.add_check(LogCheck('3 jobs were included into Optimisation', partly=True))
        self.run_solo_optimisation(settings, expected)

        self.assertEqual(push_mock.call_count, 1)
        self.assertTrue(isinstance(push_mock.call_args_list[0][0][0], SoloOptimisationStatusChangeMessage))
        self.check_push_composer_no_errors(push_mock.call_args_list[0][0][0])
        self.assertEqual(Order.aggregated_objects.get(id=settings.orders_map[2].id).status, OrderStatus.ASSIGNED)
        self.assertEqual(Order.aggregated_objects.get(id=settings.orders_map[4].id).status, OrderStatus.ASSIGNED)
        self.assertEqual(Order.aggregated_objects.get(id=settings.orders_map[6].id).status, OrderStatus.ASSIGNED)

        self.client.force_authenticate(settings.drivers_map[1])
        date_from = self._day - timedelta(days=5)
        date_to = self._day + timedelta(days=5)
        resp = self.client.get('/api/mobile/daily_orders/v1/', data={'date_from': date_from, 'date_to': date_to})
        self.assert_response_daily_orders_v1(resp)
        resp = self.client.get('/api/mobile/daily_orders/v2/', data={'date_from': date_from, 'date_to': date_to})
        self.assert_response_daily_orders_v2(resp)

    def assert_response_daily_orders_v1(self, resp):
        self.assertEqual(resp.status_code, 200)
        day_orders = resp.json()[0]
        self.assertEqual(day_orders['delivery_date'], str(self._day))
        self.assertIsNone(day_orders['concatenated_orders'])
        self.assertIsNone(day_orders['orders'])
        self.assertEqual(len(day_orders['route_optimisations']), 1)
        points = day_orders['route_optimisations'][0]['points']
        self.assertEqual(len(points['orders']), 3)
        self.assertEqual(len(points['concatenated_orders']), 3)
        self.assertEqual(points['hubs'][0]['number'], 1)
        self.assertEqual(points['hubs'][1]['number'], 8)

        flat_points = [item for name in ['hubs', 'orders', 'concatenated_orders'] for item in points[name]]
        flat_points = sorted(flat_points, key=itemgetter('number'))
        prev = 0
        for point in flat_points:
            if prev + 1 != point['number']:
                self.fail('Points numbers are not consecutive')
            prev += 1

    def assert_response_daily_orders_v2(self, resp):
        self.assertEqual(resp.status_code, 200)
        day_orders = resp.json()[0]
        self.assertEqual(day_orders['delivery_date'], str(self._day))
        self.assertIsNone(day_orders['concatenated_orders'])
        self.assertIsNone(day_orders['orders'])
        self.assertEqual(len(day_orders['route_optimisations']), 1)
        points = day_orders['route_optimisations'][0]['points']
        self.assertEqual(len(points['orders']), 3)
        self.assertEqual(len(points['concatenated_orders']), 3)
        self.assertEqual(points['hubs'][0]['number'], 1)
        self.assertEqual(points['hubs'][1]['number'], 9)
        self.assertEqual(points['breaks'][0]['number'], 3)
        self.assertEqual(points['breaks'][0]['point_object']['start_time'], f'{self._day}T08:48:10+10:00')
        self.assertEqual(points['breaks'][0]['point_object']['end_time'], f'{self._day}T10:10:00+10:00')

        flat_points = [item for name in ['hubs', 'orders', 'concatenated_orders', 'breaks'] for item in points[name]]
        flat_points = sorted(flat_points, key=itemgetter('number'))
        prev = 0
        for point in flat_points:
            if prev + 1 != point['number']:
                raise self.failureException('Points numbers are not consecutive')
            prev += 1
