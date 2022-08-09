import copy

from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import ManagerFactory
from merchant.factories import LabelFactory, MerchantFactory
from tasks.models import Order
from tasks.tests.factories import OrderFactory


class OrderLabelsTestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        super(OrderLabelsTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory(enable_labels=True)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.label = LabelFactory(merchant=cls.merchant)
        cls.order = OrderFactory(merchant=cls.merchant, manager=cls.manager)
        cls.order.labels.add(cls.label)
        cls.default_job_data = {
            'deliver': {
                'customer': {
                    'name': 'Mike Kowalski',
                },
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {
                            'lat': 53.91254758887667,
                            'lng': 27.543441765010357
                        },
                    },
                    'secondary_address': '27'
                }
            }
        }

        cls.orders_url = '/api/web/dev/orders/'

    def setUp(self):
        self.second_label = LabelFactory(merchant=self.merchant)

    def test_order_label(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get(f'{self.orders_url}?group=active&page=1&page_size=300')
        self.assertTrue(isinstance(resp.data['results'][0]['label_ids'], list))

    def test_change_order_remove_labels(self):
        self.client.force_authenticate(self.manager)
        modified_job_data = copy.deepcopy(self.default_job_data)
        modified_job_data.update({'label_ids': [self.label.id, self.second_label.id]})
        resp = self.client.post(self.orders_url, data=modified_job_data)
        job_id = resp.data['id']
        resp = self.client.patch(f'{self.orders_url}{job_id}/', {'label_ids': []})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(Order.objects.filter(order_id=resp.data['order_id'], labels__isnull=True).exists())

    def test_create_order_with_multiple_labels_v2(self):
        self.client.force_authenticate(self.manager)
        modified_job_data = copy.deepcopy(self.default_job_data)
        modified_job_data.update({
            'label_ids': [self.label.id, self.second_label.id],
            'deliver': {
                'customer': {
                    'name': 'Mike Kowalski',
                },
                'address': {
                    'primary_address': {
                        'address': 'Eaton Gate, 2 Sloane Square, South Kensington, London SW1W 9BJ, UK',
                        'location': {'lat': '51.4938516', 'lng': '-0.1567399'},
                    },
                }
            }
        })
        resp = self.client.post(self.orders_url, data=modified_job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(
            order_id=resp.data['order_id'], labels__in=[self.label.id, self.second_label.id]
        ).distinct()
        self.assertTrue(order.exists())
        self.assertEqual(order[0].labels.count(), 2)
