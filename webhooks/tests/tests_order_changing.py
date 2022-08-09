from datetime import datetime, timedelta

from rest_framework import status

import pytz

from base.factories import DriverFactory
from base.utils import get_fuzzy_location
from merchant.factories import MerchantFactory
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order
from tasks.tests.factories import OrderLocationFactory

from .base_test_cases import APIKeyTestCase


class ExternalOrderInfoChanging(APIKeyTestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    @classmethod
    def setUpTestData(cls):
        super(ExternalOrderInfoChanging, cls).setUpTestData()
        cls.driver = DriverFactory(merchant=cls.merchant)
        cls.assigned_data = {
            'status': OrderStatus.ASSIGNED,
            'driver': cls.driver.member_id,
        }
        cls.pick_up_data = {'status': OrderStatus.PICK_UP, }
        cls.in_progress_data = {'status': OrderStatus.IN_PROGRESS, }
        cls.completed_data = {'status': OrderStatus.DELIVERED, }
        cls.delivery_interval = (datetime.now(cls.merchant.timezone) + timedelta(days=1)).replace(hour=1)
        cls.delivery_interval_data = {
                "deliver_before": str((cls.delivery_interval + timedelta(hours=1)).astimezone(pytz.UTC).isoformat()),
                "deliver_after": str(cls.delivery_interval.astimezone(pytz.UTC).isoformat()),
            }
        cls.data = {'title': 'new_title', }

    def setUp(self):
        self.external_id = 'test-ext-job'
        data = {
            'external_id': self.external_id,
            'customer': {
                'name': 'new customer'
            },
            'deliver_address': {
                'location': get_fuzzy_location(),
            }
        }
        self.client.post('/api/webhooks/jobs/?key=%s' % self.apikey.key, data=data)
        self.order = Order.objects.get(external_job__external_id=self.external_id)

    def test_change_status_to_assigned(self):
        resp = self.client.patch('/api/webhooks/jobs/%s/?key=%s' % (self.external_id, self.apikey.key),
                                 data=self.assigned_data)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], OrderStatus.ASSIGNED)
        self.assertEqual(resp.data['driver'], self.driver.member_id)

    def test_change_status_to_assigned_without_driver(self):
        resp = self.client.patch('/api/webhooks/jobs/%s/?key=%s' % (self.external_id, self.apikey.key),
                                 data={'status': 'assigned'})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_driver_without_status(self):
        resp = self.client.patch('/api/webhooks/jobs/%s/?key=%s' % (self.external_id, self.apikey.key),
                                 data={'driver': self.driver.member_id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(resp.json()['status'], self.order.status)

    def test_add_driver_without_status_to_in_progress_job(self):
        self.order.driver = self.driver
        self.order.status = OrderStatus.IN_PROGRESS
        self.order.save()

        resp = self.client.patch('/api/webhooks/jobs/%s/?key=%s' % (self.external_id, self.apikey.key),
                                 data={'driver': self.driver.member_id})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_status_to_assigned_with_not_own_driver(self):
        other_driver = DriverFactory(merchant=MerchantFactory())
        resp = self.client.patch('/api/webhooks/jobs/%s/?key=%s' % (self.external_id, self.apikey.key),
                                 data={'status': 'assigned', 'driver': other_driver.member_id})

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cant_use_pick_up_status(self):
        self.order.driver = self.driver
        self.order.status = OrderStatus.ASSIGNED
        self.order.pickup_address = OrderLocationFactory()
        self.order.save()
        resp = self.client.patch('/api/webhooks/jobs/%s/?key=%s' % (self.external_id, self.apikey.key),
                                 data=self.pick_up_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_use_pick_up_status(self):
        self.order.driver = self.driver
        self.order.status = OrderStatus.ASSIGNED
        self.order.save()
        self.merchant.use_pick_up_status = True
        self.merchant.save()

        resp = self.client.patch('/api/webhooks/jobs/%s/?key=%s' % (self.external_id, self.apikey.key),
                                 data=self.pick_up_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.order.pickup_address = OrderLocationFactory()
        self.order.save()
        resp = self.client.patch('/api/webhooks/jobs/%s/?key=%s' % (self.external_id, self.apikey.key),
                                 data=self.pick_up_data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], OrderStatus.PICK_UP)

        resp = self.client.patch('/api/webhooks/jobs/%s/?key=%s' % (self.external_id, self.apikey.key),
                                 data=self.in_progress_data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], OrderStatus.IN_PROGRESS)
        self.merchant.use_pick_up_status = False
        self.merchant.save()

    def test_change_status_to_in_progress(self):
        self.order.driver = self.driver
        self.order.status = OrderStatus.ASSIGNED
        self.order.save()

        resp = self.client.patch('/api/webhooks/jobs/%s/?key=%s' % (self.external_id, self.apikey.key),
                                 data=self.in_progress_data)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], OrderStatus.IN_PROGRESS)

    def test_change_status_to_completed(self):
        self.order.driver = self.driver
        self.order.status = OrderStatus.IN_PROGRESS
        self.order.save()

        resp = self.client.patch('/api/webhooks/jobs/%s/?key=%s' % (self.external_id, self.apikey.key),
                                 data=self.completed_data)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], OrderStatus.DELIVERED)

    def test_update_not_assigned_order_info(self):
        resp = self.client.patch('/api/webhooks/jobs/%s/?key=%s' % (self.external_id, self.apikey.key), data=self.data)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(self.data, dict(filter(lambda item: item[0] in self.data.keys(), resp.json().items())))

    def test_update_delivery_interval(self):
        resp = self.client.patch(
            '/api/webhooks/jobs/%s/?key=%s' % (self.external_id, self.apikey.key), data=self.delivery_interval_data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        order = Order.objects.get(external_job__external_id=self.external_id)
        self.assertEqual(self.delivery_interval_data['deliver_after'], order.deliver_after.isoformat())
        self.assertEqual(self.delivery_interval_data['deliver_before'], order.deliver_before.isoformat())

    def test_update_assigned_order_info(self):
        self.order.driver = self.driver
        self.order.status = OrderStatus.ASSIGNED
        self.order.save()

        resp = self.client.patch('/api/webhooks/jobs/%s/?key=%s' % (self.external_id, self.apikey.key), data=self.data)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(self.data, dict(filter(lambda item: item[0] in self.data.keys(), resp.json().items())))

    def test_update_in_progress_order_info(self):
        self.order.driver = self.driver
        self.order.status = OrderStatus.IN_PROGRESS
        self.order.save()

        resp = self.client.patch('/api/webhooks/jobs/%s/?key=%s' % (self.external_id, self.apikey.key), data=self.data)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
