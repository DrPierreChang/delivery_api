from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from tasks.tests.factories import OrderFactory


class PublicReportTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(work_status=WorkStatus.WORKING, merchant=cls.merchant)
        cls.merchant_uidb64 = urlsafe_base64_encode(force_bytes(cls.merchant.id))

    def setUp(self):
        self.order = OrderFactory(merchant=self.merchant)
        self.client.force_authenticate(self.manager)

    def test_get_public_report_link(self):
        resp = self.client.get('/api/v2/orders/%s/' % (self.order.id,))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.data['public_report_link'])
        resp = self.client.patch('/api/v2/orders/%s/' % (self.order.id,), {'status': 'failed'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get('/api/v2/orders/%s/' % (self.order.id,))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data['public_report_link'])
        self.assertIn(self.merchant_uidb64, resp.data['public_report_link'])
        self.assertIn(str(self.order.order_token), resp.data['public_report_link'])

    def test_get_public_report_data(self):
        resp = self.client.patch('/api/v2/orders/%s/' % (self.order.id,), {'status': 'failed'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get('/api/v2/orders/%s/' % (self.order.id,))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data['public_report_link'])
        self.client.logout()
        url = '/api/v2/public-merchant/%s/public-report/%s/' % (self.merchant_uidb64, str(self.order.order_token))
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_cant_get_public_report_wrong_merchant(self):
        resp = self.client.patch('/api/v2/orders/%s/' % (self.order.id,), {'status': 'failed'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get('/api/v2/orders/%s/' % (self.order.id,))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data['public_report_link'])
        self.client.logout()
        url = '/api/v2/public-merchant/%s/public-report/%s/' % (self.merchant_uidb64+'random',
                                                                str(self.order.order_token))
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
