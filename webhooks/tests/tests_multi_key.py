import copy

from rest_framework import status
from rest_framework.test import APITestCase

import factory
from six.moves import cStringIO

from base.factories import AdminFactory, DriverFactory
from base.utils import get_fuzzy_location
from merchant.factories import MerchantFactory
from tasks.models import Order
from tasks.tests.factories import OrderFactory
from tasks.tests.utils import CreateOrderCSVTextMixin
from webhooks.factories import MerchantAPIKeyFactory
from webhooks.models import MerchantAPIKey


class MerchantAPIMultiKeyTestCase(CreateOrderCSVTextMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.merchants = MerchantFactory.create_batch(size=3)
        cls.admin = AdminFactory(merchant=cls.merchants[0])
        cls.drivers = [DriverFactory(merchant=merchant) for merchant in cls.merchants]
        cls.multi_key = MerchantAPIKeyFactory(creator=cls.admin, merchant=None, key_type=MerchantAPIKey.MULTI,
                                              available=True)
        for merchant in cls.merchants:
            merchant.api_multi_key = cls.multi_key
            merchant.save()
        cls.default_orders_payload = [{'external_id': 'external-{}'.format(driver.member_id),
                                       'customer': {'name': 'customer-{}'.format(driver.id)},
                                       'deliver_address': {'location': get_fuzzy_location()},
                                       'driver': driver.member_id}
                                      for driver in cls.drivers]

    def test_bulk_create_orders(self):
        resp = self.client.post('/api/webhooks/jobs/?key=%s' % self.multi_key.key, data=self.default_orders_payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        orders = Order.objects.filter(driver_id__in=[d.id for d in self.drivers])
        self.assertEqual(orders.count(), len(self.default_orders_payload))
        for driver in self.drivers:
            self.assertEqual(orders.get(driver_id=driver.id).merchant, driver.current_merchant)

    def test_create_order_without_driver(self):
        data = copy.deepcopy(self.default_orders_payload[0])
        del data['driver']
        resp = self.client.post('/api/webhooks/jobs/?key=%s' % self.multi_key.key, data=data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_order_with_wrong_driver(self):
        self.extra_merchant = MerchantFactory()
        self.extra_driver = DriverFactory(merchant=self.extra_merchant)
        data = copy.deepcopy(self.default_orders_payload[0])
        data['driver'] = self.extra_driver.member_id
        resp = self.client.post('/api/webhooks/jobs/?key=%s' % self.multi_key.key, data=data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_orders_list_with_master_key(self):
        extra_orders = OrderFactory.create_batch(size=3, external_job=None,
                                                 merchant=self.merchants[0], manager=self.admin)
        self.client.post('/api/webhooks/jobs/?key=%s' % self.multi_key.key, data=self.default_orders_payload)

        resp = self.client.get('/api/webhooks/jobs/?key=%s' % self.multi_key.key)
        self.assertEqual(resp.data['count'], len(self.default_orders_payload))

        self.multi_key.is_master_key = True
        self.multi_key.save()

        resp = self.client.get('/api/webhooks/jobs/?key=%s' % self.multi_key.key)
        self.assertEqual(resp.data['count'], len(self.default_orders_payload) + len(extra_orders))

    def test_update_order_with_multi_key(self):
        self.client.post('/api/webhooks/jobs/?key=%s' % self.multi_key.key, data=self.default_orders_payload)
        order = Order.objects.filter(merchant__in=self.merchants).last()
        update_data = {'title': 'New Title'}
        resp = self.client.patch('/api/webhooks/jobs/{}/?key={}&lookup_field=order_id'
                                 .format(order.order_id, self.multi_key.key), data=update_data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.title, update_data['title'])

    def test_upload_mixed_csv(self):
        csv_orders = [factory.build(Order, FACTORY_CLASS=OrderFactory, driver=driver) for driver in self.drivers]
        csv_text = self.create_csv_text(csv_orders)
        data = {'file': cStringIO(csv_text)}
        resp = self.client.post('/api/csv-upload/?key={}'.format(self.multi_key.key), data=data, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        orders = Order.objects.filter(driver_id__in=[d.id for d in self.drivers])
        self.assertEqual(orders.count(), len(csv_orders))
        for driver in self.drivers:
            self.assertEqual(orders.get(driver_id=driver.id).merchant, driver.current_merchant)
