from django.test import override_settings

from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, SubManagerFactory
from driver.utils import WorkStatus
from merchant.factories import SubBrandingFactory
from route_optimisation.const import OPTIMISATION_TYPES
from route_optimisation.tests.web.api_settings import APISettings
from route_optimisation.tests.web.mixins import ORToolsMixin
from route_optimisation.tests.web.optimisation_expectation import OptimisationExpectation
from tasks.models import Order


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class OrderQueueTestCase(ORToolsMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.driver = DriverFactory(merchant=self.merchant, work_status=WorkStatus.WORKING)
        self.client.force_authenticate(self.manager)
        self.sub_branding = SubBrandingFactory(merchant=self.merchant, jobs_export_email='subbrand@test.com')
        self.submanager = SubManagerFactory(merchant=self.merchant, sub_branding=self.sub_branding)

    def test_get_orders_with_queue(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1)
        settings.order(1, '-37.6780953, 145.1290807', deliver_before_time=(20,))
        settings.order(2, '-37.926451, 144.998992', deliver_before_time=(21,))
        settings.order(4, '-35.5418094, 144.9643013', deliver_before_time=(22,))
        settings.order(3, '-37.9202176, 145.2230781', deliver_before_time=(23,))
        expectation = OptimisationExpectation(skipped_orders=0)
        optimisation_id = self.run_optimisation(settings, expectation)

        driver_route_queues = [3, 1, 4, 2]
        delivery_time_queues = [1, 2, 3, 4]

        Order.objects.update(sub_branding=self.sub_branding)

        # queue numbers for sub manager
        self.client.force_authenticate(self.submanager)
        subbrand_orders_resp = self.client.get('/api/web/subbrand/orders/')
        subbrand_orders = subbrand_orders_resp.data['results']
        order_queue_numbers = [order['in_queue'] for order in subbrand_orders]
        self.assertListEqual(order_queue_numbers, driver_route_queues)
        order = Order.objects.get(id=subbrand_orders[0]['server_entity_id'])
        self.assertEqual(order.in_queue, driver_route_queues[0])

        self.client.force_authenticate(self.manager)
        self.remove_optimisation(optimisation_id, unassign=False)

        self.client.force_authenticate(self.submanager)
        # queue numbers for sub manager
        subbrand_orders_resp_without_optimization = self.client.get('/api/web/subbrand/orders/')
        subbrand_orders_without_optimization = subbrand_orders_resp_without_optimization.data['results']
        order_queue_numbers_without_optimization = [
            order['in_queue']
            for order in subbrand_orders_without_optimization
        ]
        self.assertListEqual(order_queue_numbers_without_optimization, delivery_time_queues)
        order = Order.objects.get(id=subbrand_orders[0]['server_entity_id'])
        self.assertEqual(order.in_queue, delivery_time_queues[0])

    def remove_optimisation(self, opt_id, status_code=status.HTTP_204_NO_CONTENT, unassign=None):
        url = '{}{}'.format(self.api_url, opt_id)
        data = {} if unassign is None else {'unassign': unassign}
        resp = self.client.delete(url, data=data)
        self.assertEqual(resp.status_code, status_code)
