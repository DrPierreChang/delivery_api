from __future__ import unicode_literals

from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import ManagerFactory
from merchant.factories import HubFactory, MerchantFactory
from merchant.models import Hub


class HubsChangingTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)
        HubFactory.create_batch(size=10, merchant=cls.merchant)
        HubFactory.create_batch(size=10)

    def setUp(self):
        self.client.force_authenticate(self.manager)

    def test_hub_creation_without_location(self):
        hub_info = {'name': 'My new hub',
                    'phone': '+61499909090', }
        resp = self.client.post('/api/hubs/', data=hub_info)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsNotNone(resp.data['errors'].get('location'))

    def test_hub_creation_with_location(self):
        hub_info = {'name': 'My second hub',
                    'phone': '+61499909091',
                    'location': {'location': '55.555555,22.222222',
                                 'address': 'test address'}, }
        resp = self.client.post('/api/hubs/', data=hub_info)

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Hub.objects.filter(id=resp.data['id']).exists())
        self.assertEqual(resp.data['location']['location'], hub_info['location']['location'])

    def test_hub_change_info(self):
        hub = Hub.objects.filter(merchant=self.merchant).first()
        new_info = {'name': 'New name for hub',
                    'phone': '+61499908090'}
        resp = self.client.patch('/api/hubs/%s' % hub.id, data=new_info)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(new_info, dict(filter(lambda item: item[0] in new_info.keys(), resp.data.items())))

    def test_hubs_list_getting(self):
        resp = self.client.get('/api/hubs/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], Hub.objects.filter(merchant=self.merchant).count())

    def test_hubs_list_getting_v2(self):
        resp = self.client.get('/api/v2/hubs/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        hub = resp.data['results'][0]
        hub_model = Hub.objects.get(id=hub['id'])
        lat_lng = dict(zip(('lat', 'lng'), map(float, hub_model.location.location.split(','))))
        self.assertDictEqual(resp.data['results'][0]['location']['location'], lat_lng)

    def test_hub_creation_with_location_v2(self):
        hub_info = {'name': 'My second hub',
                    'phone': '+61499909091',
                    'location': {'location': {'lat': 55.555555, 'lng': 22.222222},
                                 'address': 'test address'}, }
        resp = self.client.post('/api/v2/hubs/', data=hub_info)

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Hub.objects.filter(id=resp.data['id']).exists())
        self.assertDictEqual(resp.data['location']['location'], hub_info['location']['location'])

    def test_hub_deletion(self):
        hub = Hub.objects.filter(merchant=self.merchant).first()
        resp = self.client.delete('/api/hubs/%s/' % hub.id)

        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        with self.assertRaises(Hub.DoesNotExist):
            Hub.objects.get(id=hub.id)

    def test_hub_events(self):
        date = timezone.now()
        hub = Hub.objects.filter(merchant=self.merchant).first()
        data = {k: getattr(hub, k) for k in ('id', 'name', 'phone')}
        data['name'] = 'Broken'
        resp = self.client.patch('/api/hubs/%s/' % hub.id, data=data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.get('/api/v2/new-events/', params={'date_since': date})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
