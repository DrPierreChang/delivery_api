from rest_framework import status

from webhooks.factories import MerchantAPIKeyFactory
from webhooks.models import MerchantAPIKey

from .base_test_cases import APIKeyTestCase


class MerchantAPIKeyTestCase(APIKeyTestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    def test_get_api_keys_list(self):
        self.client.force_authenticate(self.manager)
        other_apikey = MerchantAPIKeyFactory(creator=self.manager, merchant=self.merchant, available=True)

        resp = self.client.get('/api/api-key/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], MerchantAPIKey.objects.filter(creator=self.manager).count())

    def test_set_api_key(self):
        self.client.force_authenticate(self.manager)
        data = {'name': 'myapikey', }

        resp = self.client.post('/api/api-key/', data=data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['name'], data['name'])

    def test_patch_api_key(self):
        self.client.force_authenticate(self.manager)
        data = {'available': False, }

        resp = self.client.put('/api/api-key/%s/' % self.apikey.key, data=data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['available'], data['available'])

    def test_delete_api_key(self):
        self.client.force_authenticate(self.manager)

        resp = self.client.delete('/api/api-key/%s/' % self.apikey.key)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(MerchantAPIKey.objects.filter(key=self.apikey.key).exists())
