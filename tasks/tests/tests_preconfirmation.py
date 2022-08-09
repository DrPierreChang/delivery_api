from base64 import b64encode
from io import BytesIO

from rest_framework import status
from rest_framework.test import APITestCase

from PIL import Image

from base.factories import DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from tasks.models import Order
from tasks.tests.factories import OrderFactory


def get_preconfirmation_data():
    f = BytesIO()
    image = Image.new("RGBA", size=(50, 50))
    image.save(f, "png")
    f.seek(0)
    pre_confirmation_signature = b64encode(f.read())
    pre_confirmation_photos = [{"image": pre_confirmation_signature, }]
    pre_confirmation_comment = "Test preconfirmation comment"

    return {"pre_confirmation_signature": pre_confirmation_signature,
            "pre_confirmation_photos": pre_confirmation_photos,
            "pre_confirmation_comment": pre_confirmation_comment}


class TestOrderPreConfirmationDisabledAPITestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)

        cls.pre_confirmation_data = get_preconfirmation_data()

    def test_pre_confirmation_disabled(self):
        order = OrderFactory(manager=self.manager, driver=self.driver, status=Order.IN_PROGRESS, merchant=self.merchant)
        self.client.force_authenticate(self.driver)
        resp = self.client.put('/api/orders/{}/confirmation'.format(order.order_id), data=self.pre_confirmation_data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp_data = resp.json()
        self.assertEqual(resp_data['pre_confirmation_signature'], None)
        self.assertEqual(resp_data['pre_confirmation_photos'], [])


class TestOrderPreConfirmationEnabledAPITestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(enable_delivery_pre_confirmation=True)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)
        cls.pre_confirmation_data = get_preconfirmation_data()

    def setUp(self):
        self.order = OrderFactory(manager=self.manager, driver=self.driver,
                                  status=Order.IN_PROGRESS, merchant=self.merchant)

    def test_pre_confirmation(self):
        self.client.force_authenticate(self.driver)
        resp = self.client.put('/api/orders/{}/confirmation'.format(self.order.order_id),
                               data=self.pre_confirmation_data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.order.refresh_from_db()
        self.assertEqual(self.order.pre_confirmation_photos.count(),
                         len(self.pre_confirmation_data['pre_confirmation_photos']))

    def test_pre_confirmation_with_completed_order_status(self):
        order = OrderFactory(manager=self.manager, driver=self.driver, status=Order.DELIVERED, merchant=self.merchant)
        self.client.force_authenticate(self.driver)
        resp = self.client.put('/api/orders/{}/confirmation'.format(order.order_id), data=self.pre_confirmation_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
