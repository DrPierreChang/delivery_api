from base64 import b64encode
from datetime import timedelta
from io import BytesIO

from django.test.utils import override_settings
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

import mock
from PIL import Image

from base.factories import DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory, SkillSetFactory
from notification.tests.mixins import NotificationTestMixin
from tasks.mixins.order_status import OrderStatus
from tasks.models.orders import Order
from tasks.tests.factories import OrderFactory


class no_check:
    pass


TEST_UNALLOCATED_ORDER_INTERVAL = 7 * 101


class OrderStatusChangingByManagerTestCase(NotificationTestMixin, APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    @classmethod
    def setUpTestData(cls):
        super(OrderStatusChangingByManagerTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory(enable_skill_sets=True)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant)
        cls.skill_set = SkillSetFactory(merchant=cls.merchant)
        cls.driver.skill_sets.add(cls.skill_set)

    def setUp(self):
        self.order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.ASSIGNED,
            driver=self.driver,
            deliver_before=timezone.now() + timedelta(days=1),
        )
        self.order.skill_sets.add(self.skill_set)
        self.client.force_authenticate(self.manager)

    def change_status_to(self, order_status, order=None, **kwargs):
        order = order or self.order
        order_resp = self.client.patch('/api/orders/%s/' % order.order_id, {
            'status': order_status,
            **kwargs,
        })
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(order_resp.data['status'], order_status)

    @override_settings(UNALLOCATED_ORDER_INTERVAL=TEST_UNALLOCATED_ORDER_INTERVAL)
    def test_status_to_assign(self):
        self.merchant.in_app_jobs_assignment = True
        self.merchant.notify_of_not_assigned_orders = True
        self.merchant.save()

        order_2 = OrderFactory(merchant=self.merchant, manager=self.manager,
                               status=OrderStatus.NOT_ASSIGNED, driver=None)
        order_2.skill_sets.add(self.skill_set)
        driver_2 = DriverFactory(merchant=self.merchant)
        driver_2.skill_sets.add(self.skill_set)

        with self.mock_send_versioned_push() as send_push_mock:
            self.change_status_to(order=order_2, order_status=OrderStatus.ASSIGNED, driver=self.driver.id)
            # This merchant has 2 drivers
            # Push message about not available job is sent to both drivers in case of status change by manager
            self.assertEqual(send_push_mock.call_count, 2)

        self.assertTrue(Order.all_objects.filter(id=self.order.id).exists())

    def test_status_to_not_assign(self):
        self.merchant.in_app_jobs_assignment = True
        self.merchant.notify_of_not_assigned_orders = True
        self.merchant.save()

        driver_2 = DriverFactory(merchant=self.merchant)
        driver_2.skill_sets.add(self.skill_set)
        self.merchant.required_skill_sets_for_notify_orders.add(self.skill_set)

        with self.mock_send_versioned_push() as send_push_mock:
            self.change_status_to(OrderStatus.NOT_ASSIGNED)
            # This merchant has 2 driver.
            # The old driver is sent a push that the job is no longer his
            # The new driver is sent a push about the available new job
            self.assertEqual(send_push_mock.call_count, 2)
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


