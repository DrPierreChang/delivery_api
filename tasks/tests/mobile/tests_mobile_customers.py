from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory
from merchant.factories import MerchantFactory
from merchant.models import Merchant
from tasks.models import Customer, Pickup
from tasks.tests.factories import CustomerFactory, PickupFactory


class CustomerTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(
            option_barcodes=Merchant.TYPES_BARCODES.both,
            driver_can_create_job=True,
            enable_auto_complete_customer_fields=True,
            use_pick_up_status=True,
        )
        cls.driver = DriverFactory(
            merchant=cls.merchant
        )

        CustomerFactory.create_batch(10, merchant=cls.merchant)
        PickupFactory.create_batch(10, merchant=cls.merchant)

    def test_get_customers(self):
        self.client.force_authenticate(self.driver)

        resp = self.client.get('/api/mobile/customers/v1/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], Customer.objects.count())

    def test_get_pickups(self):
        self.client.force_authenticate(self.driver)

        resp = self.client.get('/api/mobile/pickup_customers/v1/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], Pickup.objects.count())
