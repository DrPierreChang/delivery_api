import copy
from datetime import timedelta

from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

import mock

from base.factories import DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from merchant.models import Merchant
from notification.tests.mixins import NotificationTestMixin
from radaro_utils.helpers import to_timestamp
from reporting.models import Event
from tasks.mixins.order_status import OrderStatus
from tasks.models.orders import Order
from tasks.tests.factories import OrderFactory


def make_data(offline_status, fields=None, location_field=None):
    fields = fields or ['status', 'offline_happened_at'] + ([location_field] if location_field else [])
    return dict(zip(fields, offline_status), offline_happened_at=to_timestamp(offline_status[1]))


class OfflineMixin(object):
    @classmethod
    def setUpTestData(cls):
        super(OfflineMixin, cls).setUpTestData()
        cls.merchant = MerchantFactory(use_pick_up_status=True, geofence_settings=Merchant.UPON_ENTERING)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)

        cls.order = OrderFactory(
            merchant=cls.merchant,
            manager=cls.manager,
        )

        cls.fake_now = timezone.now() - timedelta(hours=2)
        cls.offline_statuses = [
            [OrderStatus.PICK_UP, cls.fake_now + timedelta(minutes=5), {'location': '53.906736,27.530501'}],
            [OrderStatus.IN_PROGRESS, cls.fake_now + timedelta(minutes=10), {'location': '53.906756,27.530601'}],
            [OrderStatus.DELIVERED, cls.fake_now + timedelta(minutes=60), {'location': '53.918772,27.526775'}],
        ]

    def setUp(self):
        self.client.force_authenticate(self.manager)

        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = self.fake_now
            resp = self.client.patch('/api/orders/%s/' % self.order.order_id, {
                'driver': self.driver.id,
                'status': OrderStatus.ASSIGNED,
            })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()['driver'], self.driver.id)
            self.assertEqual(resp.json()['status'], OrderStatus.ASSIGNED)

    def assert_event(self, field, value, happened_at=None, has_event=None):
        status_change_events = self.order.events.all().filter(event=Event.CHANGED, field=field, new_value=value)
        if has_event is not None:
            self.assertEqual(status_change_events.exists(), has_event)
        if happened_at is not None:
            self.assertTrue(status_change_events.filter(happened_at=happened_at).exists())

    def assert_order_offline(self, is_offline):
        self.assertTrue(Order.objects.all().filter(id=self.order.id, changed_in_offline=is_offline).exists())


