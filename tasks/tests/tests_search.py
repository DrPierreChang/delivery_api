from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import MerchantFactory
from tasks.mixins.order_status import OrderStatus
from tasks.tests.factories import CustomerFactory, OrderFactory, OrderLocationFactory


class OrderSearchTestCase(APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    @classmethod
    def setUpTestData(cls):
        super(OrderSearchTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant)
        cls.order_general_info = {'merchant': cls.merchant,
                                  'manager': cls.manager,
                                  'driver': cls.driver,
                                  'status': OrderStatus.ASSIGNED, }
        cls.location = OrderLocationFactory(location='55.555555,27.777777')

    def setUp(self):
        self.order = OrderFactory(merchant=self.merchant, manager=self.manager, )

    def test_search_by_driver_on_title(self):
        OrderFactory(title='testtitle', **self.order_general_info)
        OrderFactory(**self.order_general_info)

        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/orders/search', data={'q': 'test'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)

    def test_search_by_driver_on_order_id(self):
        order = OrderFactory(**self.order_general_info)

        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/orders/search', data={'q': order.order_id})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)

    def test_search_by_driver_on_customer_name(self):
        customer = CustomerFactory(name='TestCustomer')
        OrderFactory(customer=customer, **self.order_general_info)

        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/orders/search', data={'q': 'test'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)

    def test_search_by_driver_on_deliver_location_address(self):
        location = OrderLocationFactory(address='test street', location='55.555555,27.777778')
        OrderFactory(deliver_address=location, **self.order_general_info)

        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/orders/search', data={'q': 'test'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)

    def test_search_by_driver_on_deliver_location_latlng(self):
        OrderFactory(deliver_address=self.location, **self.order_general_info)

        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/orders/search', data={'q': '7777'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)

    def test_short_query(self):
        OrderFactory(deliver_address=self.location, title='wwwtest', **self.order_general_info)

        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/orders/search', data={'q': 'w'})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)
