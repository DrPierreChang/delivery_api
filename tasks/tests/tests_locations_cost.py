from datetime import datetime

from django.db import models

from rest_framework import status
from rest_framework.test import APITestCase

from constance import config
from mock import patch

from base.factories import DriverFactory
from base.utils import get_fuzzy_location
from driver.models import DriverLocation
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from merchant.models import Merchant
from radaro_utils import countries
from radaro_utils.helpers import to_timestamp
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order
from tasks.tests.factories import OrderFactory


class LocationsCostTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(countries=[countries.AUSTRALIA, ], use_way_back_status=True,
                                       use_pick_up_status=True, path_processing=Merchant.ANIMATION_WITH_SNAP_TO_ROADS)

    def setUp(self):
        self.driver = DriverFactory(merchant=self.merchant, work_status=WorkStatus.WORKING)
        self.client.force_authenticate(self.driver)
        self.google_requests = 0

    def send_locations(self, count=1):
        # This data means nothing. Just for test
        snap_to_roads_mock_return_value = [{'location': {'latitude': 53.9025642423, 'longitude': 27.4899480662}},
                                           {'location': {'latitude': 53.9024491053, 'longitude': 27.4880723055}}]
        directions_mock_return_value = [{'overview_polyline': {'points': '_z~gIecxfD^dPd@hSX|LjEN'}}]
        assert count > 0
        for _ in range(count):
            with patch('routing.google.RadaroGoogleMapsClient.snap_to_roads') as snap_to_roads_mock:
                with patch('routing.google.RadaroGoogleMapsClient.directions') as directions_mock:
                    snap_to_roads_mock.return_value = snap_to_roads_mock_return_value
                    directions_mock.return_value = directions_mock_return_value
                    resp = self.client.post('/api/drivers/me/locations', data={
                        "location": get_fuzzy_location(),
                        "speed": 10,
                        "accuracy": 20.0,
                    })
                    self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
                    self.google_requests += int(snap_to_roads_mock.called)
                    self.google_requests += int(directions_mock.called)

    def _change_status(self, order_status, order):
        resp = self.client.put('/api/orders/{}'.format(order.order_id) + '/status', data={'status': order_status})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def _google_requests_in_db(self):
        return DriverLocation.objects.aggregate(sum=models.Sum('google_requests'))['sum']

    def change_status(self, order_status, order):
        if order_status == OrderStatus.DELIVERED:
            with patch('routing.google.RadaroGoogleMapsClient.snap_to_roads') as snap_to_roads_mock:
                with patch('routing.google.RadaroGoogleMapsClient.directions') as directions_mock:
                    snap_to_roads_mock.return_value = [{'location': {'latitude': 52.123452, 'longitude': 52.123452}}]
                    directions_mock.return_value = [{'overview_polyline': {'points': 'yg_}Hium}H'}}]
                    return self._change_status(order_status, order)
        return self._change_status(order_status, order)

    def assert_google_requests_count(self):
        self.assertEqual(self._google_requests_in_db(), self.google_requests)

    def test_location_processing_price(self):
        orders = OrderFactory.create_batch(size=2, merchant=self.merchant, status=OrderStatus.ASSIGNED,
                                           driver=self.driver)
        self.send_locations(2)
        self.change_status(OrderStatus.IN_PROGRESS, orders[0])
        self.send_locations(20)
        self.change_status(OrderStatus.DELIVERED, orders[0])
        self.assertEqual(float(Order.objects.get(id=orders[0].id).locations_cost), 0.02)
        self.merchant.location_processing_price = 0.0004
        self.merchant.save()
        self.change_status(OrderStatus.IN_PROGRESS, orders[1])
        self.send_locations(25)
        self.change_status(OrderStatus.DELIVERED, orders[1])
        self.assertEqual(float(Order.objects.get(id=orders[1].id).locations_cost), 0.02)
        self.assert_google_requests_count()

    def test_parallel_jobs(self):
        orders = OrderFactory.create_batch(size=2, merchant=self.merchant, status=OrderStatus.ASSIGNED,
                                           driver=self.driver)
        self.send_locations(3)
        cost0, cost1 = 0., 0.
        self.change_status(OrderStatus.IN_PROGRESS, orders[0])
        self.send_locations(20)
        cost0 += 0.02
        self.change_status(OrderStatus.IN_PROGRESS, orders[1])
        self.send_locations(20)
        cost0 += 0.01
        cost1 += 0.01
        self.change_status(OrderStatus.DELIVERED, orders[1])
        self.send_locations(20)
        cost0 += 0.02
        self.change_status(OrderStatus.DELIVERED, orders[0])
        self.assertEqual(float(Order.objects.get(id=orders[0].id).locations_cost), cost0)
        self.assertEqual(float(Order.objects.get(id=orders[1].id).locations_cost), cost1)
        self.assert_google_requests_count()

    def test_parallel_jobs_with_pick_up(self):
        orders = OrderFactory.create_batch(size=2, merchant=self.merchant, status=OrderStatus.ASSIGNED,
                                           driver=self.driver)
        self.send_locations(1)
        cost0, cost1 = 0., 0.
        self.change_status(OrderStatus.IN_PROGRESS, orders[0])
        self.send_locations(20)
        cost0 += 0.02
        self.change_status(OrderStatus.PICK_UP, orders[1])
        self.send_locations(10)
        cost0 += 0.01
        self.change_status(OrderStatus.IN_PROGRESS, orders[1])
        self.send_locations(20)
        cost0 += 0.01
        cost1 += 0.01
        self.change_status(OrderStatus.DELIVERED, orders[1])
        self.send_locations(20)
        cost0 += 0.02
        self.change_status(OrderStatus.DELIVERED, orders[0])
        self.assertEqual(float(Order.objects.get(id=orders[0].id).locations_cost), cost0)
        self.assertEqual(float(Order.objects.get(id=orders[1].id).locations_cost), cost1)
        self.assert_google_requests_count()

    def test_parallel_jobs_with_way_back(self):
        orders = OrderFactory.create_batch(size=2, merchant=self.merchant, status=OrderStatus.ASSIGNED,
                                           driver=self.driver)
        self.send_locations(1)
        cost0, cost1 = 0., 0.
        self.change_status(OrderStatus.IN_PROGRESS, orders[0])
        self.send_locations(20)
        cost0 += 0.02
        self.change_status(OrderStatus.IN_PROGRESS, orders[1])
        self.send_locations(20)
        cost0 += 0.01
        cost1 += 0.01
        self.change_status(OrderStatus.WAY_BACK, orders[1])
        self.send_locations(10)
        cost0 += 0.01
        self.change_status(OrderStatus.DELIVERED, orders[1])
        self.send_locations(20)
        cost0 += 0.02
        self.change_status(OrderStatus.DELIVERED, orders[0])
        self.assertEqual(float(Order.objects.get(id=orders[0].id).locations_cost), cost0)
        self.assertEqual(float(Order.objects.get(id=orders[1].id).locations_cost), cost1)
        self.assert_google_requests_count()

    def test_dont_count_google_requests_after_completed_job(self):
        order = OrderFactory(merchant=self.merchant, status=OrderStatus.ASSIGNED, driver=self.driver)
        self.send_locations(1)
        self.change_status(OrderStatus.IN_PROGRESS, order)
        self.send_locations(2)
        old_count = self._google_requests_in_db()
        self.change_status(OrderStatus.DELIVERED, order)
        self.assertEqual(old_count, self._google_requests_in_db())
        self.assert_google_requests_count()

    def test_locations_cost_function(self):
        import decimal

        from tasks.utils import calculate_locations_cost

        order = OrderFactory(merchant=self.merchant, status=OrderStatus.ASSIGNED, driver=self.driver)
        self.send_locations(1)
        self.change_status(OrderStatus.IN_PROGRESS, order)
        self.send_locations(1)
        self.change_status(OrderStatus.DELIVERED, order)
        order = Order.objects.get(id=order.id)
        order.serialized_track = []
        self.assertEqual(calculate_locations_cost(order), decimal.Decimal('0'))

        order = OrderFactory(merchant=self.merchant, status=OrderStatus.ASSIGNED, driver=self.driver)
        self.send_locations(1)
        self.change_status(OrderStatus.IN_PROGRESS, order)
        location_time = float(to_timestamp(datetime.utcnow()))
        self.send_locations(1)
        self.change_status(OrderStatus.DELIVERED, order)
        order = Order.objects.get(id=order.id)
        order.serialized_track = [
            {'timestamp': location_time},  # without fields in_progress_orders, google_requests, google_request_cost
            {'in_progress_orders': 1, 'google_requests': 2, 'google_request_cost': 0.1, 'timestamp': location_time},
            {'in_progress_orders': 5, 'google_requests': 10, 'google_request_cost': '0.005',
             'timestamp': location_time},
            {'in_progress_orders': 0, 'google_requests': None, 'google_request_cost': None,
             'timestamp': location_time},
        ]
        self.assertEqual(calculate_locations_cost(order), decimal.Decimal('0.21'))

    def test_processing_only_in_progress_locations(self):
        # This data means nothing. Just for test
        snap_to_roads_mock_return_value = [{'location': {'latitude': 52.123452, 'longitude': 52.123452}}]
        directions_mock_return_value = [{'overview_polyline': {'points': '_z~gIecxfD^dPd@hSX|LjEN'}}]

        def send_location():
            with patch('routing.google.RadaroGoogleMapsClient.snap_to_roads') as snap_to_roads_mock:
                with patch('routing.google.RadaroGoogleMapsClient.directions') as directions_mock:
                    snap_to_roads_mock.return_value = snap_to_roads_mock_return_value
                    directions_mock.return_value = directions_mock_return_value
                    resp = self.client.post('/api/drivers/me/locations', data={
                        "location": get_fuzzy_location()
                    })
                    self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
                    self.assertEqual(snap_to_roads_mock.called, driver_is_in_progress)
                    return resp.data['id']

        order = OrderFactory(merchant=self.merchant, status=OrderStatus.ASSIGNED, driver=self.driver)
        driver_is_in_progress = False
        send_location()
        self.change_status(OrderStatus.IN_PROGRESS, order)
        driver_is_in_progress = True
        location_id = send_location()
        self.change_status(OrderStatus.WAY_BACK, order)
        driver_is_in_progress = False
        send_location()
        self.change_status(OrderStatus.DELIVERED, order)
        send_location()
        driver_location = DriverLocation.objects.get(id=location_id)
        self.assertEqual(float(driver_location.google_request_cost), config.DEFAULT_LOCATION_PROCESSING_COST)
        self.assertEqual(driver_location.google_requests, 2)
        self.assertEqual(driver_location.in_progress_orders, 1)