class OrderStatusChangingByDriverTestCase(APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    @classmethod
    def setUpTestData(cls):
        super(OrderStatusChangingByDriverTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory()
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)

        cls.merchant_with_enabled_confirmation = MerchantFactory(enable_delivery_confirmation=True)
        cls.other_driver = DriverFactory(merchant=cls.merchant_with_enabled_confirmation, work_status=WorkStatus.WORKING)

    def setUp(self):
        self.order = OrderFactory(
            merchant=self.merchant,
            status=OrderStatus.ASSIGNED,
            driver=self.driver
        )
        self.client.force_authenticate(self.driver)

    def change_status_to(self, order_status):
        order_resp = self.client.put('/api/orders/%s/status' % self.order.order_id, {
            'status': order_status,
        })
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(order_resp.data['status'], order_status)

    def test_status_to_in_progress(self):
        self.change_status_to(OrderStatus.IN_PROGRESS)
        self.assertTrue(self.driver.order_set.filter(id=self.order.id).exists())

    def test_status_to_terminated(self):
        self.change_status_to(OrderStatus.FAILED)
        self.assertTrue(self.driver.order_set.filter(id=self.order.id).exists())

    def test_status_to_completed_without_enabled_confirming_by_driver(self):
        self.change_status_to(OrderStatus.DELIVERED)
        self.assertTrue(self.driver.order_set.filter(id=self.order.id).exists())

    def test_status_to_completed_with_enabled_confirming_by_driver(self):
        self.client.force_authenticate(self.other_driver)
        other_order = OrderFactory(merchant=self.merchant_with_enabled_confirmation,
                                   driver=self.other_driver,
                                   status=OrderStatus.ASSIGNED)

        f = BytesIO()
        image = Image.new("RGBA", size=(50, 50))
        image.save(f, "png")
        f.seek(0)

        data = {'status': OrderStatus.DELIVERED,
                'order_confirmation_photos': [{"image": b64encode(f.read()), }]}
        resp = self.client.put('/api/orders/%s/status/' % other_order.order_id, data=data)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], OrderStatus.DELIVERED)
        self.assertGreater(len(resp.data['order_confirmation_photos']), 0)
        self.assertTrue(self.other_driver.order_set.filter(id=other_order.id).exists())

    def test_adding_photo_to_order_with_enabled_confirming_by_driver(self):
        self.client.force_authenticate(self.other_driver)
        other_order = OrderFactory(merchant=self.merchant_with_enabled_confirmation,
                                   driver=self.other_driver,
                                   status=OrderStatus.ASSIGNED)

        f = BytesIO()
        image = Image.new("RGBA", size=(50, 50))
        image.save(f, "png")
        f.seek(0)

        data = {'status': OrderStatus.DELIVERED,
                'order_confirmation_photos': [{"image": b64encode(f.read()), }]}
        resp = self.client.put('/api/orders/%s/confirmation/' % other_order.order_id, data=data)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], OrderStatus.DELIVERED)
        self.assertGreater(len(resp.data['order_confirmation_photos']), 0)
        self.assertTrue(self.other_driver.order_set.filter(id=other_order.id).exists())

    def test_save_actual_device_for_order(self):
        from notification.factories import GCMDeviceFactory
        self.order.refresh_from_db()
        self.assertIsNone(self.order.actual_device_id)
        self.change_status_to(OrderStatus.IN_PROGRESS)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.actual_device_id)

        gcm_device = GCMDeviceFactory.build()
        resp = self.client.post('/api/register-device/gcm/', data={
            'registration_id': gcm_device.registration_id,
            'device_id': gcm_device.device_id,
        })
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.change_status_to(OrderStatus.DELIVERED)
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.actual_device)
        self.assertEqual(self.order.actual_device.gcmdevice.registration_id, gcm_device.registration_id)


class CalculateStatusTimeDistancesTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        super(CalculateStatusTimeDistancesTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory(use_pick_up_status=True, use_way_back_status=True)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)

    def setUp(self):
        self.order = OrderFactory(merchant=self.merchant, status=OrderStatus.ASSIGNED, driver=self.driver)
        self.client.force_authenticate(self.driver)
        self.now = timezone.now()

    @mock.patch('routing.google.GoogleClient.directions_distance', return_value=[1200, 1000])
    def test_1(self, mock_obj):
        # ASSIGNED -> PICK_UP -> FAILED
        self.change_status_to(OrderStatus.PICK_UP, change_time=self.now)
        self.assert_statuses_time_distance(has_pickup=True, pickup_distance=1200)

        self.now += timedelta(seconds=5)
        mock_obj.reset_mock()
        self.change_status_to(OrderStatus.FAILED, change_time=self.now)
        self.assert_statuses_time_distance(has_pickup=True, has_overall=True, pickup_time=5,
                                           overall_time=5)

    @mock.patch('routing.google.GoogleClient.directions_distance', return_value=[1200, 1000])
    def test_2(self, mock_obj):
        # ASSIGNED -> PICK_UP -> IN_PROGRESS -> DELIVERED/FAILED
        self.change_status_to(OrderStatus.PICK_UP, change_time=self.now)
        self.assert_statuses_time_distance(has_pickup=True, pickup_distance=1200)

        self.now += timedelta(seconds=5)
        mock_obj.reset_mock()
        self.change_status_to(OrderStatus.IN_PROGRESS, change_time=self.now)
        self.assert_statuses_time_distance(has_pickup=True, pickup_time=5, pickup_distance=1200,
                                           has_in_progress=True, in_progress_time=None, in_progress_distance=1000)

        self.now += timedelta(seconds=10)
        mock_obj.reset_mock()
        self.change_status_to(OrderStatus.DELIVERED, change_time=self.now)
        self.assert_statuses_time_distance(has_pickup=True, pickup_time=5,
                                           has_in_progress=True, in_progress_time=10,
                                           has_overall=True, overall_time=15)

    @mock.patch('routing.google.GoogleClient.directions_distance', return_value=[1200, 1000])
    def test_3(self, mock_obj):
        # ASSIGNED -> PICK_UP -> IN_PROGRESS -> WAY_BACK -> DELIVERED/FAILED
        self.change_status_to(OrderStatus.PICK_UP, change_time=self.now)
        self.assert_statuses_time_distance(has_pickup=True, pickup_distance=1200)

        self.now += timedelta(seconds=5)
        mock_obj.reset_mock()
        self.change_status_to(OrderStatus.IN_PROGRESS, change_time=self.now)
        self.assert_statuses_time_distance(has_pickup=True, pickup_time=5, pickup_distance=1200,
                                           has_in_progress=True, in_progress_time=None, in_progress_distance=1000)

        resp = self.client.put('/api/v2/orders/%s/wayback_point' % self.order.id, {
                'wayback_point': {'location': {'lat': 12.345, 'lng': 21.345}}})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        self.now += timedelta(seconds=10)
        mock_obj.reset_mock()
        self.change_status_to(OrderStatus.WAY_BACK, change_time=self.now)
        self.assert_statuses_time_distance(
            has_pickup=True, pickup_time=5, pickup_distance=1200,
            has_in_progress=True, in_progress_time=10, in_progress_distance=1000,
            has_way_back=True, way_back_time=None, way_back_distance=None)
        self.order.refresh_from_db()
        self.assertEqual(self.order.wayback_at, self.now)

        mock_obj.return_value = [1100]
        resp = self.client.put('/api/v2/orders/%s/wayback_point' % self.order.id, {
                'wayback_point': {'location': {'lat': 12.345, 'lng': 21.345}}})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assert_statuses_time_distance(
            has_pickup=True, pickup_time=5, pickup_distance=1200,
            has_in_progress=True, in_progress_time=10, in_progress_distance=1000,
            has_way_back=True, way_back_time=None, way_back_distance=1100)

        self.now += timedelta(seconds=15)
        mock_obj.reset_mock()
        self.change_status_to(OrderStatus.DELIVERED, change_time=self.now)
        self.assert_statuses_time_distance(has_pickup=True, pickup_time=5,
                                           has_in_progress=True, in_progress_time=10,
                                           has_way_back=True, way_back_time=15,
                                           has_overall=True, overall_time=30)

    @mock.patch('routing.google.GoogleClient.directions_distance', return_value=[1000])
    def test_4(self, mock_obj):
        # ASSIGNED -> IN_PROGRESS -> DELIVERED/FAILED
        self.change_status_to(OrderStatus.IN_PROGRESS, change_time=self.now)
        self.assert_statuses_time_distance(has_in_progress=True, in_progress_time=None, in_progress_distance=1000)

        self.now += timedelta(seconds=15)
        mock_obj.reset_mock()
        self.change_status_to(OrderStatus.DELIVERED, change_time=self.now)
        self.assert_statuses_time_distance(has_in_progress=True, in_progress_time=15,
                                           has_overall=True, overall_time=15)

    @mock.patch('routing.google.GoogleClient.directions_distance', return_value=[1000])
    def test_5(self, mock_obj):
        # ASSIGNED -> IN_PROGRESS -> WAY_BACK -> DELIVERED/FAILED
        self.change_status_to(OrderStatus.IN_PROGRESS, change_time=self.now)
        self.assert_statuses_time_distance(has_in_progress=True, in_progress_time=None, in_progress_distance=1000)

        self.now += timedelta(seconds=10)
        mock_obj.reset_mock()
        self.change_status_to(OrderStatus.WAY_BACK, change_time=self.now)
        self.assert_statuses_time_distance(
            has_in_progress=True, in_progress_time=10, in_progress_distance=1000,
            has_way_back=True, way_back_time=None)
        self.order.refresh_from_db()
        self.assertEqual(self.order.wayback_at, self.now)

        self.now += timedelta(seconds=15)
        mock_obj.reset_mock()
        self.change_status_to(OrderStatus.DELIVERED, change_time=self.now)
        self.assert_statuses_time_distance(has_in_progress=True, in_progress_time=10,
                                           has_way_back=True, way_back_time=15,
                                           has_overall=True, overall_time=25)

    def test_6(self):
        # ASSIGNED -> DELIVERED/FAILED
        self.change_status_to(OrderStatus.DELIVERED, change_time=self.now)
        self.assert_statuses_time_distance(has_overall=True, overall_time=0, overall_distance=0)

    def change_status_to(self, order_status, change_time):
        with mock.patch('django.utils.timezone.now', return_value=change_time):
            order_resp = self.client.put('/api/v2/orders/%s/status' % self.order.id, {
                'status': order_status,
            })
            self.assertEqual(order_resp.status_code, status.HTTP_200_OK)
            self.assertEqual(order_resp.data['status'], order_status)

    def assert_statuses_time_distance(self,
                                      has_pickup=False, pickup_time=no_check, pickup_distance=no_check,
                                      has_in_progress=False, in_progress_time=no_check, in_progress_distance=no_check,
                                      has_way_back=False, way_back_time=no_check, way_back_distance=no_check,
                                      has_overall=False, overall_time=no_check, overall_distance=no_check):
        order = Order.objects.get(id=self.order.id)
        result = order.statuses_time_distance
        local_variables = locals()
        for key in [OrderStatus.PICK_UP, OrderStatus.IN_PROGRESS, OrderStatus.WAY_BACK, 'overall']:
            has_result_value = local_variables['has_%s' % key]
            assert (result[key] is not None) is has_result_value, \
                "'has_%s' is %s, not %s" % (key, not has_result_value, has_result_value)
            if not has_result_value:
                continue
            time_value = local_variables['%s_time' % key]
            distance_value = local_variables['%s_distance' % key]
            if time_value is not no_check:
                assert time_value == result[key]['time'], \
                    "'%s_time' is %s, not %s" % (key, result[key]['time'], time_value)
            if distance_value is not no_check:
                assert distance_value == result[key]['distance'], \
                    "'%s_distance' is %s, not %s" % (key, result[key]['distance'], distance_value)


class TimeOfStatusChangingTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant)

    def change_status(self, order, job_status, resp_status, initiator, driver=-1):
        url = '/api/v2/orders/{order_id}/' + ('status' if initiator.is_driver else '')
        method = self.client.put if initiator.is_driver else self.client.patch
        data = {'status': job_status}
        if driver != -1:
            data['driver'] = driver
        resp = method(url.format(order_id=order.id), data)
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
            self.client.force_authenticate(self.driver)
            self.change_status(order, OrderStatus.IN_PROGRESS, status.HTTP_200_OK, self.driver)
        order = Order.objects.get(id=order.id)
        self.assertEqual(order.assigned_at, assign_time)
        self.assertEqual(order.started_at, in_progress_time)

    def test_status_change_time_from_assigned(self):
        now = timezone.now()
        creation_time = now + timedelta(minutes=5)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = creation_time
            self.client.force_authenticate(self.manager)
            resp = self.client.post('/api/v2/orders/', {
                'status': OrderStatus.ASSIGNED,
                'driver': self.driver.id,
                'deliver_address': {'location': {'lat': 53.23, 'lng': 27.32}},
                'customer': {'name': 'Customer'},
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
