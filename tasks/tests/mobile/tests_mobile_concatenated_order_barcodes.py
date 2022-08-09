from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import MerchantFactory
from merchant.models import Merchant
from reporting.models import Event
from tasks.models import Barcode, ConcatenatedOrder, Order
from webhooks.factories import MerchantAPIKeyFactory


class CreateConcatenatedOrderBarcodesTestsCase(APITestCase):
    api_url = '/api/mobile/orders/v1/'
    co_api_url = '/api/mobile/concatenated_orders/v1/'

    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(
            option_barcodes=Merchant.TYPES_BARCODES.both,
            driver_can_create_job=True,
            enable_concatenated_orders=True,
        )
        cls.manager = ManagerFactory(
            merchant=cls.merchant
        )
        cls.merchant_api_key = MerchantAPIKeyFactory(
            creator=cls.manager,
            merchant=cls.merchant
        )
        cls.driver = DriverFactory(
            merchant=cls.merchant
        )

    def test_create_job_with_barcodes(self):
        self.client.force_authenticate(self.driver)

        order_data = {
            'driver_id': self.driver.id,
            'customer': {
                'name': 'John Sykes'
            },
            'deliver_address': {
                'address': 'Sydney, AU',
                'location': {'lat': 55.555555, 'lng': 22.222222}
            },
        }

        order_data_1 = {
            **order_data,
            'barcodes': [
                {
                    'code_data': 'barcode 1',
                    'required': True
                },
                {
                    'code_data': 'barcode 2',
                    'required': False
                }
            ]
        }
        order_data_2 = {
            **order_data,
            'barcodes': [
                {
                    'code_data': 'barcode 3',
                    'required': True
                }
            ]
        }

        response = self.client.post(self.api_url, order_data_1)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(order_data_1['barcodes']), len(response.data['barcodes']))

        response = self.client.post(self.api_url, order_data_2)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(order_data_2['barcodes']), len(response.data['barcodes']))

        concatenated_order = ConcatenatedOrder.objects.all().last()
        self.assertIsNotNone(concatenated_order)

        # check barcodes

        events_qs = Event.objects.filter(
            object_id__in=[order.id for order in concatenated_order.orders.all()], event=Event.MODEL_CHANGED
        )
        old_events_ids_qs = events_qs.values_list('id', flat=True)
        old_events_ids = list(old_events_ids_qs.all())

        response = self.client.post(
            self.co_api_url + str(concatenated_order.id) + '/scan_barcodes/',
            {'barcode_codes': ['barcode 1', 'barcode 2']}
        )
        concatenated_order.refresh_from_db()
        self.assertTrue(Barcode.objects.get(code_data='barcode 1').scanned_at_the_warehouse)
        self.assertTrue(Barcode.objects.get(code_data='barcode 2').scanned_at_the_warehouse)
        self.assertFalse(Barcode.objects.get(code_data='barcode 3').scanned_at_the_warehouse)
        self.assertEqual(events_qs.exclude(id__in=old_events_ids).all().count(), 1)  # barcodes 1 orders
        old_events_ids = list(old_events_ids_qs.all())

        response = self.client.patch(self.co_api_url + str(concatenated_order.id) + '/', {'status': Order.IN_PROGRESS})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        concatenated_order.refresh_from_db()
        self.assertEqual(events_qs.exclude(id__in=old_events_ids).all().count(), 2)  # 2 orders
        old_events_ids = list(old_events_ids_qs.all())

        self.client.post(
            self.co_api_url + str(concatenated_order.id) + '/scan_barcodes/',
            {'barcode_codes': ['barcode 2', 'barcode 3']}
        )

        self.assertFalse(Barcode.objects.get(code_data='barcode 1').scanned_upon_delivery)
        self.assertTrue(Barcode.objects.get(code_data='barcode 2').scanned_upon_delivery)
        self.assertTrue(Barcode.objects.get(code_data='barcode 3').scanned_upon_delivery)
        self.assertEqual(events_qs.exclude(id__in=old_events_ids).all().count(), 2)  # barcodes 2 orders
