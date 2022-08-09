from factory.fuzzy import FuzzyChoice

from driver.factories import DriverLocationFactory
from tasks.mixins.order_status import OrderStatus
from tasks.models.orders import Order
from tasks.tests.factories import OrderFactory

from ..base_test_cases import BaseOrderTestCase


class OrderTestCase(BaseOrderTestCase):
    subbrands_url = '/api/web/dev/subbrand/orders/'
    one_subbrand_url = '/api/web/dev/subbrand/orders/{}/'.format

    @classmethod
    def setUpTestData(cls):
        super(OrderTestCase, cls).setUpTestData()
        loc = DriverLocationFactory(member=cls.driver)
        cls.driver.last_location = loc
        cls.driver.save()

    def setUp(self):
        self.order = self.create_default_order(sub_branding=self.sub_branding)

    def test_submanager_orders_list_getting(self):
        OrderFactory.create_batch(
            size=10,
            merchant=self.merchant,
            manager=self.manager,
            sub_branding=self.sub_branding,
            status=OrderStatus.ASSIGNED,
        )
        self.client.force_authenticate(self.submanager)
        resp = self.client.get(self.subbrands_url)
        resp_json_data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(resp_json_data.get('count'), 0)

    def test_many_submanager_orders_list_getting(self):
        OrderFactory.create_batch(
            size=20,
            merchant=self.merchant,
            manager=self.manager,
            sub_branding=self.sub_branding,
            status=FuzzyChoice(Order._status_dict.values()).fuzz()
        )
        self.client.force_authenticate(self.submanager)
        resp = self.client.get(self.subbrands_url)
        orders_count = Order.objects.exclude(status=OrderStatus.NOT_ASSIGNED)
        orders_count = orders_count.filter(sub_branding=self.sub_branding).count()
        self.assertEqual(resp.data['count'], orders_count)

    def test_not_assigned_order_getting_by_submanager(self):
        self.client.force_authenticate(self.submanager)
        resp = self.client.get(self.one_subbrand_url(self.order.id))
        self.assertEqual(resp.status_code, 404)

    def test_assigned_order_getting_by_submanager(self):
        order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            driver=self.driver,
            status=Order.ASSIGNED,
            customer=self.customer,
            sub_branding=self.sub_branding,
        )
        self.client.force_authenticate(self.submanager)
        resp = self.client.get(self.one_subbrand_url(order.id))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get(self.one_subbrand_url(order.id) + 'path/')
        self.assertEqual(resp.status_code, 200)
