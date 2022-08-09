import copy

from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import LabelFactory, MerchantFactory
from merchant.models import Label
from tasks.models import Order
from tasks.tests.factories import OrderFactory


class OrderLabelsTestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        super(OrderLabelsTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.label = LabelFactory(merchant=cls.merchant)
        cls.order = OrderFactory(merchant=cls.merchant, manager=cls.manager)
        cls.order.labels.add(cls.label)
        cls.default_job_data = {
            'customer': {
                'name': 'Test Customer'
            },
            'deliver_address': {
                'address': 'Eaton Gate, 2 Sloane Square, South Kensington, London SW1W 9BJ, UK',
                'location': '51.4938516,-0.1567399',
                'raw_address': 'Eaton Gate, 2 Sloane Square',
            }
        }

    def setUp(self):
        self.second_label = LabelFactory(merchant=self.merchant)

    def test_order_label(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/orders/active?page=1&page_size=300')
        self.assertTrue(isinstance(resp.data['results'][0]['label'], dict))

    def test_order_label_v2(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/v2/orders/active?page=1&page_size=300')
        self.assertTrue(isinstance(resp.data['results'][0]['labels'], list))

    def test_order_label_v2_hex_color(self):
        self.driver = DriverFactory(merchant=self.merchant)
        self.second_order = OrderFactory(merchant=self.merchant, manager=self.manager)
        self.second_order.driver = self.driver
        self.second_order.save()
        self.second_order.labels.add(self.label)

        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/v2/orders/%s' % self.second_order.id)
        self.assertEqual(resp.data['labels'][0]['color'], Label.BASE_COLORS[self.label.color])

    def test_create_order_with_multiple_labels(self):
        self.client.force_authenticate(self.manager)
        modified_job_data = copy.deepcopy(self.default_job_data)
        modified_job_data.update({'labels': [self.label.id, self.second_label.id]})
        resp = self.client.post('/api/orders/', data=modified_job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(order_id=resp.data['order_id'], labels__in=[self.label.id,
                                                                                 self.second_label.id]).distinct()
        self.assertTrue(order.exists())
        self.assertEqual(order[0].labels.count(), 2)

    def test_change_order_remove_labels(self):
        self.client.force_authenticate(self.manager)
        modified_job_data = copy.deepcopy(self.default_job_data)
        modified_job_data.update({'labels': [self.label.id, self.second_label.id]})
        resp = self.client.post('/api/orders/', data=modified_job_data)
        order_id = resp.data['order_id']
        resp = self.client.patch('/api/orders/%s/' % order_id, {'labels': []})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(Order.objects.filter(order_id=resp.data['order_id'], labels__isnull=True).exists())

    def test_create_order_with_multiple_labels_v2(self):
        self.driver = DriverFactory(merchant=self.merchant)
        self.merchant.driver_can_create_job = True
        self.merchant.save()
        self.client.force_authenticate(self.driver)
        modified_job_data = copy.deepcopy(self.default_job_data)
        modified_job_data.update({'labels': [self.label.id, self.second_label.id],
                                  'deliver_address': {
                                      'address': 'Eaton Gate, 2 Sloane Square, South Kensington, London SW1W 9BJ, UK',
                                      'location': {'lat': '51.4938516', 'lng': '-0.1567399'},
                                      'raw_address': 'Eaton Gate, 2 Sloane Square',
                                  }
                                  })
        resp = self.client.post('/api/v2/orders/', data=modified_job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(order_id=resp.data['order_id'], labels__in=[self.label.id,
                                                                                 self.second_label.id]).distinct()
        self.assertTrue(order.exists())
        self.assertEqual(order[0].labels.count(), 2)
