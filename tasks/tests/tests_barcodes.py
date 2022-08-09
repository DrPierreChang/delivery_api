from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from merchant.models import Merchant
from reporting.models import Event
from tasks.mixins.order_status import OrderStatus
from tasks.models import Barcode, Order
from tasks.tests.factories import BarcodesFactory, OrderFactory
from webhooks.factories import MerchantAPIKeyFactory


class JobBarcodesTestsCase(APITestCase):
    api_url = '/api/orders/'
    external_api_url = '/api/webhooks/jobs{path}?key={key}'

    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(
            option_barcodes=Merchant.TYPES_BARCODES.both
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

        cls.job_data = {
            "customer": {
                "name": "John Sykes"
            },
            "deliver_address": {
                "address": "Sydney, AU",
                "location": "-33.874904,151.207976"
            }
        }

    def setUp(self):
        self.job_with_barcodes = OrderFactory(
            manager=self.manager,
            merchant=self.merchant
        )
        self.barcodes = BarcodesFactory.create_batch(order=self.job_with_barcodes, size=3)

    def test_create_job_with_barcodes(self):
        barcodes = [
            {
                "code_data": "123456",
                "required": True
            },
            {
                "code_data": "hello world!",
                "required": False
            },
            {
                "code_data": "qwerty",
            }
        ]
        self.job_data['barcodes'] = barcodes
        self.client.force_authenticate(self.manager)
        response = self.client.post(self.api_url, self.job_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_barcodes = response.json()['barcodes']
        self.assertEqual(len(barcodes), len(created_barcodes))

    def test_create_job_with_barcodes_through_external_api(self):
        barcodes = [
            {
                "code_data": "123456",
                "required": True
            },
            {
                "code_data": "hello world!",
                "required": False
            },
            {
                "code_data": "qwerty",
            }
        ]

        url = self.external_api_url.format(path='', key=self.merchant_api_key.key)
        external_id = '1234'
        self.job_data['barcodes'] = barcodes
        self.job_data['external_id'] = external_id
        response = self.client.post(url, self.job_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.filter(external_job__external_id=external_id)
        self.assertTrue(order.exists())
        order = order.last()
        self.assertEqual(len(barcodes), order.barcodes.count())

    def test_update_barcodes(self):
        barcode = self.barcodes[0]
        new_barcode_data = [{
            "code_data": barcode.code_data + "New",
            "required": True,
            "scanned_at_the_warehouse": True,
            "scanned_upon_delivery": True,
            "id": barcode.id
        }]
        url = self.api_url + str(self.job_with_barcodes.order_id)
        self.client.force_authenticate(self.manager)
        response = self.client.patch(url, {'barcodes': new_barcode_data})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_barcode = self.job_with_barcodes.barcodes.get(id=barcode.id)
        self.assertEqual(updated_barcode.code_data, new_barcode_data[0]['code_data'])
        self.assertTrue(updated_barcode.required)
        self.assertTrue(updated_barcode.scanned_at_the_warehouse)
        self.assertTrue(updated_barcode.scanned_upon_delivery)

    def test_add_new_barcode_to_existing_job(self):
        new_barcode_data = [
            {
                "code_data": "New barcode",
                "required": True
            }
        ]
        url = self.api_url + str(self.job_with_barcodes.order_id)
        barcodes_num = self.job_with_barcodes.barcodes.count()
        self.client.force_authenticate(self.manager)
        response = self.client.patch(url, {'barcodes': new_barcode_data})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        current_barcodes_num = self.job_with_barcodes.barcodes.count()
        self.assertEqual(current_barcodes_num - barcodes_num, len(new_barcode_data))
        self.assertTrue(self.job_with_barcodes.barcodes.filter(**new_barcode_data[0]).exists())

    def test_remove_barcode_from_job(self):
        barcode = self.barcodes[0]
        barcodes_to_remove = [{"id": barcode.id}]
        url = self.api_url + str(self.job_with_barcodes.order_id)
        barcodes_num = self.job_with_barcodes.barcodes.count()
        self.client.force_authenticate(self.manager)
        response = self.client.patch(url, {'barcodes': barcodes_to_remove})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        current_barcodes_num = self.job_with_barcodes.barcodes.count()
        self.assertEqual(barcodes_num - current_barcodes_num, len(barcodes_to_remove))
        self.assertFalse(self.job_with_barcodes.barcodes.filter(id=barcode.id))


class JobBarcodesScannedTwiceTestsCase(APITestCase):
    api_url = '/api/orders/'
    external_api_url = '/api/webhooks/jobs/{path}?key={key}'

    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(option_barcodes=Merchant.TYPES_BARCODES.both)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)
        cls.apikey = MerchantAPIKeyFactory(creator=cls.manager, merchant=cls.merchant, available=True)
        cls.external_id = '1111'
        cls.job_data = {
            "external_id": cls.external_id,
            "customer": {
                "name": "John Sykes"
            },
            "deliver_address": {
                "address": "Sydney, AU"
            }
        }

    def setUp(self):
        self.client.post('/api/webhooks/jobs/?key=%s' % self.apikey.key, data=self.job_data)
        self.order = Order.objects.get(external_job__external_id=self.external_id)
        self.barcodes = BarcodesFactory.create_batch(order=self.order, size=3)

    def test_scanned_before_delivery_barcodes(self):
        new_barcodes_data = [{
            "code_data": barcode.code_data,
            "scanned_at_the_warehouse": True,
            "id": barcode.id
        } for barcode in self.barcodes]
        url = self.external_api_url.format(path=self.order.external_job.external_id, key=self.apikey.key)
        response = self.client.patch(url, {'barcodes': new_barcodes_data})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_barcodes = self.order.barcodes.all()
        self.assertTrue(all(barcode.scanned_at_the_warehouse for barcode in updated_barcodes))

    def test_scanned_after_delivery_barcodes(self):
        new_barcodes_data = [{
            "code_data": barcode.code_data,
            "scanned_upon_delivery": True,
            "id": barcode.id
        } for barcode in self.barcodes]
        url = self.external_api_url.format(path=self.order.external_job.external_id, key=self.apikey.key)
        response = self.client.patch(url, {'barcodes': new_barcodes_data})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_barcodes = self.order.barcodes.all()
        self.assertTrue(all(barcode.scanned_upon_delivery for barcode in updated_barcodes))

    def test_adding_non_unique_barcodes(self):
        new_barcodes_data = [{
            "code_data": self.barcodes[2].code_data,
            "id": self.barcodes[0].id
        }, {
            "code_data": 'test_code_data',
            "id": self.barcodes[1].id
        }]
        url = self.external_api_url.format(path=self.order.external_job.external_id, key=self.apikey.key)
        response = self.client.patch(url, {'barcodes': new_barcodes_data})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class BarcodeScanningFromMultipleOrdersTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(option_barcodes=Merchant.TYPES_BARCODES.both)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)
        cls.order = OrderFactory(
            merchant=cls.merchant,
            manager=cls.manager,
            driver=cls.driver,
            status=OrderStatus.ASSIGNED,
            pickup_address=None,
        )
        cls.order_2 = OrderFactory(
            merchant=cls.merchant,
            manager=cls.manager,
            driver=cls.driver,
            status=OrderStatus.PICK_UP,
        )
        cls.order_3 = OrderFactory(
            merchant=cls.merchant,
            manager=cls.manager,
            driver=cls.driver,
            status=OrderStatus.IN_PROGRESS,
            pickup_address=None,
        )
        cls.order_4 = OrderFactory(
            merchant=cls.merchant,
            manager=cls.manager,
            driver=cls.driver,
            status=OrderStatus.ASSIGNED,
        )
        cls.order_5 = OrderFactory(
            merchant=cls.merchant,
            manager=cls.manager,
            driver=cls.driver,
            status=OrderStatus.PICK_UP,
            pickup_address=None,
        )

        cls.barcodes = (BarcodesFactory.create_batch(order=cls.order, size=1)
                        + BarcodesFactory.create_batch(order=cls.order_2, size=1)
                        + BarcodesFactory.create_batch(order=cls.order_3, size=1)
                        + BarcodesFactory.create_batch(order=cls.order_4, size=1)
                        + BarcodesFactory.create_batch(order=cls.order_5, size=3))

    def test_get_orders_by_barcode_before_delivery(self):
        self.client.force_authenticate(self.driver)
        old_events_ids = list(Event.objects.values_list('id', flat=True))
        response = self.client.post('/api/v2/orders/scan_barcodes/', {'barcodes': [self.barcodes[0].code_data]})

        # checking that only one order data came
        self.assertEqual(len(response.data), 1)

        # checking that only the desired barcode has been scanned
        modified_barcode = response.data[0]['barcodes'][0]
        self.assertEqual(modified_barcode['scanned_at_the_warehouse'], True)
        self.assertEqual(
            Barcode.objects.filter(scanned_at_the_warehouse=True).exclude(id=modified_barcode['id']).exists(), False
        )
        self.assertEqual(Event.objects.exclude(id__in=old_events_ids).count(), 1)

    def test_get_pick_up_orders_by_barcode_before_delivery(self):
        self.client.force_authenticate(self.driver)
        old_events_ids = list(Event.objects.values_list('id', flat=True))
        response = self.client.post('/api/v2/orders/scan_barcodes/', {'barcodes': [self.barcodes[1].code_data]})

        # checking that only one order data came
        self.assertEqual(len(response.data), 1)

        # checking that only the desired barcode has been scanned
        modified_barcode = response.data[0]['barcodes'][0]
        self.assertEqual(modified_barcode['scanned_at_the_warehouse'], True)
        self.assertEqual(
            Barcode.objects.filter(scanned_at_the_warehouse=True).exclude(id=modified_barcode['id']).exists(), False
        )
        self.assertEqual(Event.objects.exclude(id__in=old_events_ids).count(), 1)

    def test_get_orders_by_barcode_after_delivery(self):
        self.client.force_authenticate(self.driver)
        old_events_ids = list(Event.objects.values_list('id', flat=True))
        response = self.client.post('/api/v2/orders/scan_barcodes/', {
            'barcodes': [self.barcodes[2].code_data],
            'changed_in_offline': True,
        })

        # checking that only one order data came
        self.assertEqual(len(response.data), 1)

        # checking that only the desired barcode has been scanned
        modified_barcode = response.data[0]['barcodes'][0]
        self.assertEqual(modified_barcode['scanned_upon_delivery'], True)
        self.assertFalse(Barcode.objects.filter(scanned_upon_delivery=True).exclude(id=modified_barcode['id']).exists())
        order = self.barcodes[2].order
        order.refresh_from_db()
        self.assertTrue(order.changed_in_offline)
        self.assertEqual(Event.objects.exclude(id__in=old_events_ids).count(), 1)

    def test_get_orders_by_wrong_barcode(self):
        self.client.force_authenticate(self.driver)
        response = self.client.post('/api/v2/orders/scan_barcodes/', {
            'barcodes': ['wrong_barcode'],
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_scanned_barcodes(self):
        self.client.force_authenticate(self.driver)

        order = self.order_5
        order.status = OrderStatus.ASSIGNED
        order.driver = self.driver
        order.scanned_at_the_warehouse = False
        order.scanned_upon_delivery = False
        order.save()
        barcode = order.barcodes.first()
        response = self.client.put('/api/v2/orders/' + str(order.id) + '/barcodes/', [
            {
                "id": barcode.id,
                "scanned": True
            }
        ])

        self.assertEqual(len(response.data), 1)
        modified_barcode = response.data[0]
        self.assertEqual(modified_barcode['scanned_at_the_warehouse'], True)
        self.assertEqual(modified_barcode['scanned_upon_delivery'], False)
        self.assertEqual(modified_barcode['scanned'], True)

        order.status = OrderStatus.IN_PROGRESS
        order.driver = self.driver
        order.save()

        response = self.client.put('/api/v2/orders/' + str(order.id) + '/barcodes/', [
            {
                "id": barcode.id,
                "scanned": True
            }
        ])

        self.assertEqual(len(response.data), 1)
        modified_barcode = response.data[0]
        self.assertEqual(modified_barcode['scanned_upon_delivery'], True)
        self.assertEqual(modified_barcode['scanned'], True)
