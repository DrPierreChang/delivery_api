from rest_framework import status

from tasks.models import Order
from tasks.tests.tests_bulk import BaseBulkUploadTestCase
from webhooks.factories import MerchantAPIKeyFactory


class ExternalBulkUploadTestCase(BaseBulkUploadTestCase):
    url = '/api/csv-upload/'

    @classmethod
    def setUpTestData(cls):
        super(ExternalBulkUploadTestCase, cls).setUpTestData()
        cls.apikey = MerchantAPIKeyFactory(creator=cls.manager, merchant=cls.merchant, available=True)
        cls.url += '?key={}'.format(cls.apikey.key)

    def setUp(self):
        super(ExternalBulkUploadTestCase, self).setUp()
        self.client.logout()

    def test_external_bulk_upload(self):
        resp = self.post_orders_in_csv(self.orders_list, status.HTTP_202_ACCEPTED)

        self.assertEqual(resp.data.get('errors', None), None)
        self.assertEqual(Order.objects.filter(manager=self.manager).count(), len(self.orders_list))
