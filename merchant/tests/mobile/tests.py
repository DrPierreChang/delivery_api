from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import HubFactory, MerchantFactory, SkillSetFactory, SubBrandingFactory


class MobileMerchantTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(
            enable_labels=True,
            enable_skill_sets=True,
            use_subbranding=True,
            use_hubs=True,
        )
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant)
        HubFactory.create_batch(size=5, merchant=cls.merchant)
        SkillSetFactory.create_batch(size=5, merchant=cls.merchant)
        SubBrandingFactory(merchant=cls.merchant)

    def setUp(self):
        self.client.force_authenticate(self.driver)

    def test_labels(self):
        resp = self.client.get('/api/mobile/labels/v1/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_skill_sets(self):
        resp = self.client.get('/api/mobile/skill_sets/v1/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_sub_branding(self):
        resp = self.client.get('/api/mobile/sub_branding/v1/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_hubs(self):
        resp = self.client.get('/api/mobile/hubs/v1/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_merchant(self):
        resp = self.client.get('/api/mobile/merchant/v1/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
