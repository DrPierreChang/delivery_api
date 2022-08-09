from django.test import override_settings

from rest_framework import status
from rest_framework.test import APITestCase

import mock

from base.factories import DriverFactory, ManagerFactory
from base.utils import get_fuzzy_location
from merchant.factories import HubFactory, MerchantFactory
from route_optimisation.const import MerchantOptimisationTypes
from route_optimisation.models import DriverRoute, RoutePoint
from tasks.models import Order
from webhooks.factories import MerchantAPIKeyFactory


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class ExternalRouteOptimizationTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(route_optimization=MerchantOptimisationTypes.PTV_SMARTOUR_EXPORT)
        cls.other_merchant = MerchantFactory(route_optimization=MerchantOptimisationTypes.PTV_SMARTOUR_EXPORT)
        cls.driver = DriverFactory(merchant=cls.merchant)
        cls.other_driver = DriverFactory(merchant=cls.other_merchant)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.hub = HubFactory(merchant=cls.merchant)
        cls.apikey = MerchantAPIKeyFactory(creator=cls.manager, merchant=cls.merchant)

    def setUp(self):
        self.external_id = 'test-ext-job'
        data = {
            'external_id': self.external_id,
            'customer': {
                'name': 'new customer'
            },
            'deliver_address': {
                'location': get_fuzzy_location(),
            }
        }
        self.client.post('/api/webhooks/jobs/?key=%s' % self.apikey.key, data=data)
        self.order = Order.objects.get(external_job__external_id=self.external_id)

    def create_optimization_request(self, data):
        return self.client.post('/api/webhooks/route-optimizations/?key=%s' % self.apikey.key, data=data)

    @mock.patch('route_optimisation.celery_tasks.ptv.ptv_import_calculate_driving_distance.delay')
    def test_create_optimization(self, distance_async):
        optimization_data = {'days': ['2021-03-03'], 'driver_routes': [
            {'driver': self.driver.id, 'route_points': [
                {
                    'end_time': '2021-03-03T18:00:00+00:00',
                    'start_time': '2021-03-03T18:00:00+00:00',
                    'point_content_type': 'hub',
                    'point_object_id': self.hub.id,
                    'number': 1,
                },
                {
                    'end_time': '2021-03-03T20:45:00+00:00',
                    'start_time': '2021-03-03T20:25:00+00:00',
                    'point_content_type': 'order',
                    'point_object_external_id': self.external_id,
                    'number': 2,
                    'service_time': 200,
                }
            ]}
        ]}
        resp = self.create_optimization_request(optimization_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        resp = self.client.get('/api/webhooks/route-optimizations/?key=%s' % self.apikey)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['count'], 1)
        for route_point in RoutePoint.objects.filter(route__optimisation_id=resp.json()['results'][0]['id']):
            self.assertNotEqual(route_point.point_kind, '')
            self.assertIsNotNone(route_point.point_kind)
        for route in DriverRoute.objects.filter(optimisation_id=resp.json()['results'][0]['id']):
            self.assertIsNotNone(route.total_time)
            self.assertIsNotNone(route.driving_time)
            self.assertIsNotNone(route.driving_distance)
        self.assertEqual(distance_async.call_count, 1)
        self.assertEqual(distance_async.call_args[0][0], resp.json()['results'][0]['id'])

    def test_route_optimization_validation_driver(self):
        optimization_data = {'days': ['2018-03-03'], 'driver_routes': [
            {'driver': self.other_driver.id, 'route_points': []}
        ]}
        resp = self.create_optimization_request(optimization_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        optimization_data = {'days': ['2018-03-03'], 'driver_routes': [
            {'driver': self.driver.id, 'route_points': []},
            {'driver': self.other_driver.id, 'route_points': []}
        ]}
        resp = self.create_optimization_request(optimization_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_route_optimization_validation_route_point_fields(self):
        optimization_data = {'days': ['2018-03-03'], 'driver_routes': [
            {'driver': self.driver.id, 'route_points': [
                {'point_content_type': 'unknown type',}
            ]},
        ]}
        resp = self.create_optimization_request(optimization_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        optimization_data = {'days': ['2018-03-03'], 'driver_routes': [
            {'driver': self.driver.id, 'route_points': [
                {'point_content_type': 'hub', 'number': 1}
            ]},
        ]}
        resp = self.create_optimization_request(optimization_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_route_optimization_validation_route_point_ids(self):
        optimization_data = {'days': ['2018-03-03'], 'driver_routes': [
            {'driver': self.driver.id, 'route_points': [
                {'point_content_type': 'order', 'number': 1, 'point_object_external_id': self.external_id+'random'}
            ]},
        ]}
        resp = self.create_optimization_request(optimization_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        optimization_data = {'days': ['2018-03-03'], 'driver_routes': [
            {'driver': self.driver.id, 'route_points': [
                {'point_content_type': 'order', 'number': 1, 'point_object_id': self.order.id + 42}
            ]},
        ]}
        resp = self.create_optimization_request(optimization_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        optimization_data = {'days': ['2018-03-03'], 'driver_routes': [
            {'driver': self.driver.id, 'route_points': [
                {'point_content_type': 'hub', 'number': 1, 'point_object_id': self.hub.id + 42}
            ]},
        ]}
        resp = self.create_optimization_request(optimization_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
