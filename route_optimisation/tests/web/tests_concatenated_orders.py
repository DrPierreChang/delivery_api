from functools import wraps

from django.test import override_settings

from rest_framework import status
from rest_framework.test import APITestCase

from notification.tests.mixins import NotificationTestMixin
from route_optimisation.const import OPTIMISATION_TYPES
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order
from tasks.push_notification.push_messages.order_change_status_composers import (
    BulkAssignedMessage,
    BulkUnassignedMessage,
)

from ...models import RoutePoint
from ...push_messages.composers import NewRoutePushMessage, RemovedOptimisationPushMessage
from .api_settings import APISettings
from .mixins import ORToolsMixin
from .optimisation_expectation import (
    DeliveryRODetailsFillCheck,
    LogCheck,
    NumberFieldConsecutiveCheck,
    OptimisationExpectation,
    OrderIsAssignedCheck,
    RoutePointsCountCheck,
    ServiceTimeCheck,
)
from .tests_pickup_feature import enable_pickup_for_merchant


def enable_concatenated_orders_for_merchant(func):
    @wraps(func)
    def patched(self, *args, **kwargs):
        prev_value = self.merchant.enable_concatenated_orders
        if not prev_value:
            self.merchant.enable_concatenated_orders = True
            self.merchant.save(update_fields=('enable_concatenated_orders',))
        try:
            result = func(self, *args, **kwargs)
            return result
        finally:
            if not prev_value:
                self.merchant.enable_concatenated_orders = prev_value
                self.merchant.save(update_fields=('enable_concatenated_orders',))
    return patched


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=3, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=3)
class OptimisationConcatenatedOrdersTestCase(NotificationTestMixin, ORToolsMixin, APITestCase):
    api_url = '/api/web/ro/optimisation/'

    @enable_pickup_for_merchant
    @enable_concatenated_orders_for_merchant
    def test_create_ro_with_concatenated_order_no_pickups(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8421644,144.9399743',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(3, '-37.8421644,144.9399743',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.concatenated_order(4, (1, 2, 3))
        settings.order(5, '-37.8485871,144.6670881',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(6, '-37.698763,145.054753',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.service_time(12)
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(ServiceTimeCheck(settings.orders_map[4], 12))
        expected.add_check(ServiceTimeCheck(settings.orders_map[5], 12))
        expected.add_check(ServiceTimeCheck(settings.orders_map[6], 12))
        expected.add_check(DeliveryRODetailsFillCheck())
        expected.add_check(RoutePointsCountCheck(settings.drivers_map[1].id, 5, hubs=2, deliveries=3))
        expected.add_check(LogCheck('3 new jobs were assigned to', partly=True))
        self.run_optimisation(settings, expected)

    @enable_pickup_for_merchant
    @enable_concatenated_orders_for_merchant
    def test_create_ro_with_concatenated_order(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743', pickup_address='-37.755938,145.706767',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8421644,144.9399743', pickup_address='-37.5795883,143.8387151',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(3, '-37.8421644,144.9399743', pickup_address='-37.698763,145.054753',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.concatenated_order(4, (1, 2, 3))
        settings.order(5, '-37.8485871,144.6670881', pickup_address='-37.755938,145.706767',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(6, '-37.698763,145.054753',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(7, '-37.8421644,144.9399743', pickup_address='-37.755938,145.706767',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(8, '-37.8421644,144.9399743', pickup_address='-37.5795883,143.8387151',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(9, '-37.8421644,144.9399743', pickup_address='-37.5795883,143.8387151',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.concatenated_order(10, (7, 8, 9))
        settings.service_time(12)
        settings.set_pickup_service_time(11)
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(ServiceTimeCheck(settings.orders_map[1], 11*3, is_pickup=True))  # Also 5th and 7th
        expected.add_check(ServiceTimeCheck(settings.orders_map[2], 11*3, is_pickup=True))  # Also 8th and 9th
        expected.add_check(ServiceTimeCheck(settings.orders_map[3], 11, is_pickup=True))
        expected.add_check(ServiceTimeCheck(settings.orders_map[4], 12))
        expected.add_check(ServiceTimeCheck(settings.orders_map[5], 12))
        expected.add_check(ServiceTimeCheck(settings.orders_map[5], 11*3, is_pickup=True))  # Also 1st and 7th
        expected.add_check(ServiceTimeCheck(settings.orders_map[6], 12))
        expected.add_check(ServiceTimeCheck(settings.orders_map[7], 11*3, is_pickup=True))  # Also 1st and 5th
        expected.add_check(ServiceTimeCheck(settings.orders_map[8], 11*3, is_pickup=True))  # Also 2th and 9th
        expected.add_check(ServiceTimeCheck(settings.orders_map[9], 11*3, is_pickup=True))  # Also 2th and 8th
        expected.add_check(ServiceTimeCheck(settings.orders_map[10], 12))
        expected.add_check(DeliveryRODetailsFillCheck())
        expected.add_check(RoutePointsCountCheck(settings.drivers_map[1].id, 9, hubs=2, pickups=3, deliveries=4))
        expected.add_check(LogCheck('4 new jobs were assigned to', partly=True))
        opt_id = self.run_optimisation(settings, expected)

        get = self.client.get(self.api_url + str(opt_id))
        self.assertEqual(len(get.data['routes'][0]['points'][1]['objects_ids']), 2)
        self.assertEqual(len(get.data['routes'][0]['points'][3]['objects_ids']), 1)
        self.assertEqual(len(get.data['routes'][0]['points'][4]['objects_ids']), 3)

        self.client.force_authenticate(settings.drivers_map[1])
        get = self.get_legacy_driver_routes(self._day)
        self.assertEqual(len(get.data['results'][0]['route_points_orders']), 4)
        self.assertEqual(get.data['results'][0]['route_points_orders'][0]['number'], 2)
        self.assertEqual(get.data['results'][0]['route_points_orders'][1]['number'], 3)
        self.assertEqual(get.data['results'][0]['route_points_orders'][2]['number'], 4)
        self.assertEqual(get.data['results'][0]['route_points_orders'][3]['number'], 5)
        self.assertEqual(get.data['results'][0]['route_points_hubs'][0]['number'], 1)
        self.assertEqual(get.data['results'][0]['route_points_hubs'][1]['number'], 6)

        get = self.get_legacy_driver_routes_v1(self._day)
        self.assertEqual(len(get.data['results'][0]['route_points_orders']), 11)

        self.assertEqual(RoutePoint.objects.filter(route__optimisation__id=opt_id).count(), 13)
        concatenated_orders_url = '/api/mobile/concatenated_orders/v1/'
        resp = self.client.patch(
            '{}{}'.format(concatenated_orders_url, settings.orders_map[4].id), {'status': OrderStatus.NOT_ASSIGNED}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(RoutePoint.objects.filter(route__optimisation__id=opt_id).count(), 9)

    @enable_pickup_for_merchant
    @enable_concatenated_orders_for_merchant
    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_create_ro_with_concatenated_order_capacity(self, push_mock):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, start_time=(8, 0), end_time=(20, 0), capacity=10)
        settings.order(1, '-37.8421644,144.9399743', pickup_address='-37.755938,145.706767',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0), capacity=5)
        settings.order(2, '-37.8421644,144.9399743', pickup_address='-37.5795883,143.8387151',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0), capacity=3)
        settings.order(3, '-37.8421644,144.9399743', pickup_address='-37.698763,145.054753',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0), capacity=1)
        settings.concatenated_order(4, (1, 2, 3))
        settings.order(5, '-37.8485871,144.6670881', pickup_address='-37.755938,145.706767',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0), capacity=7)
        settings.order(6, '-37.698763,145.054753',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0), capacity=6)
        settings.service_time(12)
        settings.set_pickup_service_time(5)
        settings.set_use_vehicle_capacity(True)
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(NumberFieldConsecutiveCheck())
        expected.add_check(OrderIsAssignedCheck(settings.orders_map[1].id))
        expected.add_check(OrderIsAssignedCheck(settings.orders_map[2].id))
        expected.add_check(OrderIsAssignedCheck(settings.orders_map[3].id))
        expected.add_check(OrderIsAssignedCheck(settings.orders_map[4].id))
        expected.add_check(OrderIsAssignedCheck(settings.orders_map[5].id))
        expected.add_check(OrderIsAssignedCheck(settings.orders_map[6].id))
        expected.add_check(ServiceTimeCheck(settings.orders_map[1], 5, is_pickup=True))
        expected.add_check(ServiceTimeCheck(settings.orders_map[2], 5, is_pickup=True))
        expected.add_check(ServiceTimeCheck(settings.orders_map[3], 5, is_pickup=True))
        expected.add_check(ServiceTimeCheck(settings.orders_map[4], 12))
        expected.add_check(ServiceTimeCheck(settings.orders_map[5], 12))
        expected.add_check(ServiceTimeCheck(settings.orders_map[5], 5, is_pickup=True))
        expected.add_check(ServiceTimeCheck(settings.orders_map[6], 12))
        expected.add_check(DeliveryRODetailsFillCheck())
        expected.add_check(RoutePointsCountCheck(settings.drivers_map[1].id, 9, hubs=2, pickups=4, deliveries=3))
        expected.add_check(LogCheck('3 new jobs were assigned to', partly=True))
        push_mock.reset_mock()
        opt_id = self.run_optimisation(settings, expected)

        self.assertEqual(push_mock.call_count, 2)
        assigned_push_sent, new_route_push_sent = False, False
        for (push_composer,), _ in push_mock.call_args_list:
            if isinstance(push_composer, BulkAssignedMessage):
                assigned_push_sent = True
                self.assertEqual(len(push_composer.get_kwargs(1)['data']['orders_ids']), 3)
            if isinstance(push_composer, NewRoutePushMessage):
                new_route_push_sent = True
            self.check_push_composer_no_errors(push_composer)
        self.assertTrue(assigned_push_sent)
        self.assertTrue(new_route_push_sent)
        self.assertEqual(Order.aggregated_objects.get(id=settings.orders_map[2].id).status, OrderStatus.ASSIGNED)
        self.assertEqual(Order.aggregated_objects.get(id=settings.orders_map[4].id).status, OrderStatus.ASSIGNED)
        self.assertEqual(Order.aggregated_objects.get(id=settings.orders_map[6].id).status, OrderStatus.ASSIGNED)

        push_mock.reset_mock()
        resp = self.client.delete('{}{}'.format(self.api_url, opt_id), data={'unassign': True})
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(push_mock.call_count, 2)
        unassigned_push_sent, removed_push_sent = False, False
        for (push_composer,), _ in push_mock.call_args_list:
            if isinstance(push_composer, BulkUnassignedMessage):
                unassigned_push_sent = True
                self.assertEqual(len(push_composer.get_kwargs(1)['data']['orders_ids']), 3)
            if isinstance(push_composer, RemovedOptimisationPushMessage):
                removed_push_sent = True
            self.check_push_composer_no_errors(push_composer)
        self.assertTrue(unassigned_push_sent)
        self.assertTrue(removed_push_sent)
        self.assertEqual(Order.aggregated_objects.get(id=settings.orders_map[1].id).status, OrderStatus.NOT_ASSIGNED)
        self.assertEqual(Order.aggregated_objects.get(id=settings.orders_map[4].id).status, OrderStatus.NOT_ASSIGNED)
        self.assertEqual(Order.aggregated_objects.get(id=settings.orders_map[5].id).status, OrderStatus.NOT_ASSIGNED)
