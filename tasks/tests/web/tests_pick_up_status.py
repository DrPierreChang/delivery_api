from datetime import timedelta

from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

import mock

from base.factories import DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from tasks.models import Order, OrderStatus
from tasks.tests.factories import OrderFactory


class PickUpStatusTestCase(APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    @classmethod
    def setUpTestData(cls):
        super(PickUpStatusTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory(use_pick_up_status=True, driver_can_create_job=True)
        cls.merchant_no_pickup = MerchantFactory(use_pick_up_status=False)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.manager_no_pickup = ManagerFactory(merchant=cls.merchant_no_pickup)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)
        cls.driver_no_pickup = DriverFactory(merchant=cls.merchant_no_pickup, work_status=WorkStatus.WORKING)
        cls.job_data = {
            'pickup': {
                'address': {
                    'primary_address': {
                        'address': 'Eaton Gate, 2, UK',
                        'location': {
                            'lat': 51.5938516,
                            'lng': -0.1167399
                        },
                    },
                    'secondary_address': 'Eaton Gate, 2 Sloane Square',
                },
            },
            'deliver': {
                'customer': {'name': 'Test Customer'},
                'address': {
                    'primary_address': {
                        'address': 'Eaton Gate, UK',
                        'location': {
                            'lat': 51.4938516,
                            'lng': -0.1567399
                        },
                    },
                    'secondary_address': 'Eaton Gate, Sloane Square',
                },
            },
        }

    def setUp(self):
        super(PickUpStatusTestCase, self).setUp()
        self.order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.ASSIGNED,
            driver=self.driver
        )

    def change_status(self, order, job_status, resp_status, initiator, driver=None):
        resp = self.client.patch(f'/api/web/dev/orders/{order.id}/', {'status': job_status})
        self.assertEqual(resp.status_code, resp_status)
        if status.is_success(resp_status):
            self.assertEqual(resp.data['status'], job_status)

    def test_change_status_to_pick_up_by_manager(self):
        self.client.force_authenticate(self.manager)
        self.change_status(self.order, OrderStatus.PICK_UP, status.HTTP_200_OK, self.manager)

    def test_cant_change_status_to_pick_up(self):
        order = OrderFactory(
            merchant=self.merchant_no_pickup,
            manager=self.manager_no_pickup,
            status=OrderStatus.ASSIGNED,
            driver=self.driver_no_pickup
        )
        self.client.force_authenticate(self.manager_no_pickup)
        self.change_status(order, OrderStatus.PICK_UP, status.HTTP_400_BAD_REQUEST, self.manager_no_pickup)

    def test_use_pickup_only_with_pickup_address(self):
        order_no_pickup_address = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.ASSIGNED,
            driver=self.driver,
            pickup_address=None,
        )
        self.client.force_authenticate(self.manager)
        self.change_status(order_no_pickup_address, OrderStatus.PICK_UP, status.HTTP_400_BAD_REQUEST, self.driver)
        resp = self.client.patch(
            f'/api/web/dev/orders/{order_no_pickup_address.id}/',
            {'pickup': {'address': {'primary_address': {'location': {'lat': 23.123, 'lng': 23.123}}}}}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_dont_use_pickup_status(self):
        order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.NOT_ASSIGNED,
            driver=None,
        )
        self.client.force_authenticate(self.manager)
        resp = self.client.patch(
            f'/api/web/dev/orders/{order.id}/',
            {'status': OrderStatus.ASSIGNED, 'driver_id': self.driver.id}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_can_delete_pickup_address(self):
        self.assertIsNotNone(self.order.pickup_address)
        self.client.force_authenticate(self.manager)
        resp = self.client.patch(f'/api/web/dev/orders/{self.order.id}/', {'pickup': {'address': None}})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.pickup_address)

    def test_calculate_picked_up_time(self):
        self.client.force_authenticate(self.manager)
        now = timezone.now()
        times = [(OrderStatus.PICK_UP, now + timedelta(minutes=10)),
                 (OrderStatus.IN_PROGRESS, now + timedelta(minutes=20))]

        with mock.patch('django.utils.timezone.now') as mock_now:
            for to_status, change_time in times:
                mock_now.return_value = change_time
                self.change_status(self.order, to_status, status.HTTP_200_OK, self.driver)
        self.order.refresh_from_db()
        self.assertEqual(self.order.started_at, times[0][1])
        self.assertEqual(self.order.picked_up_at, times[1][1])

    def test_create_job_with_pickup_address(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.post('/api/web/dev/orders/', data=self.job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.get(order_id=resp.data['order_id'])
        self.assertIsNotNone(order.pickup_address)