class OrderOfflineTestCase(OfflineMixin, APITestCase):

    def test_successful_change_statuses(self):
        self.client.force_authenticate(self.driver)
        resp = self.client.put('/api/orders/%s/status/' % self.order.order_id,
                               make_data(self.offline_statuses[1], location_field='starting_point'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assert_status_event(OrderStatus.IN_PROGRESS, has_event=True, happened_at=self.offline_statuses[1][1])
        self.assert_job_start(self.offline_statuses[1][1], location_string=self.offline_statuses[1][2].get('location'))
        resp = self.client.put('/api/orders/%s/status/' % self.order.order_id,
                               make_data(self.offline_statuses[2], location_field='ending_point'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assert_status_event(OrderStatus.DELIVERED, has_event=True, happened_at=self.offline_statuses[2][1])
        self.assert_order_offline(True)

    def test_use_pickup_status_offline(self):
        self.client.force_authenticate(self.driver)
        resp = self.client.put('/api/orders/%s/status/' % self.order.order_id,
                               make_data(self.offline_statuses[0], location_field='starting_point'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assert_status_event(OrderStatus.PICK_UP, has_event=True, happened_at=self.offline_statuses[0][1])
        self.assert_job_start(self.offline_statuses[0][1], location_string=self.offline_statuses[0][2].get('location'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.starting_point.location, self.offline_statuses[0][2]['location'])

        resp = self.client.put('/api/orders/%s/status/' % self.order.order_id,
                               make_data(self.offline_statuses[1], location_field='starting_point'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.starting_point.location, self.offline_statuses[0][2]['location'])
        self.assert_status_event(OrderStatus.IN_PROGRESS, has_event=True, happened_at=self.offline_statuses[1][1])
        self.assert_order_offline(True)

    def test_successful_completed_status_change(self):
        in_progress_time = self.fake_now + timedelta(minutes=30)

        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = in_progress_time
            resp = self.client.patch('/api/orders/%s/' % self.order.order_id, {
                'driver': self.driver.id,
                'status': OrderStatus.IN_PROGRESS,
            })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()['status'], OrderStatus.IN_PROGRESS)

        self.client.force_authenticate(self.driver)
        resp = self.client.put('/api/orders/%s/status/' % self.order.order_id,
                               make_data(self.offline_statuses[1], location_field='starting_point'))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', resp.json()['errors'])
        self.assert_status_event(OrderStatus.IN_PROGRESS, has_event=True, happened_at=in_progress_time)
        resp = self.client.put('/api/orders/%s/status/' % self.order.order_id,
                               make_data(self.offline_statuses[2], location_field='ending_point'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assert_status_event(OrderStatus.DELIVERED, has_event=True, happened_at=self.offline_statuses[2][1])
        self.assert_order_offline(True)

    def test_unsuccessful_status_change(self):
        in_progress_time, delivered_time = self.fake_now + timedelta(minutes=30), self.fake_now + timedelta(minutes=120)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = in_progress_time
            resp = self.client.patch('/api/orders/%s/' % self.order.order_id, {
                'driver': self.driver.id,
                'status': OrderStatus.IN_PROGRESS,
            })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()['status'], OrderStatus.IN_PROGRESS)

            mock_now.return_value = delivered_time
            resp = self.client.patch('/api/orders/%s/' % self.order.order_id, {
                'driver': self.driver.id,
                'status': OrderStatus.DELIVERED,
            })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()['status'], OrderStatus.DELIVERED)

        self.client.force_authenticate(self.driver)
        resp = self.client.put('/api/orders/%s/status/' % self.order.order_id,
                               make_data(self.offline_statuses[1], location_field='starting_point'))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', resp.json()['errors'])
        self.assert_status_event(OrderStatus.IN_PROGRESS, has_event=True, happened_at=in_progress_time)
        resp = self.client.put('/api/orders/%s/status/' % self.order.order_id,
                               make_data(self.offline_statuses[2], location_field='ending_point'))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', resp.json()['errors'])
        self.assert_status_event(OrderStatus.DELIVERED, has_event=True, happened_at=delivered_time)
        self.assert_order_offline(False)

    def test_wrong_time(self):
        self.client.force_authenticate(self.driver)
        for offline_status, location_field in zip(copy.copy(self.offline_statuses[1:]),
                                                  ['starting_point', 'ending_point']):
            offline_status[1] = self.fake_now - timedelta(minutes=1)
            resp = self.client.put('/api/orders/%s/status/' % self.order.order_id,
                                   make_data(offline_status, location_field=location_field))
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertContains(resp, 'Time mismatching.', status_code=status.HTTP_400_BAD_REQUEST)
            self.assert_status_event(OrderStatus.IN_PROGRESS, has_event=False)
        self.assert_order_offline(False)

    def test_not_changed_in_offline(self):
        self.client.force_authenticate(self.driver)

        for offline_status in [OrderStatus.IN_PROGRESS, OrderStatus.DELIVERED]:
            with mock.patch('django.utils.timezone.now') as mock_now:
                mock_now.return_value = self.fake_now + timedelta(minutes=2)
                order_resp = self.client.put('/api/orders/%s/status' % self.order.order_id, {
                    'status': offline_status,
                })
                self.assertEqual(order_resp.status_code, status.HTTP_200_OK)

        self.assert_order_offline(False)

    def test_not_passed_location_for_in_progress(self):
        self.client.force_authenticate(self.driver)
        resp = self.client.put('/api/orders/%s/status/' % self.order.order_id,
                               make_data(self.offline_statuses[1][:2]))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', resp.json()['errors'])
        self.assert_status_event(OrderStatus.IN_PROGRESS, has_event=False)
        self.assert_order_offline(False)

    def test_not_assigned(self):
        self.client.force_authenticate(self.driver)
        resp = self.client.put('/api/orders/%s/status/' % self.order.order_id,
                               make_data([OrderStatus.NOT_ASSIGNED, self.fake_now + timedelta(minutes=1)]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assert_status_event(OrderStatus.NOT_ASSIGNED, has_event=True)
        self.assert_order_offline(True)

    def assert_job_start(self, start_time, location_string):
        order = Order.objects.select_related('starting_point').get(id=self.order.id)
        self.assertEqual(str(order.starting_point), location_string)
        self.assertEqual(order.started_at, start_time)

    def assert_status_event(self, order_status, happened_at=None, has_event=None):
        self.assert_event('status', order_status, happened_at, has_event)


class GeofenceOfflineTestCase(NotificationTestMixin, OfflineMixin, APITestCase):
    def test_geofence(self):
        in_progress_time, offline_happened_at = self.fake_now + timedelta(minutes=1),\
                                                self.fake_now + timedelta(minutes=20)
        self.client.force_authenticate(self.driver)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = in_progress_time
            self.client.put('/api/orders/%s/status/' % self.order.order_id, {
                'status': OrderStatus.IN_PROGRESS,
            })
        resp = self.client.put('/api/orders/%s/geofence/' % self.order.order_id, {
            'geofence_entered': True,
            'offline_happened_at': to_timestamp(offline_happened_at),
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assert_geofence_event(True, happened_at=offline_happened_at)
        self.assert_order_offline(True)

    def test_geofence_not_offline(self):
        self.client.force_authenticate(self.driver)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = self.fake_now + timedelta(minutes=2)
            self.client.put('/api/orders/%s/status/' % self.order.order_id, {
                'status': OrderStatus.IN_PROGRESS,
            })
            resp = self.client.put('/api/orders/%s/geofence/' % self.order.order_id, {
                'geofence_entered': True,
            })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assert_geofence_event(True, happened_at=self.fake_now + timedelta(minutes=2))
        self.assert_order_offline(False)

    def test_geofence_entered_wrong_time(self):
        in_progress_time = self.fake_now + timedelta(minutes=30)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = in_progress_time
            resp = self.client.patch('/api/orders/%s/' % self.order.order_id, {
                'driver': self.driver.id,
                'status': OrderStatus.IN_PROGRESS,
            })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()['status'], OrderStatus.IN_PROGRESS)

        self.client.force_authenticate(self.driver)
        resp = self.client.put('/api/orders/%s/geofence/' % self.order.order_id, {
            'geofence_entered': True,
            'offline_happened_at': to_timestamp(in_progress_time - timedelta(minutes=1)),
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assert_order_offline(False)

    def test_geofence_exit_wrong_time(self):
        in_progress_time = self.fake_now + timedelta(minutes=30)
        geofence_entered = in_progress_time + timedelta(minutes=5)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = in_progress_time
            resp = self.client.patch('/api/orders/%s/' % self.order.order_id, {
                'driver': self.driver.id,
                'status': OrderStatus.IN_PROGRESS,
            })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()['status'], OrderStatus.IN_PROGRESS)

        self.client.force_authenticate(self.driver)
        resp = self.client.put('/api/orders/%s/geofence/' % self.order.order_id, {
            'geofence_entered': True,
            'offline_happened_at': to_timestamp(geofence_entered),
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.put('/api/orders/%s/geofence/' % self.order.order_id, {
            'geofence_entered': False,
            'offline_happened_at': to_timestamp(geofence_entered - timedelta(minutes=1)),
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        self.assert_order_offline(True)

    def assert_geofence_event(self, value, happened_at=None, has_event=None):
        self.assert_event('geofence_entered', value, happened_at, has_event)

    @NotificationTestMixin.make_push_available
    def test_notification_about_jobs_completed_geofence(self):
        self.client.force_authenticate(self.driver)
        with self.mock_send_versioned_push() as send_push_mock:
            self.client.put('/api/orders/%s/status/' % self.order.order_id, {
                'status': OrderStatus.IN_PROGRESS,
            })
            resp = self.client.put('/api/orders/%s/geofence/' % self.order.order_id, {
                'geofence_entered': True,
            })
            self.assertTrue(send_push_mock.called)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @NotificationTestMixin.make_push_available
    def test_notification_not_sent_about_jobs_completed_geofence(self):
        in_progress_time, offline_happened_at = self.fake_now + timedelta(minutes=1),\
                                                self.fake_now + timedelta(minutes=20)
        self.client.force_authenticate(self.driver)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = in_progress_time
            self.client.put('/api/orders/%s/status/' % self.order.order_id, {
                'status': OrderStatus.IN_PROGRESS,
            })

        with self.mock_send_versioned_push() as send_push_mock:
            self.client.put('/api/orders/%s/status/' % self.order.order_id, {
                'status': OrderStatus.IN_PROGRESS,
            })
            resp = self.client.put('/api/orders/%s/geofence/' % self.order.order_id, {
                'geofence_entered': True,
                'offline_happened_at': to_timestamp(offline_happened_at),
            })
            self.assertFalse(send_push_mock.called)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assert_geofence_event(True, happened_at=offline_happened_at)
            self.assert_order_offline(True)
