from datetime import timedelta

from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

import mock

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import MerchantFactory
from tasks.mixins.order_status import OrderStatus
from tasks.models.orders import Order
from tasks.tests.factories import OrderFactory


class no_check:
    pass


class OrderStatusChangingByManagerTestCase(APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]
    orders_url = '/api/web/dev/orders/'

    @classmethod
    def setUpTestData(cls):
        super(OrderStatusChangingByManagerTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant)

    def setUp(self):
        self.order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.ASSIGNED,
            driver=self.driver
        )
        self.client.force_authenticate(self.manager)

    def change_status_to(self, order_status):
        order_resp = self.client.patch(f'{self.orders_url}{self.order.id}/', {
            'status': order_status,
        })
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(order_resp.data['status'], order_status)

    def test_status_to_not_assign(self):
        self.change_status_to(OrderStatus.NOT_ASSIGNED)
        self.assertFalse(self.driver.order_set.filter(id=self.order.id).exists())
        self.assertTrue(Order.all_objects.filter(id=self.order.id).exists())

    def test_status_to_in_progress(self):
        self.change_status_to(OrderStatus.IN_PROGRESS)
        self.assertTrue(self.driver.order_set.filter(id=self.order.id).exists())

    def test_status_to_completed(self):
        self.change_status_to(OrderStatus.DELIVERED)
        self.assertTrue(self.driver.order_set.filter(id=self.order.id).exists())

    def test_status_to_terminated(self):
        self.change_status_to(OrderStatus.FAILED)
        self.assertTrue(self.driver.order_set.filter(id=self.order.id).exists())


class TimeOfStatusChangingTestCase(APITestCase):
    orders_url = '/api/web/dev/orders/'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant)

    def change_status(self, order, job_status, resp_status, initiator, driver=-1):
        data = {'status': job_status}
        if driver != -1:
            data['driver_id'] = driver
        resp = self.client.patch(f'{self.orders_url}{order.id}/', data)
        self.assertEqual(resp.status_code, resp_status)
        if status.is_success(resp_status):
            self.assertEqual(resp.data['status'], job_status)

    def test_status_change_time_from_not_assigned(self):
        order = OrderFactory(merchant=self.merchant, manager=self.manager, status=OrderStatus.NOT_ASSIGNED)
        self.assertEqual(order.assigned_at, None)
        self.assertEqual(order.started_at, None)
        now = timezone.now()
        assign_time = now + timedelta(minutes=5)
        in_progress_time = now + timedelta(minutes=10)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = assign_time
            self.client.force_authenticate(self.manager)
            self.change_status(order, OrderStatus.ASSIGNED, status.HTTP_200_OK, self.manager, driver=self.driver.id)
        order.refresh_from_db()
        self.assertEqual(order.assigned_at, assign_time)

        not_assign_time = now + timedelta(minutes=15)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = not_assign_time
            self.client.force_authenticate(self.manager)
            self.change_status(order, OrderStatus.NOT_ASSIGNED, status.HTTP_200_OK, self.manager, driver=None)
        order = Order.objects.get(id=order.id)
        self.assertEqual(order.assigned_at, None)

        assign_time = now + timedelta(minutes=20)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = assign_time
            self.client.force_authenticate(self.manager)
            self.change_status(order, OrderStatus.ASSIGNED, status.HTTP_200_OK, self.manager, driver=self.driver.id)
            mock_now.return_value = in_progress_time
            self.change_status(order, OrderStatus.IN_PROGRESS, status.HTTP_200_OK, self.manager)
        order = Order.objects.get(id=order.id)
        self.assertEqual(order.assigned_at, assign_time)
        self.assertEqual(order.started_at, in_progress_time)

    def test_status_change_time_from_assigned(self):
        now = timezone.now()
        creation_time = now + timedelta(minutes=5)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = creation_time
            self.client.force_authenticate(self.manager)
            resp = self.client.post(self.orders_url, {
                'status': OrderStatus.ASSIGNED,
                'driver_id': self.driver.id,
                'deliver': {
                    'customer': {'name': 'Customer'},
                    'address': {
                        'primary_address': {
                            'location': {'lat': 53.23, 'lng': 27.32}
                        },
                    },
                }
            })
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        order = Order.objects.get(id=resp.data['id'])
        self.assertEqual(order.assigned_at, creation_time)

        not_assign_time = now + timedelta(minutes=10)
        assign_time = now + timedelta(minutes=20)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = not_assign_time
            self.client.force_authenticate(self.manager)
            self.change_status(order, OrderStatus.NOT_ASSIGNED, status.HTTP_200_OK, self.manager, driver=None)
        order = Order.objects.get(id=resp.data['id'])
        self.assertEqual(order.assigned_at, None)

        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = assign_time
            self.client.force_authenticate(self.manager)
            self.change_status(order, OrderStatus.ASSIGNED, status.HTTP_200_OK, self.manager, driver=self.driver.id)
        order = Order.objects.get(id=resp.data['id'])
        self.assertEqual(order.assigned_at, assign_time)
