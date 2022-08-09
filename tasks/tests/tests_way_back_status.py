import tempfile
from base64 import b64encode

from rest_framework import status
from rest_framework.test import APITestCase

from PIL import Image

from base.factories import DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import HubFactory, MerchantFactory
from merchant.models import Merchant
from tasks.models import OrderStatus
from tasks.tests.factories import OrderFactory


class OrderWithWayBackTestCase(APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    @classmethod
    def setUpTestData(cls):
        super(OrderWithWayBackTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory(use_way_back_status=True)
        cls.merchant_with_confirmation = MerchantFactory(use_way_back_status=True, enable_delivery_confirmation=True)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)
        cls.driver_with_confirmation = DriverFactory(merchant=cls.merchant_with_confirmation, work_status=WorkStatus.WORKING)
        cls.hub = HubFactory(merchant=cls.merchant)

    def setUp(self):
        self.order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.IN_PROGRESS,
            driver=self.driver
        )
        self.client.force_authenticate(self.driver)

    def test_change_status_to_way_back(self):
        resp = self.client.put('/api/orders/{order_id}/status'.format(order_id=self.order.order_id),
                                 {'status': OrderStatus.WAY_BACK})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], OrderStatus.WAY_BACK)

    def test_change_status_to_way_back_geofence_on_entered(self):
        geofence_on_enter_merchant = MerchantFactory(use_way_back_status=True, geofence_settings=Merchant.UPON_ENTERING)
        driver = DriverFactory(merchant=geofence_on_enter_merchant, work_status=WorkStatus.WORKING)
        self.client.force_authenticate(driver)
        order = OrderFactory(merchant=geofence_on_enter_merchant, status=OrderStatus.IN_PROGRESS, driver=driver)
        resp = self.client.put('/api/orders/{order_id}/geofence'.format(order_id=order.order_id),
                                 {'geofence_entered': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], OrderStatus.WAY_BACK)

    def test_change_status_to_way_back_geofence_on_exit(self):
        geofence_on_exit_merchant = MerchantFactory(use_way_back_status=True, geofence_settings=Merchant.UPON_EXITING)
        driver = DriverFactory(merchant=geofence_on_exit_merchant, work_status=WorkStatus.WORKING)
        self.client.force_authenticate(driver)
        order = OrderFactory(merchant=geofence_on_exit_merchant, status=OrderStatus.IN_PROGRESS, driver=driver)

        resp = self.client.put('/api/orders/{order_id}/geofence'.format(order_id=order.order_id),
                                 {'geofence_entered': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], OrderStatus.IN_PROGRESS)

        resp = self.client.put('/api/orders/{order_id}/geofence'.format(order_id=order.order_id),
                                 {'geofence_entered': False})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], OrderStatus.WAY_BACK)

    def test_confirmation_after_way_back_setting(self):
        self.client.force_authenticate(self.driver_with_confirmation)
        order = OrderFactory(merchant=self.merchant_with_confirmation, status=OrderStatus.WAY_BACK,
                             driver=self.driver_with_confirmation)
        with tempfile.TemporaryFile('wb+') as tf:
            image = Image.new("RGBA", size=(50, 50))
            image.save(tf, "png")
            tf.seek(0)

            resp = self.client.put('/api/orders/{order_id}/confirmation/'.format(order_id=order.order_id),
                                   {"confirmation_signature": b64encode(tf.read())})

            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertTrue(resp.data['confirmation_signature'])

    def test_change_status_to_way_back_with_confirmation(self):
        self.client.force_authenticate(self.driver_with_confirmation)
        order = OrderFactory(merchant=self.merchant_with_confirmation, status=OrderStatus.IN_PROGRESS,
                             driver=self.driver_with_confirmation)

        with tempfile.TemporaryFile('wb+') as tf:
            image = Image.new("RGBA", size=(50, 50))
            image.save(tf, "png")
            tf.seek(0)
            sign = b64encode(tf.read())
            resp = self.client.put('/api/orders/{order_id}/status/'.format(order_id=order.order_id),
                                   {"status": OrderStatus.WAY_BACK, "confirmation_signature": sign})
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(resp.data['status'], OrderStatus.WAY_BACK)
            self.assertTrue(resp.data['confirmation_signature'])

    def test_set_wayback_point(self):
        order = OrderFactory(merchant=self.merchant, manager=self.manager, status=OrderStatus.ASSIGNED,
                             driver=self.driver)
        self.client.put('/api/orders/{order_id}/status'.format(order_id=order.order_id),
                        {'status': OrderStatus.IN_PROGRESS})
        resp = self.client.put('/api/orders/{order_id}/wayback_point'.format(order_id=order.order_id),
                               {'wayback_hub': self.hub.id})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        resp = self.client.put('/api/orders/{order_id}/status'.format(order_id=order.order_id),
                               {'status': OrderStatus.WAY_BACK})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], OrderStatus.WAY_BACK)

        wayback_point_url = '/api/orders/{order_id}/wayback_point'.format(order_id=order.order_id)
        resp = self.client.put(wayback_point_url, {'wayback_hub': self.hub.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertIsNotNone(order.wayback_hub)
        self.assertIsNone(order.wayback_point)

        resp = self.client.put(wayback_point_url, {'wayback_point': {'location': {'lat': 23.123, 'lng': 23.123}}})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertIsNotNone(order.wayback_point)
        self.assertIsNone(order.wayback_hub)

        resp = self.client.put(wayback_point_url, {'wayback_hub': self.hub.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertIsNotNone(order.wayback_hub)
        self.assertIsNone(order.wayback_point)
