import contextlib
from datetime import datetime, time, timedelta
from pprint import pprint

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from rest_framework import status

import mock
import pytz

from base.factories import ManagerFactory
from merchant.factories import MerchantFactory
from route_optimisation.const import OPTIMISATION_TYPES, MerchantOptimisationTypes
from route_optimisation.models import RouteOptimisation
from route_optimisation.tests.factories import (
    DriverRouteFactory,
    OptimisationTaskFactory,
    RouteOptimisationFactory,
    RoutePointFactory,
)
from route_optimisation.tests.test_utils.distance_matrix import TestDiMaCache
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order
from tasks.tests.factories import OrderFactory

from .api_settings import APISettings, SoloAPISettings
from .optimisation_expectation import OptimisationExpectation


@contextlib.contextmanager
def patch_get_distance_matrix_cache():
    distance_matrix_cache = TestDiMaCache()
    pp_distance_matrix_cache = TestDiMaCache(polylines=True)
    patcher = mock.patch(
        'route_optimisation.engine.engine.Engine.get_distance_matrix_cache',
        return_value=distance_matrix_cache
    )
    patcher_polyline = mock.patch(
        'route_optimisation.celery_tasks.optimisation.RunnerBase.get_pp_distance_matrix_cache',
        return_value=pp_distance_matrix_cache
    )
    mock_obj = patcher.start()
    mock_obj_polyline = patcher_polyline.start()
    try:
        yield mock_obj, mock_obj_polyline
    finally:
        patcher.stop()
        patcher_polyline.stop()


