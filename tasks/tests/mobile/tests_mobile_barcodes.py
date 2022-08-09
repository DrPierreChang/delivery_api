from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import MerchantFactory
from merchant.models import Merchant
from reporting.models import Event
from tasks.models import Barcode, Order
from tasks.tests.factories import BarcodesFactory, OrderFactory
from webhooks.factories import MerchantAPIKeyFactory


class CreateJobBarcodesTestsCase(APITestCase):
    api_url = '/api/mobile/orders/v1/'

    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(
            option_barcodes=Merchant.TYPES_BARCODES.both,
            driver_can_create_job=True
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

    def setUp(self):
        self.job_with_barcodes = OrderFactory(
            manager=self.manager,
            merchant=self.merchant
        )
        self.barcodes = BarcodesFactory.create_batch(order=self.job_with_barcodes, size=3)

    def test_create_job_with_barcodes(self):
        self.client.force_authenticate(self.driver)

        # check first order

        order_data = {
            'driver_id': self.driver.id,
            'customer': {
                'name': 'John Sykes'
            },
            'deliver_address': {
                'address': 'Sydney, AU',
                'location': {'lat': 55.555555, 'lng': 22.222222}
            },
            'barcodes': [
                {
                    'code_data': '123456_z',
                    'required': True
                },
                {
                    'code_data': 'hello world!_z',
                    'required': False
                },
                {
                    'code_data': 'qwerty_z',
                }
            ]
        }

        response = self.client.post(self.api_url, order_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(order_data['barcodes']), len(response.data['barcodes']))

        order = Order.objects.get(id=response.data['server_entity_id'])

        # check second order
        order_data = {
            'driver_id': self.driver.id,
            'customer': {
                'name': 'John One'
            },
            'deliver_address': {
                'address': 'Sydney, AU',
                'location': {'lat': 55.555555, 'lng': 22.222222}
            },
            'barcodes': [
                {
                    'code_data': '123456_z',
                    'required': True
                }
            ]
        }

        # Unique check
        response = self.client.post(self.api_url, order_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        order_data['barcodes'] = [
            {
                'code_data': 'bla_q',
                'required': False
            },
            {
                'code_data': 'bla_q',
                'required': False
            }
        ]

        # Unique check
        response = self.client.post(self.api_url, order_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        order_data['barcodes'] = [
            {
                'code_data': 'bla_q',
                'required': False
            }
        ]

        response = self.client.post(self.api_url, order_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        order_2 = Order.objects.get(id=response.data['server_entity_id'])

        # check barcodes

        events_qs = Event.objects.filter(object_id__in=[order.id, order_2.id], event=Event.MODEL_CHANGED)
        old_events_ids_qs = events_qs.values_list('id', flat=True)

        self.client.post(
            self.api_url + str(order.id) + '/scan_barcodes/',
            {'barcode_codes': ['123456_z', 'hello world!_z']}
        )
        order.refresh_from_db()
        self.assertTrue(Barcode.objects.get(code_data='123456_z').scanned_at_the_warehouse)
        self.assertTrue(Barcode.objects.get(code_data='hello world!_z').scanned_at_the_warehouse)
        self.assertFalse(Barcode.objects.get(code_data='qwerty_z').scanned_at_the_warehouse)
        self.assertEqual(events_qs.all().count(), 1)
        old_events_ids = list(old_events_ids_qs.all())

        response = self.client.patch(self.api_url + str(order.id) + '/', {'status': Order.IN_PROGRESS})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(events_qs.exclude(id__in=old_events_ids).all().count(), 1)
        old_events_ids = list(old_events_ids_qs.all())

        self.client.post(
            self.api_url + str(order.id) + '/scan_barcodes/',
            {'barcode_codes': ['qwerty_z', 'hello world!_z']}
        )

        self.assertFalse(Barcode.objects.get(code_data='123456_z').scanned_upon_delivery)
        self.assertTrue(Barcode.objects.get(code_data='hello world!_z').scanned_upon_delivery)
        self.assertTrue(Barcode.objects.get(code_data='qwerty_z').scanned_upon_delivery)
        self.assertEqual(events_qs.exclude(id__in=old_events_ids).all().count(), 1)
        old_events_ids = list(old_events_ids_qs.all())

        # check multi-order barcodes

        self.client.post(
            self.api_url + 'scan_barcodes/',
            {'barcode_codes': ['123456_z', 'bla_q']}
        )

        self.assertTrue(Barcode.objects.get(code_data='123456_z').scanned_upon_delivery)
        self.assertTrue(Barcode.objects.get(code_data='bla_q').scanned_at_the_warehouse)
        self.assertEqual(events_qs.exclude(id__in=old_events_ids).all().count(), 2)
