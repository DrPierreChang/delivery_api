from rest_framework import status

from reporting.models import Event
from tasks.mixins.order_status import OrderStatus
from tasks.models import ConcatenatedOrder, Order
from tasks.tests.base_test_cases import BaseOrderTestCase


class MobileOrderGeofenceTestCase(BaseOrderTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.merchant.use_pick_up_status = True
        cls.merchant.geofence_settings = cls.merchant.UPON_EXITING
        cls.merchant.save()

    def setUp(self):
        self.order = self.create_default_order_with_status()
        self.client.force_authenticate(self.driver)

    def test_enter_pickup_geofence_wrong_status(self):
        resp = self.client.patch('/api/mobile/orders/v1/{}/geofence/'.format(self.order.id), {'geofence_entered': True})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pickup_geofence_workflow(self):
        self.client.patch('/api/mobile/orders/v1/{}'.format(self.order.id), {'status': OrderStatus.PICK_UP})

        resp = self.client.patch('/api/mobile/orders/v1/{}/geofence/'.format(self.order.id), {'geofence_entered': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        order = Order.objects.filter(id=self.order.id).first()
        self.assertEqual(order.pickup_geofence_entered, True)

        resp = self.client.patch('/api/mobile/orders/v1/{}/geofence/'.format(self.order.id), {'geofence_entered': True})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        resp = self.client.patch('/api/mobile/orders/v1/{}/geofence/'.format(self.order.id), {'geofence_entered': False})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.pickup_geofence_entered, False)
        self.assertIsNotNone(order.time_inside_pickup_geofence)

    def test_order_completion_with_geofence(self):
        self.client.patch('/api/mobile/orders/v1/{}'.format(self.order.id), {'status': OrderStatus.IN_PROGRESS})

        resp = self.client.patch('/api/mobile/orders/v1/{}/geofence/'.format(self.order.id), {'geofence_entered': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        order = Order.objects.filter(id=self.order.id).first()
        self.assertEqual(order.geofence_entered, True)

        resp = self.client.patch('/api/mobile/orders/v1/{}/geofence/'.format(self.order.id), {'geofence_entered': False})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.geofence_entered, False)
        self.assertIsNotNone(order.time_inside_geofence)
        self.assertIsNotNone(order.time_at_job)
        self.assertEqual(order.status, OrderStatus.DELIVERED)
        self.assertTrue(order.is_completed_by_geofence)


class MobileConcatenatedOrderGeofenceTestCase(BaseOrderTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.merchant.enable_concatenated_orders = True
        cls.merchant.driver_can_create_job = True
        cls.merchant.use_pick_up_status = True
        cls.merchant.geofence_settings = cls.merchant.UPON_EXITING
        cls.merchant.save()

    def setUp(self):
        self.concatenated_order = self.prepare_concatenated_order()

    def prepare_concatenated_order(self):
        job_data = {
            'deliver_address': {
                'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                'location': {
                    'lat': 53.91254758887667,
                    'lng': 27.543441765010357,
                },
            },
            'customer': {
                'name': 'Test20',
            },
            'pickup_address': {
                'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                'location': {
                    'lat': 53.91254758887667,
                    'lng': 27.543441765010357,
                },
            },
            'pickup': {
                'name': 'Test20',
            },
            'driver_id': self.driver.id
        }
        path = '/api/mobile/orders/v1/'
        self.client.force_authenticate(self.driver)
        resp = self.client.post(path, data=job_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resp = self.client.post(path, data=job_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).last()
        self.assertIsNotNone(concatenated_order)
        self.assertEqual(concatenated_order.status, ConcatenatedOrder.ASSIGNED)
        return concatenated_order

    def test_enter_geofence_wrong_status(self):
        co_path = f'/api/mobile/concatenated_orders/v1/{self.concatenated_order.id}/'
        self.client.patch(co_path, data={'status': OrderStatus.PICK_UP})
        resp = self.client.patch(co_path + 'geofence/', data={'geofence_entered': True})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_concatenated_order_geofence_workflow(self):
        co_path = f'/api/mobile/concatenated_orders/v1/{self.concatenated_order.id}/'
        self.client.patch(co_path, data={'status': OrderStatus.IN_PROGRESS})

        resp = self.client.patch(co_path + 'geofence/', data={'geofence_entered': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.concatenated_order.refresh_from_db()
        self.assertEqual(self.concatenated_order.geofence_entered, True)
        for order in self.concatenated_order.orders.all():
            self.assertEqual(order.geofence_entered, True)

        resp = self.client.patch(co_path + 'geofence/', data={'geofence_entered': False})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.concatenated_order.refresh_from_db()
        self.assertEqual(self.concatenated_order.geofence_entered, False)
        self.assertEqual(self.concatenated_order.status, ConcatenatedOrder.DELIVERED)
        self.assertTrue(self.concatenated_order.is_completed_by_geofence)
        self.assertIsNotNone(self.concatenated_order.time_inside_geofence)
        self.assertIsNotNone(self.concatenated_order.time_at_job)
        for order in self.concatenated_order.orders.all():
            self.assertEqual(order.geofence_entered, False)
            self.assertIsNotNone(order.time_inside_geofence)
            self.assertIsNotNone(order.time_at_job)
            self.assertTrue(order.is_completed_by_geofence)

        # geofence events are created for parent order only
        self.assertEqual(self.concatenated_order.events
                         .filter(event=Event.CHANGED, field='geofence_entered').count(), 2)
        for order in self.concatenated_order.orders.all():
            self.assertEqual(order.events.filter(event=Event.CHANGED, field='geofence_entered').count(), 0)