class ORToolsMixin:
    api_url = '/api/web/ro/optimisation/'
    individual_api_url = '/api/latest/route-optimization/individual/'
    driver_routes_url = '/api/latest/driver-routes/'
    orders_url = '/api/web/orders/'
    hubs_url = '/api/web/hubs/'
    refresh_solo_api_url = '/api/web/ro/optimisation/{}/refresh/'
    mobile_api_driver_routes_url = '/api/v2/driver-routes/v1/'

    mobile_solo_api_url = '/api/mobile/ro/optimisation/v1/'
    mobile_refresh_solo_api_url = '/api/mobile/ro/routes/v1/{}/refresh/'

    merchant = None
    default_timezone = None
    manager = None
    ro_object = None
    _day = None

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.merchant = MerchantFactory(route_optimization=MerchantOptimisationTypes.OR_TOOLS,
                                       timezone=pytz.timezone('Australia/Melbourne'),
                                       job_service_time=10, pickup_service_time=10,
                                       enable_job_capacity=True,)
        cls.default_timezone = cls.merchant.timezone
        cls.manager = ManagerFactory(merchant=cls.merchant)
        now = timezone.now().astimezone(cls.default_timezone)
        cls._day = (now + timedelta(days=1)).date()

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.manager)

    def tearDown(self):
        super().tearDown()
        if self.merchant.timezone != self.default_timezone:
            self.merchant.timezone = self.default_timezone
            self.merchant.save(update_fields=['timezone'])

    def create_with_validation(self, settings: APISettings):
        options = settings.build_request_options()
        with mock.patch('route_optimisation.celery_tasks.optimisation.Runner.run') as task_mock, \
                mock.patch('route_optimisation.celery_tasks.optimisation.AdvancedRunner.run') as advanced_task_mock:
            resp = self.client.post(self.api_url, dict(type=settings.ro_type, day=str(settings.day), options=options))
            self.assertTrue(task_mock.called or advanced_task_mock.called)
            if task_mock.called:
                self.assertEqual(task_mock.call_args.args[1].id, resp.data['id'])
            if advanced_task_mock.called:
                self.assertEqual(advanced_task_mock.call_args.args[1].id, resp.data['id'])
        return resp.data['id']

    def run_optimisation(self, settings: APISettings, expectation: OptimisationExpectation):
        options = settings.build_request_options()
        with patch_get_distance_matrix_cache():
            resp = self.client.post(self.api_url, dict(type=settings.ro_type, day=str(settings.day), options=options))
        self.assertEqual(resp.status_code, expectation.response_status)
        get = self.client.get(self.api_url + str(resp.data['id']))
        ro_object = RouteOptimisation.objects.get(id=resp.data['id'])
        expectation.check(self, get, ro_object)
        self.ro_object = ro_object
        return resp.data['id']

    def run_solo_optimisation(self, settings: SoloAPISettings, expectation: OptimisationExpectation):
        request_data = settings.build_solo_request_data()
        self.client.force_authenticate(settings.initiator_driver)
        creation_time = timezone.now().astimezone(self.merchant.timezone).replace(
            month=settings.day.month, day=settings.day.day, hour=7, minute=0)
        with patch_get_distance_matrix_cache(), mock.patch('django.utils.timezone.now', return_value=creation_time):
            resp = self.client.post(self.mobile_solo_api_url, request_data)
        self.assertEqual(resp.status_code, expectation.response_status)

        self.client.force_authenticate(settings.manager)
        get = self.client.get(self.api_url + str(resp.data['id']))
        ro_object = RouteOptimisation.objects.get(id=resp.data['id'])
        expectation.check(self, get, ro_object)
        self.ro_object = ro_object
        return resp.data['id']

    def refresh_solo(self, optimisation_id, route_id, settings: SoloAPISettings, expectation: OptimisationExpectation):
        self.client.force_authenticate(settings.initiator_driver)
        with patch_get_distance_matrix_cache():
            resp = self.client.post(self.mobile_refresh_solo_api_url.format(route_id))
        self.assertEqual(resp.status_code, expectation.response_status)
        self.client.force_authenticate(settings.manager)
        get = self.client.get(self.api_url + str(optimisation_id))
        ro_object = RouteOptimisation.objects.get(id=optimisation_id)
        expectation.check(self, get, ro_object)

    def manager_refresh_solo(self, optimisation_id, settings: SoloAPISettings, expectation: OptimisationExpectation,
                             options=None):
        self.client.force_authenticate(settings.manager)
        with patch_get_distance_matrix_cache():
            resp = self.client.post(self.refresh_solo_api_url.format(optimisation_id), data={'options': options or {}})

        self.assertEqual(resp.status_code, expectation.response_status)

        get = self.client.get(self.api_url + str(optimisation_id))
        ro_object = RouteOptimisation.objects.get(id=optimisation_id)
        expectation.check(self, get, ro_object)

    def manager_refresh(self, optimisation_id, route_id, settings: APISettings, expectation: OptimisationExpectation,
                        options=None):
        self.client.force_authenticate(settings.manager)
        with patch_get_distance_matrix_cache():
            resp = self.client.post(
                self.refresh_solo_api_url.format(optimisation_id),
                data={'route': route_id, 'options': options or {}},
            )

        self.assertEqual(resp.status_code, expectation.response_status)

        get = self.client.get(self.api_url + str(optimisation_id))
        ro_object = RouteOptimisation.objects.get(id=optimisation_id)
        expectation.check(self, get, ro_object)

    def run_legacy_solo_optimisation(self, settings: SoloAPISettings, expectation: OptimisationExpectation):
        driver = settings.initiator_driver
        driver_setting = settings.initiator_driver_setting
        driver_start_time = self.merchant.timezone.localize(
            datetime.combine(settings.day, time(
                hour=driver_setting.start_time.hour,
                minute=driver_setting.start_time.minute, second=0, microsecond=0
            )))
        request_data = settings.build_solo_request_data()
        with mock.patch('django.utils.timezone.now', return_value=driver_start_time), patch_get_distance_matrix_cache():
            self.client.force_authenticate(driver)
            resp = self.client.post(self.individual_api_url, request_data['options'])
        self.assertEqual(resp.status_code, expectation.response_status)
        self.client.force_authenticate(self.manager)
        get = self.client.get(self.api_url + str(resp.data['id']))
        ro_object = RouteOptimisation.objects.get(id=resp.data['id'])
        expectation.check(self, get, ro_object)
        self.ro_object = ro_object
        return resp.data['id']

    def create_optimisation_by_factory(self, day, driver, orders_count=2, ro_type=OPTIMISATION_TYPES.ADVANCED,
                                       state=RouteOptimisation.STATE.COMPLETED):
        orders = OrderFactory.create_batch(size=orders_count, merchant=self.merchant, manager=self.manager,
                                           status=OrderStatus.ASSIGNED, driver=driver)
        created_by = self.manager
        route_optimisation = RouteOptimisationFactory(
            day=day, created_by=created_by, type=ro_type, merchant=self.merchant,
        )
        OptimisationTaskFactory(optimisation=route_optimisation)
        route_optimisation.state = state
        route_optimisation.save(update_fields=['state'])
        driver_route = DriverRouteFactory(optimisation=route_optimisation, driver=driver)
        order_ct = ContentType.objects.get_for_model(Order)
        [
            RoutePointFactory(route=driver_route, number=idx+1, point_content_type=order_ct, point_object_id=order.id)
            for idx, order in enumerate(orders)
        ]
        return orders, route_optimisation

    def get_legacy_driver_routes(self, day=None):
        day_param = '?day={}'.format(str(day)) if day else ''
        return self.client.get('{}{}'.format(self.driver_routes_url, day_param))

    def get_legacy_driver_routes_v1(self, day=None):
        day_param = '?day={}'.format(str(day)) if day else ''
        return self.client.get('{}{}'.format(self.mobile_api_driver_routes_url, day_param))

    def get_optimisation(self, optimisation_id):
        return self.client.get('{}{}'.format(self.api_url, optimisation_id))

    def remove_optimisation(self, opt_id, status_code=status.HTTP_204_NO_CONTENT, unassign=None):
        url = '{}{}'.format(self.api_url, opt_id)
        data = {} if unassign is None else {'unassign': unassign}
        resp = self.client.delete(url, data=data)
        self.assertEqual(resp.status_code, status_code)
