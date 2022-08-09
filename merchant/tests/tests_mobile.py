from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import HubFactory, MerchantFactory
from merchant.models import DriverHub


class MobileTestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.merchant = MerchantFactory(use_hubs=True)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant)
        cls.hubs = HubFactory.create_batch(size=10, merchant=cls.merchant)
        DriverHub.objects.create(driver=cls.driver, hub=cls.hubs[0])

    def setUp(self):
        self.client.force_authenticate(self.driver)

    def test_hubs(self):
        resp = self.client.get('/api/mobile/hubs/v1/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 10)

        resp = self.client.get('/api/mobile/hubs/v1/', data={'wayback': 'true'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)
