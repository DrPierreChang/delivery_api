from django.test import override_settings

from rest_framework import status
from rest_framework.test import APITestCase

from route_optimisation.const import OPTIMISATION_TYPES
from route_optimisation.models import DriverRoute, RouteOptimisation
from tasks.mixins.order_status import OrderStatus

from .api_settings import APISettings
from .mixins import ORToolsMixin
from .optimisation_expectation import OptimisationExpectation


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class StateChangeTestCase(ORToolsMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.manager)
        self.settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                                    self.merchant, self.manager)
        self.settings.hub('-37.869197,144.820283', hub_id=1)
        self.settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=15)
        self.settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=15)
        self.settings.driver(member_id=3, start_hub=1, end_hub=1, capacity=15)
        self.settings.driver(member_id=4, start_hub=1, end_hub=1, capacity=15)
        self.settings.order(1, '-37.6780953, 145.1290807', driver=1)
        self.settings.order(2, '-37.926451, 144.998992', driver=1)
        self.settings.order(3, '-35.5418094, 144.9643013', driver=2)
        self.settings.order(4, '-37.9202176, 145.2230781', driver=3)
        self.settings.order(5, '-37.9202176, 145.2230781', driver=4)

    def test_status_change(self):
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_optimisation(self.settings, expectation)

        self.assert_optimisation_state(optimisation_id, RouteOptimisation.STATE.COMPLETED)
        self.assert_route_state(driver_id=1, route_state=DriverRoute.STATE.CREATED)
        self.assert_route_state(driver_id=2, route_state=DriverRoute.STATE.CREATED)
        self.assert_route_state(driver_id=3, route_state=DriverRoute.STATE.CREATED)
        self.assert_route_state(driver_id=4, route_state=DriverRoute.STATE.CREATED)

        self.change_order_status(driver_id=1, order_id=1, order_status=OrderStatus.IN_PROGRESS)

        self.assert_optimisation_state(optimisation_id, RouteOptimisation.STATE.RUNNING)
        self.assert_route_state(driver_id=1, route_state=DriverRoute.STATE.RUNNING)
        self.assert_route_state(driver_id=2, route_state=DriverRoute.STATE.CREATED)
        self.assert_route_state(driver_id=3, route_state=DriverRoute.STATE.CREATED)
        self.assert_route_state(driver_id=4, route_state=DriverRoute.STATE.CREATED)

        self.change_order_status(driver_id=2, order_id=3, order_status=OrderStatus.IN_PROGRESS)

        self.assert_optimisation_state(optimisation_id, RouteOptimisation.STATE.RUNNING)
        self.assert_route_state(driver_id=1, route_state=DriverRoute.STATE.RUNNING)
        self.assert_route_state(driver_id=2, route_state=DriverRoute.STATE.RUNNING)
        self.assert_route_state(driver_id=3, route_state=DriverRoute.STATE.CREATED)
        self.assert_route_state(driver_id=4, route_state=DriverRoute.STATE.CREATED)

        self.change_order_status(driver_id=3, order_id=4, order_status=OrderStatus.DELIVERED)

        self.assert_optimisation_state(optimisation_id, RouteOptimisation.STATE.RUNNING)
        self.assert_route_state(driver_id=1, route_state=DriverRoute.STATE.RUNNING)
        self.assert_route_state(driver_id=2, route_state=DriverRoute.STATE.RUNNING)
        self.assert_route_state(driver_id=3, route_state=DriverRoute.STATE.FINISHED)
        self.assert_route_state(driver_id=4, route_state=DriverRoute.STATE.CREATED)

        self.change_order_status(driver_id=1, order_id=1, order_status=OrderStatus.DELIVERED)
        self.change_order_status(driver_id=2, order_id=3, order_status=OrderStatus.DELIVERED)

        self.assert_optimisation_state(optimisation_id, RouteOptimisation.STATE.RUNNING)
        self.assert_route_state(driver_id=1, route_state=DriverRoute.STATE.RUNNING)
        self.assert_route_state(driver_id=2, route_state=DriverRoute.STATE.FINISHED)
        self.assert_route_state(driver_id=3, route_state=DriverRoute.STATE.FINISHED)
        self.assert_route_state(driver_id=4, route_state=DriverRoute.STATE.CREATED)

        self.unassign_order(2)

        self.assert_optimisation_state(optimisation_id, RouteOptimisation.STATE.RUNNING)
        self.assert_route_state(driver_id=1, route_state=DriverRoute.STATE.FINISHED)
        self.assert_route_state(driver_id=2, route_state=DriverRoute.STATE.FINISHED)
        self.assert_route_state(driver_id=3, route_state=DriverRoute.STATE.FINISHED)
        self.assert_route_state(driver_id=4, route_state=DriverRoute.STATE.CREATED)

        self.delete_order(5)

        self.assert_optimisation_state(optimisation_id, RouteOptimisation.STATE.FINISHED)
        self.assert_route_state(driver_id=1, route_state=DriverRoute.STATE.FINISHED)
        self.assert_route_state(driver_id=2, route_state=DriverRoute.STATE.FINISHED)
        self.assert_route_state(driver_id=3, route_state=DriverRoute.STATE.FINISHED)
        self.assert_route_state(driver_id=4, route_state=DriverRoute.STATE.FINISHED)

    def assert_optimisation_state(self, optimisation_id, state):
        ro = RouteOptimisation.objects.get(id=optimisation_id)
        self.assertEqual(ro.state, state)

    def assert_route_state(self, driver_id, route_state):
        driver = self.settings.drivers_map[driver_id]
        route = driver.routes.all().first()
        if route is None:
            self.assertEqual(DriverRoute.STATE.FINISHED, route_state)
            return
        self.assertEqual(route.state, route_state)

    def change_order_status(self, driver_id, order_id, order_status):
        driver = self.settings.drivers_map[driver_id]
        order = self.settings.orders_map[order_id]
        self.client.force_authenticate(driver)
        resp = self.client.put('{url}{id}/status/'.format(url=self.orders_url, id=order.id), {'status': order_status})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.manager)

    def unassign_order(self, order_id):
        order = self.settings.orders_map[order_id]
        resp = self.client.patch('{url}{id}/'.format(url=self.orders_url, id=order.id),
                               {'status': OrderStatus.NOT_ASSIGNED, 'driver': None})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def delete_order(self, order_id):
        order = self.settings.orders_map[order_id]
        resp = self.client.delete('{url}{id}/'.format(url=self.orders_url, id=order.id))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
