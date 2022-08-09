from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import MerchantFactory
from tasks.models import ConcatenatedOrder


class ConcatenatedTestCase(APITestCase):
    aggregated_orders_url = '/api/web/dev/orders/'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.merchant = MerchantFactory(enable_concatenated_orders=True)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant)

    def setUp(self):
        self.client.force_authenticate(self.manager)

    def test_aggregated_orders_api(self):
        order_data_1 = {
            'deliver': {
                'customer': {'name': 'Mike Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            }
        }
        resp = self.client.post(self.aggregated_orders_url, data=order_data_1)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resp = self.client.post(self.aggregated_orders_url, data=order_data_1)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        order_data_2 = {
            'deliver': {
                'customer': {'name': 'Luis Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 3',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            }
        }
        resp = self.client.post(self.aggregated_orders_url, data=order_data_2)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()
        self.assertEqual(concatenated_order.orders.all().count(), 2)

        resp = self.client.get(f'{self.aggregated_orders_url}?types_group=aggregated')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 2)

        resp = self.client.get(f'{self.aggregated_orders_url}?types_group=aggregated&page_size=1&page=1')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['results']), 1)
        self.assertIsNotNone(resp.data['next'])
        self.assertIsNone(resp.data['previous'])

        resp = self.client.get(f'{self.aggregated_orders_url}?types_group=aggregated&page_size=1&page=2')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['results']), 1)
        self.assertIsNone(resp.data['next'])
        self.assertIsNotNone(resp.data['previous'])

        resp = self.client.get(
            f'{self.aggregated_orders_url}?types_group=aggregated&q=bla&status=not_assigned&group=active',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.get(f'{self.aggregated_orders_url}ids/?types_group=aggregated')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['results']), 2)

        resp = self.client.get(f'{self.aggregated_orders_url}deadlines/?types_group=aggregated')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['results']), 2)

        resp = self.client.get(f'{self.aggregated_orders_url}last_customer_comments/?types_group=aggregated')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.merchant.enable_concatenated_orders = False
        self.merchant.save()

        resp = self.client.get(self.aggregated_orders_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 3)

        resp = self.client.get(f'{self.aggregated_orders_url}ids/?types_group=aggregated')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['results']), 3)

        resp = self.client.get(f'{self.aggregated_orders_url}deadlines/?types_group=aggregated')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['results']), 3)

        resp = self.client.get(f'{self.aggregated_orders_url}last_customer_comments/?types_group=aggregated')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
