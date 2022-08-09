import copy
import io
from base64 import b64encode
from datetime import timedelta

from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

import mock
from PIL import Image

from base.factories import DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from tasks.models import Order, OrderStatus
from tasks.tests.factories import OrderFactory


class PickUpStatusTestCase(APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    @classmethod
    def setUpTestData(cls):
        super(PickUpStatusTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory(use_pick_up_status=True, driver_can_create_job=True)
        cls.merchant_no_pickup = MerchantFactory(use_pick_up_status=False)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.manager_no_pickup = ManagerFactory(merchant=cls.merchant_no_pickup)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)
        cls.driver_no_pickup = DriverFactory(merchant=cls.merchant_no_pickup, work_status=WorkStatus.WORKING)
        cls.job_data = {
            'customer': {'name': 'Test Customer'},
            'deliver_address': {
                'address': 'Eaton Gate, UK',
                'location': '51.4938516,-0.1567399',
                'raw_address': 'Eaton Gate, Sloane Square',
            },
            'pickup_address': {
                'address': 'Eaton Gate, 2, UK',
                'location': '51.5938516,-0.1167399',
                'raw_address': 'Eaton Gate, 2 Sloane Square',
            }
        }

    def setUp(self):
        super(PickUpStatusTestCase, self).setUp()
        self.order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.ASSIGNED,
            driver=self.driver
        )
        self.client.force_authenticate(self.driver)

    def change_status(self, order, job_status, resp_status, initiator, driver=None):
        url = '/api/v2/orders/{order_id}/' + ('status' if initiator.is_driver else '')
        method = self.client.put if initiator.is_driver else self.client.patch
        resp = method(url.format(order_id=order.id), {'status': job_status})
        self.assertEqual(resp.status_code, resp_status)
        if status.is_success(resp_status):
            self.assertEqual(resp.data['status'], job_status)

    def test_change_status_to_pick_up(self):
        self.change_status(self.order, OrderStatus.PICK_UP, status.HTTP_200_OK, self.driver)

    def test_change_status_to_pick_up_by_manager(self):
        self.client.force_authenticate(self.manager)
        self.change_status(self.order, OrderStatus.PICK_UP, status.HTTP_200_OK, self.manager)

    def test_cant_change_status_to_pick_up(self):
        order = OrderFactory(merchant=self.merchant_no_pickup, manager=self.manager_no_pickup,
                             status=OrderStatus.ASSIGNED, driver=self.driver_no_pickup)
        self.client.force_authenticate(self.driver_no_pickup)
        self.change_status(order, OrderStatus.PICK_UP, status.HTTP_400_BAD_REQUEST, self.driver_no_pickup)
        self.client.force_authenticate(self.manager_no_pickup)
        self.change_status(order, OrderStatus.PICK_UP, status.HTTP_400_BAD_REQUEST, self.manager_no_pickup)

    def test_use_pickup_only_with_pickup_address(self):
        order_no_pickup_address = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.ASSIGNED,
            driver=self.driver,
            pickup_address=None,
        )
        self.change_status(order_no_pickup_address, OrderStatus.PICK_UP, status.HTTP_400_BAD_REQUEST, self.driver)
        self.client.force_authenticate(self.manager)
        resp = self.client.patch('/api/v2/orders/%s/' % (order_no_pickup_address.id,),
                                 {'pickup_address': {'location': {'lat': 23.123, 'lng': 23.123}}})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.driver)
        self.change_status(order_no_pickup_address, OrderStatus.PICK_UP, status.HTTP_200_OK, self.driver)

    def test_dont_use_pickup_status(self):
        order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.NOT_ASSIGNED,
            driver=None,
        )
        self.client.force_authenticate(self.manager)
        resp = self.client.patch('/api/v2/orders/%s/' % (order.id,),
                                 {'status': OrderStatus.ASSIGNED, 'driver': self.driver.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.driver)
        self.change_status(self.order, OrderStatus.IN_PROGRESS, status.HTTP_200_OK, self.driver)

    def test_cant_delete_pickup_address_with_pickup_status(self):
        def _check_cant_delete_pickup_address():
            self.client.force_authenticate(self.manager)
            delete_resp = self.client.patch('/api/v2/orders/%s/' % (self.order.id,), {'pickup_address': None})
            self.assertEqual(delete_resp.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertIsNotNone(self.order.pickup_address)
        self.client.force_authenticate(self.driver)
        self.change_status(self.order, OrderStatus.PICK_UP, status.HTTP_200_OK, self.driver)
        _check_cant_delete_pickup_address()
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.pickup_address)
        self.client.force_authenticate(self.driver)
        self.change_status(self.order, OrderStatus.IN_PROGRESS, status.HTTP_200_OK, self.driver)
        _check_cant_delete_pickup_address()
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.pickup_address)

    def test_can_delete_pickup_address(self):
        self.assertIsNotNone(self.order.pickup_address)
        self.client.force_authenticate(self.manager)
        resp = self.client.patch('/api/v2/orders/%s/' % (self.order.id,), {'pickup_address': None})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.pickup_address)

    def test_calculate_picked_up_time(self):
        now = timezone.now()
        times = [(OrderStatus.PICK_UP, now + timedelta(minutes=10)),
                 (OrderStatus.IN_PROGRESS, now + timedelta(minutes=20))]

        with mock.patch('django.utils.timezone.now') as mock_now:
            for to_status, change_time in times:
                mock_now.return_value = change_time
                self.change_status(self.order, to_status, status.HTTP_200_OK, self.driver)
        self.order.refresh_from_db()
        self.assertEqual(self.order.started_at, times[0][1])
        self.assertEqual(self.order.picked_up_at, times[1][1])

    def test_create_job_with_pickup_address(self):
        self._create_job(self.manager)

    def test_create_job_with_pickup_address_driver(self):
        self._create_job(self.driver)

    def _create_job(self, user):
        self.client.force_authenticate(user)
        resp = self.client.post('/api/orders/', data=self.job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.get(order_id=resp.data['order_id'])
        self.assertIsNotNone(order.pickup_address)

    def test_create_order_with_pickup_by_driver(self):
        pickup_data = {
            "name": "test pickup",
            "email": "pickup@testemail.com"
        }
        data = copy.deepcopy(self.job_data)
        data.update({'pickup': pickup_data})

        self.client.force_authenticate(self.driver)

        resp = self.client.post('/api/orders/', data=data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(order_id=resp.data['order_id']).first()
        self.assertIsNotNone(order.pickup)
        self.assertEqual(order.pickup.name, pickup_data["name"])
        self.assertEqual(order.pickup.email, pickup_data["email"])


def get_pick_up_confirmation_data():
    f = io.BytesIO()
    image = Image.new("RGBA", size=(50, 50))
    image.save(f, "png")
    f.seek(0)
    confirmation_signature = b64encode(f.getvalue())
    confirmation_photos = [{"image": confirmation_signature, }]
    confirmation_comment = "Test pick up confirmation comment"
    return {"pick_up_confirmation_signature": confirmation_signature,
            "pick_up_confirmation_photos": confirmation_photos,
            "pick_up_confirmation_comment": confirmation_comment}


class PickUpConfirmationTestCase(APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    @classmethod
    def setUpTestData(cls):
        super(PickUpConfirmationTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory(use_pick_up_status=True, enable_pick_up_confirmation=True)
        cls.merchant_no_confirm = MerchantFactory(use_pick_up_status=True, enable_pick_up_confirmation=False)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.manager_no_confirm = ManagerFactory(merchant=cls.merchant_no_confirm)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)
        cls.driver_no_confirm = DriverFactory(merchant=cls.merchant_no_confirm, work_status=WorkStatus.WORKING)
        cls.confirm_data = get_pick_up_confirmation_data()

    def send(self, order, confirm_status):
        resp = self.client.put('/api/v2/orders/{order_id}/status'.format(order_id=order.id),
                               {'status': OrderStatus.PICK_UP})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], OrderStatus.PICK_UP)
        resp = self.client.put('/api/v2/orders/{order_id}/status'.format(order_id=order.id),
                               dict(status=confirm_status, **self.confirm_data))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['status'], confirm_status)
        return resp

    def test_can_confirm(self):
        order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.ASSIGNED,
            driver=self.driver
        )
        self.client.force_authenticate(self.driver)
        in_progress_resp = self.send(order, OrderStatus.IN_PROGRESS)
        order.refresh_from_db()
        self.assertEqual(order.pick_up_confirmation_photos.all().count(), 1)
        self.assertEqual(order.pick_up_confirmation_comment, self.confirm_data['pick_up_confirmation_comment'])
        self.assertIsNotNone(in_progress_resp.json()['pick_up_confirmation_signature'])

    def test_can_not_confirm(self):
        order = OrderFactory(
            merchant=self.merchant_no_confirm,
            manager=self.manager_no_confirm,
            status=OrderStatus.ASSIGNED,
            driver=self.driver_no_confirm
        )
        self.client.force_authenticate(self.driver_no_confirm)
        in_progress_resp = self.send(order, OrderStatus.IN_PROGRESS)
        order.refresh_from_db()
        self.assertEqual(order.pick_up_confirmation_photos.all().count(), 0)
        self.assertIsNone(in_progress_resp.json()['pick_up_confirmation_signature'])

    def test_can_confirm_picked_up(self):
        order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.ASSIGNED,
            driver=self.driver
        )
        self.client.force_authenticate(self.driver)
        in_progress_resp = self.send(order, OrderStatus.PICKED_UP)
        order.refresh_from_db()
        self.assertEqual(order.pick_up_confirmation_photos.all().count(), 1)
        self.assertEqual(order.pick_up_confirmation_comment, self.confirm_data['pick_up_confirmation_comment'])
        self.assertIsNotNone(in_progress_resp.json()['pick_up_confirmation_signature'])
