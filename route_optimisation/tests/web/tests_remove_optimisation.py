from operator import attrgetter

from django.test import override_settings

from rest_framework import status
from rest_framework.test import APITestCase

import mock

from notification.tests.mixins import NotificationTestMixin
from route_optimisation.const import OPTIMISATION_TYPES
from route_optimisation.models import RouteOptimisation
from route_optimisation.push_messages.composers import RemovedOptimisationPushMessage
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order
from tasks.push_notification.push_messages.order_change_status_composers import BulkUnassignedMessage

from .api_settings import APISettings, SoloAPISettings
from .mixins import ORToolsMixin
from .optimisation_expectation import OptimisationExpectation


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class RemoveRouteOptimisationAPITestCase(NotificationTestMixin, ORToolsMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.manager)
        self.settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                                    self.merchant, self.manager)
        self.settings.hub('-37.869197,144.820283', hub_id=1)
        self.settings.hub('-37.868197,144.820183', hub_id=2)
        self.settings.driver(member_id=1, start_hub=1, end_hub=2, capacity=15)
        self.driver = self.settings.drivers_map[1]
        self.settings.order(1, '-37.6780953, 145.1290807')
        self.settings.order(2, '-37.926451, 144.998992')
        self.settings.order(3, '-35.5418094, 144.9643013')
        self.settings.order(4, '-37.9202176, 145.2230781')
        self.expectation = OptimisationExpectation(skipped_orders=0)

    def assert_not_removed(self, opt_id):
        url = '{}{}'.format(self.api_url, opt_id)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['state'] == RouteOptimisation.STATE.REMOVED, False)

    def assert_removed(self, opt_id):
        url = '{}{}'.format(self.api_url, opt_id)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        ro_object = RouteOptimisation.objects.get(id=opt_id)
        self.assertEqual(ro_object.state, RouteOptimisation.STATE.REMOVED)

    def assert_drivers_routes_count(self, driver, day, count):
        prev_authenticated_user = self.client.handler._force_user
        self.client.force_authenticate(driver)
        driver_routes_resp = self.get_legacy_driver_routes(day)
        self.assertEqual(driver_routes_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(driver_routes_resp.data['count'], count)
        self.client.force_authenticate(prev_authenticated_user)

    def assert_orders_status_count(self, orders, order_status, count):
        needed_orders = Order.objects.filter(id__in=map(attrgetter('id'), orders), status=order_status)
        self.assertEqual(needed_orders.count(), count)

    def assert_orders_in_status_existence(self, orders, order_status, existence=True):
        needed_orders = Order.objects.filter(id__in=map(attrgetter('id'), orders), status=order_status)
        self.assertEqual(needed_orders.exists(), existence)

    def test_remove_group_optimisation_by_manager(self):
        opt_id = self.run_optimisation(self.settings, self.expectation)
        self.assert_not_removed(opt_id)
        self.remove_optimisation(opt_id, unassign=False)
        self.remove_optimisation(opt_id, status_code=status.HTTP_404_NOT_FOUND, unassign=False)
        self.assert_orders_in_status_existence(list(self.settings.orders_map.values()), OrderStatus.NOT_ASSIGNED,
                                               existence=False)
        self.assert_removed(opt_id)

    def test_driver_cant_remove_group(self):
        opt_id = self.run_optimisation(self.settings, self.expectation)
        url = '{}{}'.format(self.api_url, opt_id)
        self.client.force_authenticate(self.driver)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.remove_optimisation(opt_id, status_code=status.HTTP_403_FORBIDDEN)

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_remove_solo_optimisation_by_manager(self, push_mock):
        settings = SoloAPISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                                self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.hub('-37.868197,144.820183', hub_id=2)
        settings.driver(member_id=1, start_hub=1, end_hub=2, capacity=15)
        settings.order(5, '-37.9202176, 145.2230781', driver=1)
        self.driver = settings.drivers_map[1]
        settings.set_initiator_driver(1)
        opt_id = self.run_legacy_solo_optimisation(settings, self.expectation)
        push_mock.reset_mock()
        self.assert_not_removed(opt_id)
        self.remove_optimisation(opt_id)
        self.remove_optimisation(opt_id, status_code=status.HTTP_404_NOT_FOUND)
        self.assertEqual(push_mock.call_count, 1)
        removed_route_push_sent = False
        for (push_composer,), _ in push_mock.call_args_list:
            if isinstance(push_composer, RemovedOptimisationPushMessage):
                removed_route_push_sent = True
            self.check_push_composer_no_errors(push_composer)
        self.assertTrue(removed_route_push_sent)
        self.assert_removed(opt_id)

    def test_unassign_jobs_on_remove(self):
        opt_id = self.run_optimisation(self.settings, self.expectation)
        self.assert_not_removed(opt_id)
        self.remove_optimisation(opt_id, unassign=True)
        orders = list(self.settings.orders_map.values())
        self.assert_orders_in_status_existence(orders, OrderStatus.NOT_ASSIGNED)
        self.assert_orders_in_status_existence(orders, OrderStatus.ASSIGNED, existence=False)
        self.assert_removed(opt_id)

    def test_dont_unassign_in_progress(self):
        opt_id = self.run_optimisation(self.settings, self.expectation)
        self.assert_not_removed(opt_id)

        self.client.force_authenticate(self.driver)
        orders = list(self.settings.orders_map.values())
        resp = self.client.put('{url}{id}/status/'.format(url=self.orders_url, id=orders[0].id),
                               {'status': 'in_progress'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(self.manager)
        self.remove_optimisation(opt_id, unassign=True)
        in_progress_order = Order.objects.filter(status=OrderStatus.IN_PROGRESS).first()
        self.assertEqual(in_progress_order.id, orders[0].id)
        self.assert_orders_status_count(orders, OrderStatus.NOT_ASSIGNED, 3)
        self.assert_orders_status_count(orders, OrderStatus.IN_PROGRESS, 1)
        self.assert_orders_in_status_existence(orders, OrderStatus.ASSIGNED, existence=False)
        self.assert_removed(opt_id)

    def test_dont_unassign_previously_assigned(self):
        self.settings.order(5, '-37.9202176, 145.2230781', driver=1)
        opt_id = self.run_optimisation(self.settings, self.expectation)
        orders = list(self.settings.orders_map.values())
        self.assert_not_removed(opt_id)
        self.client.force_authenticate(self.manager)
        self.remove_optimisation(opt_id, unassign=True)
        self.assert_orders_status_count(orders, OrderStatus.NOT_ASSIGNED, 4)
        self.assert_orders_status_count(orders, OrderStatus.ASSIGNED, 1)
        assigned_order = Order.objects.filter(status=OrderStatus.ASSIGNED).first()
        self.assertEqual(assigned_order.id, self.settings.orders_map[5].id)
        self.assert_removed(opt_id)

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_bulk_unassign_push_to_driver(self, push_mock):
        opt_id = self.run_optimisation(self.settings, self.expectation)
        push_mock.reset_mock()
        self.remove_optimisation(opt_id, unassign=True)
        self.assertEqual(push_mock.call_count, 2)
        bulk_unassigned_push_sent, removed_route_push_sent = False, False
        for (push_composer,), _ in push_mock.call_args_list:
            if isinstance(push_composer, BulkUnassignedMessage):
                bulk_unassigned_push_sent = True
                self.assertEqual(len(push_composer.events), 4)
            if isinstance(push_composer, RemovedOptimisationPushMessage):
                removed_route_push_sent = True
            self.check_push_composer_no_errors(push_composer)
        self.assertTrue(bulk_unassigned_push_sent)
        self.assertTrue(removed_route_push_sent)
        self.assert_removed(opt_id)

    def test_create_solo_after_removed_group(self):
        settings = SoloAPISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.hub('-37.868197,144.820183', hub_id=2)
        settings.driver(member_id=1, start_hub=1, end_hub=2, capacity=15)
        self.driver = settings.drivers_map[1]
        settings.order(1, '-37.6780953, 145.1290807')
        settings.order(2, '-37.926451, 144.998992')
        settings.order(3, '-35.5418094, 144.9643013')
        settings.order(4, '-37.9202176, 145.2230781')

        opt_id = self.run_optimisation(settings, self.expectation)
        self.assert_drivers_routes_count(self.driver, self._day, 1)

        with mock.patch('webhooks.celery_tasks.send_external_event') as send_external_event:
            self.remove_optimisation(opt_id, unassign=False)
            self.assertTrue(send_external_event.called)
            self.assertEqual(send_external_event.call_args.args[3], 'optimisation.deleted')

        self.assert_drivers_routes_count(self.driver, self._day, 0)
        settings.order(5, '-37.9202176, 145.2230781', driver=1)
        settings.set_initiator_driver(1)
        self.run_legacy_solo_optimisation(settings, self.expectation)
        self.assert_drivers_routes_count(self.driver, self._day, 1)
