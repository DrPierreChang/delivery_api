from datetime import datetime as dt
from datetime import timedelta

from django.utils import timezone

from rest_framework.test import APITestCase

import mock

from base.factories import DriverFactory, ManagerFactory
from base.utils import get_fuzzy_location, get_v2_fuzzy_location
from merchant.factories import MerchantFactory
from tasks.mixins.order_status import OrderStatus
from tasks.models.orders import Order
from webhooks.models import MerchantWebhookEvent


class OrderDistanceTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.merchant = MerchantFactory(driver_can_create_job=True, in_app_jobs_assignment=True)
        cls.driver = DriverFactory(merchant=cls.merchant)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.merchant.webhook_url = ['https://example.com/']
        cls.merchant.save()

    def _send_location(self, time):
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = time
            self.client.post('/api/drivers/me/locations', data={
                "location": get_fuzzy_location(),
                'timestamp': timezone.now().timestamp()
            })

    def test_distance_calculation(self):
        starting_time = dt.combine(
            dt.now(tz=self.merchant.timezone).date(),
            dt.min.time(),
        ).replace(tzinfo=self.merchant.timezone)

        self.client.force_authenticate(self.driver)

        self._send_location(starting_time + timedelta(minutes=30))

        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = starting_time + timedelta(hours=1)
            order_data = {
                'customer': {'name': 'Test Customer', },
                'deliver_address': {'location': get_v2_fuzzy_location(), },
                'deliver_before': starting_time + timedelta(days=1),
            }
            self.client.post('/api/v2/orders/', data=order_data)

        order = Order.objects.last()
        self._send_location(starting_time + timedelta(hours=2))

        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = starting_time + timedelta(hours=3)
            self.client.put('/api/v2/orders/%s/status/' % order.id, {
                'driver': self.driver.id,
                'status': OrderStatus.ASSIGNED,
            })

        self._send_location(starting_time + timedelta(hours=4))

        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = starting_time + timedelta(hours=5)
            self.client.put('/api/v2/orders/%s/status/' % order.id, {
                'status': OrderStatus.IN_PROGRESS,
            })

        self._send_location(starting_time + timedelta(hours=5))
        self._send_location(starting_time + timedelta(hours=6))
        self._send_location(starting_time + timedelta(hours=7))
        order.refresh_from_db()
        old_distance = order.order_distance

        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = starting_time + timedelta(hours=7)
            self.client.put('/api/v2/orders/%s/status/' % order.id, {
                'status': OrderStatus.FAILED,
            })

        order = Order.objects.last()
        event = MerchantWebhookEvent.objects.order_by('pk').last()

        self.assertIsNotNone(order.duration)
        self.assertEqual(order.order_distance, event.request_data['order_info']['order_distance'])
