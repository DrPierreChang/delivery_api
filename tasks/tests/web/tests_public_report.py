from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, DriverLocationFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import LabelFactory, MerchantFactory, SkillSetFactory, SubBrandingFactory
from tasks.tests.factories import OrderFactory


class WebPublicReportTestCase(APITestCase):
    order_url = '/api/web/dev/orders/{}/'.format
    order_report_url = '/api/web/dev/public_report/merchant/{}/orders/{}/'.format

    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(work_status=WorkStatus.WORKING, merchant=cls.merchant)
        cls.merchant_uidb64 = urlsafe_base64_encode(force_bytes(cls.merchant.id))

    def setUp(self):
        self.label = LabelFactory(merchant=self.merchant)
        self.skill_set = SkillSetFactory(merchant=self.merchant)
        self.sub_brand = SubBrandingFactory(merchant=self.merchant, jobs_export_email='subbrand@test.com')
        self.order = OrderFactory(merchant=self.merchant, sub_branding=self.sub_brand)
        self.order.skill_sets.add(self.skill_set)
        self.order.labels.add(self.label)
        self.client.force_authenticate(self.manager)

    def test_get_public_report_link(self):
        resp = self.client.get(self.order_url(self.order.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.data['public_report_link'])
        resp = self.client.patch(self.order_url(self.order.id), {'status': 'failed'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(self.order_url(self.order.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data['public_report_link'])
        self.assertIn(self.merchant_uidb64, resp.data['public_report_link'])
        self.assertIn(str(self.order.order_token), resp.data['public_report_link'])

    def test_get_public_report_data(self):
        resp = self.client.patch(self.order_url(self.order.id), {'status': 'failed'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(self.order_url(self.order.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data['public_report_link'])

        locations = list(DriverLocationFactory.create_batch(size=10, member=self.driver))
        self.order.path = {'full': [loc.location for loc in locations]}
        self.order.save()

        resp = self.client.get(self.order_url(self.order.id) + 'path/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.client.logout()
        url = self.order_report_url(self.merchant_uidb64, self.order.order_token)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_cant_get_public_report_wrong_merchant(self):
        resp = self.client.patch(self.order_url(self.order.id), {'status': 'failed'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get(self.order_url(self.order.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data['public_report_link'])
        self.client.logout()
        url = self.order_report_url(self.merchant_uidb64 + 'random', self.order.order_token)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
