from datetime import timedelta

from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

import mock

from base.factories import DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from merchant.models import Merchant
from radaro_utils.helpers import to_timestamp
from tasks.mixins.order_status import OrderStatus
from tasks.models.orders import Order
from tasks.tests.factories import OrderFactory


class OrderCompletionWithGeofenceTestCase(APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    def test_completion_with_geofence_upon_entering(self):
        merchant = MerchantFactory(geofence_settings=Merchant.UPON_ENTERING)
        manager = ManagerFactory(merchant=merchant)
        driver = DriverFactory(merchant=merchant, work_status=WorkStatus.WORKING)
        order = OrderFactory(merchant=merchant,
                             status=OrderStatus.IN_PROGRESS,
                             driver=driver,
                             manager=manager)

        self.client.force_authenticate(driver)

        resp = self.client.patch('/api/orders/%s/geofence/' % order.order_id, data={'geofence_entered': True})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Order.objects.get(id=order.id).status, OrderStatus.DELIVERED)

    def test_completion_with_geofence_upon_exiting(self):
        merchant = MerchantFactory(geofence_settings=Merchant.UPON_EXITING)
        manager = ManagerFactory(merchant=merchant)
        driver = DriverFactory(merchant=merchant, work_status=WorkStatus.WORKING)
        order = OrderFactory(merchant=merchant,
                             status=OrderStatus.IN_PROGRESS,
                             driver=driver,
                             manager=manager)

        self.client.force_authenticate(driver)
        self.client.patch('/api/orders/%s/geofence/' % order.order_id, data={'geofence_entered': True})

        resp = self.client.patch('/api/orders/%s/geofence/' % order.order_id, data={'geofence_entered': False})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Order.objects.get(id=order.id).status, OrderStatus.DELIVERED)


class PickupGeofenceTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(use_pick_up_status=True)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)
        cls.fake_now = timezone.now() - timedelta(hours=2)

    def setUp(self):
        self.client.force_authenticate(self.manager)
        self.order = OrderFactory(merchant=self.merchant, manager=self.manager)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = self.fake_now
            self.client.patch('/api/orders/%s/' % self.order.order_id, {
                'driver': self.driver.id,
                'status': OrderStatus.ASSIGNED,
            })

    def test_pickup_geofence_entering(self):
        self.client.force_authenticate(self.driver)
        self.client.put('/api/v2/orders/{}/status/'.format(self.order.id), {'status': 'pickup'})
        resp = self.client.put('/api/v2/orders/{}/geofence/'.format(self.order.id), {'geofence_entered': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Order.objects.get(id=self.order.id).pickup_geofence_entered, True)

    def test_time_at_pickup(self):
        pickup_geofence_entered_time, picked_up_time = self.fake_now + timedelta(minutes=2), \
            self.fake_now + timedelta(minutes=20)
        expected_time_at_pickup = picked_up_time - pickup_geofence_entered_time + timedelta(minutes=1)
        self.client.force_authenticate(self.driver)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = self.fake_now + timedelta(minutes=1)
            self.client.put('/api/v2/orders/{}/status/'.format(self.order.id), {'status': 'pickup'})

        self.client.put('/api/v2/orders/{}/geofence/'.format(self.order.id),
                        {'geofence_entered': True, 'offline_happened_at': to_timestamp(pickup_geofence_entered_time)})
        self.client.put('/api/v2/orders/{}/status/'.format(self.order.id),
                        {'status': 'picked_up', 'offline_happened_at': to_timestamp(picked_up_time)})

        self.assertEqual(Order.objects.get(id=self.order.id).time_at_pickup, expected_time_at_pickup)
