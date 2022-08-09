from django.test import TransactionTestCase

from rest_framework import status

import factory
from six.moves import cStringIO

from base.factories import AdminFactory, DriverFactory
from merchant.factories import MerchantFactory
from tasks.models import ConcatenatedOrder, Order
from tasks.tests.factories import OrderFactory
from tasks.tests.utils import CreateOrderCSVTextMixin
from webhooks.factories import MerchantAPIKeyFactory


class ConcatenatedOrderCSVTestCase(CreateOrderCSVTextMixin, TransactionTestCase):
    def test_upload_mixed_csv(self):
        self.merchant = MerchantFactory(enable_concatenated_orders=True)
        self.admin = AdminFactory(merchant=self.merchant)
        self.driver = DriverFactory(merchant=self.merchant)
        self.key = MerchantAPIKeyFactory(creator=self.admin, merchant=self.merchant, available=True)

        csv_order_1 = factory.build(Order, FACTORY_CLASS=OrderFactory, merchant=self.merchant, driver=self.driver)
        csv_order_2 = factory.build(
            Order, FACTORY_CLASS=OrderFactory, merchant=self.merchant, driver=self.driver,
            customer=csv_order_1.customer, deliver_address=csv_order_1.deliver_address,
            deliver_before=csv_order_1.deliver_before,
        )
        csv_order_3 = factory.build(
            Order, FACTORY_CLASS=OrderFactory, merchant=self.merchant, driver=self.driver,
            customer=csv_order_1.customer, deliver_address=csv_order_1.deliver_address,
            deliver_before=csv_order_1.deliver_before,
        )
        csv_text = self.create_csv_text([csv_order_1, csv_order_2, csv_order_3])
        data = {'file': cStringIO(csv_text)}
        resp = self.client.post('/api/csv-upload/?key={}'.format(self.key.key), data=data, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        orders = Order.objects.filter(driver_id=self.driver.id)
        self.assertEqual(orders.count(), 3)
        concatenated_order = ConcatenatedOrder.objects.filter(driver_id=self.driver.id).last()
        self.assertIsNotNone(concatenated_order)
