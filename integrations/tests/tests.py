from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import ManagerFactory
from integrations.factories import RevelSystemFactory
from integrations.models import RevelSystem
from merchant.factories import MerchantFactory


class RevelSystemIntegrationTestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)

    def test_getting_revel_systems(self):
        RevelSystemFactory.create_batch(size=10, merchant=self.merchant, creator=self.manager)

        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/integrations/revel/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], RevelSystem.objects.filter(merchant=self.merchant).count())

    def test_setting_revel_systems(self):
        data = {
            'merchant': self.merchant.pk,
            'subdomain': 'test-subdomain',
            'api_key': 'myapikey',
            'api_secret': 'myapisecret'
        }

        self.client.force_authenticate(self.manager)
        resp = self.client.post('/api/integrations/revel/', data=data)

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
