from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import MerchantFactory
from tasks.tests.factories import OrderFactory


class SearchTestCase(APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    @classmethod
    def setUpTestData(cls):
        super(SearchTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)

    def test_search_with_results(self):
        DriverFactory(merchant=self.merchant, last_name='Doe', )
        DriverFactory(merchant=self.merchant, first_name='Testman', )
        OrderFactory(merchant=self.merchant, title='ordertest', )
        OrderFactory(merchant=self.merchant, title='OrDeRtEsT', )

        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/search/', data={'q': 'test', })

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 3)

    def test_search_without_results(self):
        DriverFactory(merchant=self.merchant, last_name='Doe', )
        DriverFactory(merchant=self.merchant, first_name='Testman', )
        OrderFactory(merchant=self.merchant, title='ordertest', )
        OrderFactory(merchant=self.merchant, title='OrDeRtEsT', )

        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/search/', data={'q': 'te', })

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 0)
