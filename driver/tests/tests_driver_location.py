from __future__ import absolute_import

import copy
from datetime import timedelta

from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

import factory
from mock import patch

from base.factories import DriverFactory, ManagerFactory
from base.models import Member
from base.utils import get_fuzzy_location
from driver.factories import DriverLocationFactory
from driver.models import DriverLocation
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from merchant.models import Merchant
from radaro_utils import countries
from radaro_utils.exceptions import TimeMismatchingError
from radaro_utils.helpers import to_timestamp
from routing.google import GoogleClient
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order
from tasks.tests.factories import OrderFactory, OrderLocationFactory

test_location = get_fuzzy_location()


class DriverLocationTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(countries=[countries.AUSTRALIA, ])

    def setUp(self):
        self.driver = DriverFactory(merchant=self.merchant)

    def test_send_location(self):
        self.client.force_authenticate(self.driver)
        for i in range(2):
            resp = self.client.post('/api/drivers/me/locations', data={
                "location": get_fuzzy_location()
            })
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_get_locations_list(self):
        self.client.force_authenticate(self.driver)
        DriverLocationFactory.create_batch(size=10,
                                           location=factory.LazyFunction(get_fuzzy_location),
                                           member=self.driver)

        resp = self.client.get('/api/drivers/me/locations')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], Member.objects.get(id=self.driver.id).location.count())

    def test_post_locations_list(self):
        self.client.force_authenticate(self.driver)
        locations = [{"location": get_fuzzy_location(), "accuracy": 30} for _ in range(7)]
        for locs in (locations[0], [locations[1]], locations[2:]):
            self.client.post('/api/drivers/me/locations', data=locs)
        resp = self.client.get('/api/drivers/me/locations')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], Member.objects.get(id=self.driver.id).location.count())

    def test_location_improving(self):
        self.merchant.path_processing = Merchant.ANIMATION_WITH_SNAP_TO_ROADS
        self.merchant.save()
        self.driver.work_status = WorkStatus.WORKING
        self.driver.save()
        self.client.force_authenticate(self.driver)

        order_location = '53.901056,27.481664'
        start_driver_location = '53.902480, 27.489963'
        in_progress_locations = ['53.902349,27.488090', '53.902275,27.485708', '53.902147,27.483910',
                                 '53.901301,27.481634']
        # snapped points of `start_driver_location` and `in_progress_locations[0]`
        snap_to_roads_mock_return_value = [{'location': {'latitude': 53.9025642423, 'longitude': 27.4899480662}},
                                           {'location': {'latitude': 53.9024491053, 'longitude': 27.4880723055}}]
        expected_route = '_z~gIecxfD^dPd@hSX|LjEN'
        directions_mock_return_value = [{'overview_polyline': {'points': expected_route}}]

        with patch('routing.google.RadaroGoogleMapsClient.snap_to_roads') as snap_to_roads_mock:
            with patch('routing.google.RadaroGoogleMapsClient.directions') as directions_mock:
                snap_to_roads_mock.return_value = snap_to_roads_mock_return_value
                directions_mock.return_value = directions_mock_return_value

                resp = self.client.post('/api/drivers/me/locations', data=dict(
                    location=start_driver_location, accuracy=20.0,
                ))
                self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
                snap_to_roads_mock.assert_not_called()
                directions_mock.assert_not_called()

                OrderFactory(merchant=self.merchant, status=Order.IN_PROGRESS, driver=self.driver,
                             deliver_address=OrderLocationFactory(location=order_location))

                for i, loc in enumerate(in_progress_locations):
                    resp = self.client.post('/api/drivers/me/locations', data=dict(
                        location=loc, accuracy=20.0,
                    ))
                    self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

                    if i == 0:
                        snap_to_roads_mock.assert_called_once()
                        directions_mock.assert_called_once()
                        self.assertEqual(Member.objects.get(id=self.driver.id).expected_driver_route, expected_route)

                snap_to_roads_mock.assert_called_once()
                directions_mock.assert_called_once()

        last_location = Member.objects.get(id=self.driver.id).location.last()
        self.assertIsNotNone(last_location.improved_location)

    @patch.object(GoogleClient, 'snap_to_roads', return_value=([], 1000))
    def test_path_history(self, patched_google):
        self.merchant.path_processing = Merchant.ANIMATION_WITH_SNAP_TO_ROADS
        self.driver.work_status = WorkStatus.WORKING
        self.merchant.save()
        batch_size = 10
        self.driver.save()
        order = OrderFactory(merchant=self.merchant, status=Order.ASSIGNED, driver=self.driver)
        order_url = '/api/orders/{}'.format(order.order_id)
        self.client.force_authenticate(self.driver)

        resp = self.client.put(order_url + '/status', data={'status': Order.IN_PROGRESS})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        DriverLocationFactory.create_batch(size=batch_size,
                                           location=factory.LazyFunction(get_fuzzy_location),
                                           member=self.driver)
        resp = self.client.put(order_url + '/status', data={'status': Order.DELIVERED})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(Order.objects.get(id=order.id).serialized_track), batch_size)

        resp = self.client.get('/api/order-stats/%s/path_replay?hash=%s' %
                               (order.order_token, order.merchant_daily_hash()))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data.get('route')), batch_size - 1)
        self.assertTrue(patched_google.called)


class OfflineLocationsTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        super(OfflineLocationsTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory(path_processing=Merchant.ANIMATION_WITH_SNAP_TO_ROADS, countries=[countries.AUSTRALIA, ])
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)

        cls.order = OrderFactory(
            merchant=cls.merchant,
            manager=cls.manager,
        )

        cls.fake_now = timezone.now() - timedelta(hours=2)
        cls.initial_locations = [
            {'location': '53.907600,27.515333', 'timestamp': cls.fake_now.replace(microsecond=0) + timedelta(minutes=1)},
            {'location': '53.907610,27.515331', 'timestamp': cls.fake_now.replace(microsecond=0) + timedelta(minutes=2)},
            {'location': '53.907620,27.515332', 'timestamp': cls.fake_now.replace(microsecond=0) + timedelta(minutes=3)},
        ]

    def setUp(self):
        self.client.force_authenticate(self.manager)

        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = self.fake_now
            resp = self.client.patch('/api/orders/%s/' % self.order.order_id, {
                'driver': self.driver.id,
                'status': OrderStatus.ASSIGNED,
            })
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()['driver'], self.driver.id)
            self.assertEqual(resp.json()['status'], OrderStatus.ASSIGNED)

    def test_locations_save(self):
        self.client.force_authenticate(self.driver)
        resp = self.client.post('/api/drivers/me/locations/', map(self.make_data, self.initial_locations))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        for loc in self.initial_locations:
            self.assertTrue(DriverLocation.objects.filter(offline=True, **loc).exists())

    def test_locations_save_situations(self):
        self.client.force_authenticate(self.driver)
        resp = self.client.post('/api/drivers/me/locations/', [{
            'location': '53.907600,27.515333', 'timestamp': "2017-07-20T12:34:56Z"
        }])
        self.assertContains(resp, 'Float is required', status_code=status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        resp = self.client.post('/api/drivers/me/locations/', [{
            'location': '53.907600,27.515333', 'timestamp': "123123123"
        }])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resp = self.client.post('/api/drivers/me/locations/', [])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    # TODO: Add some wrong locations to this test and
    # check that validation works and nothing is saved
    def test_invalid_locations(self):
        self.client.force_authenticate(self.driver)
        new_locs = copy.deepcopy(self.initial_locations)
        new_locs[1]['timestamp'] += timedelta(hours=3)
        resp = self.client.post('/api/latest/drivers/me/locations/', map(self.make_data, new_locs))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['errors'][1]['timestamp'][0]['message'], TimeMismatchingError.message)
        self.client.post('/api/latest/drivers/me/locations/', self.make_data(new_locs[0]))
        new_locs[1]['timestamp'] += timedelta(hours=6)
        resp = self.client.post('/api/latest/drivers/me/locations/', map(self.make_data, new_locs))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(DriverLocation.objects.count(), 1)

    @staticmethod
    def make_data(data):
        return dict(data, timestamp=to_timestamp(data.get('timestamp')))
