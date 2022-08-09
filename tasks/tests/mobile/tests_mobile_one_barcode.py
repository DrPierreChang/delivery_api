from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import MerchantFactory
from merchant.models import Merchant
from reporting.models import Event
from tasks.models import Order
from tasks.tests.factories import BarcodesFactory, OrderFactory
from webhooks.factories import MerchantAPIKeyFactory


class JobBarcodesTestsCase(APITestCase):
    api_orders_url = '/api/mobile/orders/v1/'
    api_barcodes_url = '/api/mobile/barcodes/v1/'

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
        deliver_before = timezone.now().astimezone(self.merchant.timezone)
        deliver_before = deliver_before.replace(hour=23, minute=59, second=59, microsecond=0)
        self.order_2 = OrderFactory(
            manager=self.manager,
            merchant=self.merchant,
            status=Order.ASSIGNED,
            driver=self.driver,
            pickup=None,
            pickup_address=None,
            deliver_before=deliver_before,
        )
        BarcodesFactory.create_batch(order=self.order_2, size=2)

        self.order_3 = OrderFactory(
            manager=self.manager,
            merchant=self.merchant,
            status=Order.IN_PROGRESS,
            driver=self.driver,
            deliver_before=deliver_before,
        )
        BarcodesFactory.create_batch(order=self.order_3, size=2)

        self.order_4 = OrderFactory(
            manager=self.manager,
            merchant=self.merchant,
            status=Order.IN_PROGRESS,
            driver=self.driver,
            deliver_before=deliver_before,
        )

    def test_create_job_with_barcodes(self):
        self.client.force_authenticate(self.driver)

        response = self.client.get(self.api_barcodes_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        barcode = self.order_2.barcodes.all().first()
        response = self.client.patch(self.api_barcodes_url + f'{barcode.id}/', data={'comment': 'comment'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['comment'], 'comment')

        response = self.client.get(self.api_barcodes_url + 'statistics/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(self.api_barcodes_url + 'scan/', data={'barcode_code': 'fake'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        events_count = Event.objects.count()
        response = self.client.post(self.api_barcodes_url + 'scan/', data={'barcode_code': barcode.code_data})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        barcode.refresh_from_db()
        self.assertTrue(barcode.scanned_at_the_warehouse)
        new_events_count = Event.objects.count() - events_count
        self.assertEqual(new_events_count, 1)

        response = self.client.post(self.api_barcodes_url + 'scan/', data={'barcode_code': barcode.code_data})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.order_2.status = Order.IN_PROGRESS
        self.order_2.save()
        response = self.client.post(self.api_barcodes_url + 'scan/', data={'barcode_code': barcode.code_data})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        barcode.refresh_from_db()
        self.assertTrue(barcode.scanned_upon_delivery)

        response = self.client.post(self.api_barcodes_url + 'scan/', data={'barcode_code': barcode.code_data})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_job_with_barcodes_only_at_the_warehouse(self):
        self.client.force_authenticate(self.driver)

        self.merchant.option_barcodes = Merchant.TYPES_BARCODES.before
        self.merchant.save()

        barcode = self.order_2.barcodes.all().first()

        events_count = Event.objects.count()
        response = self.client.post(self.api_barcodes_url + 'scan/', data={'barcode_code': barcode.code_data})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        barcode.refresh_from_db()
        self.assertTrue(barcode.scanned_at_the_warehouse)
        new_events_count = Event.objects.count() - events_count
        self.assertEqual(new_events_count, 1)

        response = self.client.post(self.api_barcodes_url + 'scan/', data={'barcode_code': barcode.code_data})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_job_with_barcodes_only_upon_delivery(self):
        self.client.force_authenticate(self.driver)

        self.merchant.option_barcodes = Merchant.TYPES_BARCODES.after
        self.merchant.save()

        barcode = self.order_2.barcodes.all().first()

        response = self.client.post(self.api_barcodes_url + 'scan/', data={'barcode_code': barcode.code_data})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.order_2.status = Order.IN_PROGRESS
        self.order_2.save()
        response = self.client.post(self.api_barcodes_url + 'scan/', data={'barcode_code': barcode.code_data})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        barcode.refresh_from_db()
        self.assertTrue(barcode.scanned_upon_delivery)
