from datetime import datetime, time, timedelta

from django.test import override_settings
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

import pytz

from base.factories import CarFactory, DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import HubFactory, HubLocationFactory, MerchantFactory, SkillSetFactory
from route_optimisation.const import OPTIMISATION_TYPES, HubOptions, MerchantOptimisationTypes, RoutePointKind
from route_optimisation.models import OptimisationTask, RouteOptimisation
from route_optimisation.tests.test_utils.setting import DriverBreakSetting
from route_optimisation.tests.web.api_settings import SoloAPISettings
from route_optimisation.tests.web.mixins import ORToolsMixin, patch_get_distance_matrix_cache
from route_optimisation.tests.web.optimisation_expectation import (
    DriverBreaksExactTime,
    NumberFieldConsecutiveCheck,
    OptimisationExpectation,
)
from route_optimisation.tests.web.tests_pickup_feature import enable_pickup_for_merchant
from schedule.models import Schedule
from tasks.mixins.order_status import OrderStatus
from tasks.tests.factories import BarcodesFactory, OrderFactory, OrderLocationFactory
from webhooks.factories import MerchantAPIKeyFactory
from webhooks.models import MerchantAPIKey


class WebhookOptimisationMixin:
    api_url = '/api/webhooks/ro/optimisation/v1/'

    merchant = None
    manager = None

    @property
    def api_url_with_key(self):
        return self.api_url + '?key={}'.format(self.apikey)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.merchant = MerchantFactory(route_optimization=MerchantOptimisationTypes.OR_TOOLS,
                                       timezone=pytz.timezone('Australia/Melbourne'), job_service_time=10,
                                       enable_job_capacity=True,)
        cls.default_timezone = cls.merchant.timezone
        cls.manager = ManagerFactory(merchant=cls.merchant)
        now = timezone.now().astimezone(cls.default_timezone)
        cls._day = (now + timedelta(days=1)).date()
        cls.apikey = MerchantAPIKeyFactory(creator=cls.manager, merchant=cls.merchant)


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class CreateOptimisationTestCase(WebhookOptimisationMixin, APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.skill_set = SkillSetFactory(merchant=cls.merchant)
        cls.hubs = [
            HubFactory(merchant=cls.merchant, location=HubLocationFactory(location='-37.869197,144.82028300000002')),
            HubFactory(merchant=cls.merchant, location=HubLocationFactory(location='-37.7855699,144.84063459999993')),
        ]
        cls.drivers = [
            DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING, starting_hub_id=None,
                          ending_hub_id=cls.hubs[0].id, car=CarFactory(capacity=15), ),
            DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING, starting_hub_id=cls.hubs[0].id,
                          ending_hub_id=cls.hubs[0].id, car=CarFactory(capacity=15), ),
            DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING, starting_hub_id=cls.hubs[1].id,
                          ending_hub_id=None, car=CarFactory(capacity=15), ),
        ]
        for driver in cls.drivers:
            driver.skill_sets.set([cls.skill_set])

    @enable_pickup_for_merchant
    def test_create_two_advanced(self):
        with patch_get_distance_matrix_cache():
            self._test_create_two_advanced()

    def _test_create_two_advanced(self):
        orders = [
            OrderFactory(
                merchant=self.merchant,
                deliver_after=datetime.combine(self._day, time(9, 50)).astimezone(self.default_timezone),
                deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(self.default_timezone),
                deliver_address=OrderLocationFactory(location='-37.8421644,144.9399743'),
                status=OrderStatus.NOT_ASSIGNED,
                driver_id=None, pickup_address=OrderLocationFactory(location='-37.755938,145.706767'),
            ),
            OrderFactory(
                merchant=self.merchant,
                deliver_after=datetime.combine(self._day, time(9, 50)).astimezone(self.default_timezone),
                deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(self.default_timezone),
                deliver_address=OrderLocationFactory(location='-37.8485871,144.6670881'),
                status=OrderStatus.NOT_ASSIGNED,
                driver_id=None, pickup_address=OrderLocationFactory(location='-37.755938,145.706767'),
            ),
            OrderFactory(
                merchant=self.merchant,
                deliver_after=datetime.combine(self._day, time(9, 50)).astimezone(self.default_timezone),
                deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(self.default_timezone),
                deliver_address=OrderLocationFactory(location='-37.8238154,145.0108082'),
                status=OrderStatus.NOT_ASSIGNED,
                driver_id=None, pickup_address=None,
            ),
            OrderFactory(
                merchant=self.merchant,
                deliver_after=datetime.combine(self._day, time(9, 50)).astimezone(self.default_timezone),
                deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(self.default_timezone),
                deliver_address=OrderLocationFactory(location='-37.755938,145.706767'),
                status=OrderStatus.NOT_ASSIGNED,
                driver_id=None, pickup_address=None,
            ),
        ]
        BarcodesFactory(order_id=orders[0].id)
        BarcodesFactory(order_id=orders[0].id)

        order_ids = list([i.order_id for i in orders])
        member_ids = list([i.member_id for i in self.drivers])
        resp = self.client.post(self.api_url_with_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=True,
                order_ids=order_ids,
                member_ids=member_ids,
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=self.hubs[0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                service_time=12,
                working_hours={'lower': '14:00:00', 'upper': '19:00:00'},
                use_vehicle_capacity=False,
            ),
        ))
        # The last driver does not have a default end hub
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        orders_2 = [
            OrderFactory(
                merchant=self.merchant,
                deliver_after=datetime.combine(self._day, time(9, 0)).astimezone(self.default_timezone),
                deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(self.default_timezone),
                deliver_address=OrderLocationFactory(location='-37.925078, 145.004605'),
                status=OrderStatus.NOT_ASSIGNED,
                driver_id=None, pickup_address=None,
            ),
            OrderFactory(
                merchant=self.merchant,
                deliver_after=datetime.combine(self._day, time(9, 0)).astimezone(self.default_timezone),
                deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(self.default_timezone),
                deliver_address=OrderLocationFactory(location='-37.6737777, 144.5943217'),
                status=OrderStatus.NOT_ASSIGNED,
                driver_id=None, pickup_address=None,
            ),
        ]
        order_ids_2 = list([i.order_id for i in orders_2])
        resp = self.client.post(self.api_url_with_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=order_ids + order_ids_2,
                member_ids=member_ids[1:],
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                end_place=HubOptions.EXTERNAL_END_HUB.hub_location,
                end_hub=self.hubs[1].id,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        deliveries_count, pickups_count = 0, 0
        for route in resp.data['routes']:
            for point in route['points']:
                if point['point_kind'] == RoutePointKind.PICKUP:
                    pickups_count += 1
                if point['point_kind'] == RoutePointKind.DELIVERY:
                    deliveries_count += 1
        self.assertEqual(deliveries_count, 6)
        self.assertEqual(pickups_count, 2)

    def test_create_past(self):
        resp = self.client.post(self.api_url_with_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED, day='2020-06-11', options=dict(),
        ))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('day', resp.data['errors'])

    def test_validations(self):
        with patch_get_distance_matrix_cache():
            self._test_validations()

    def _test_validations(self):
        drivers = [
            DriverFactory(merchant=self.merchant, work_status=WorkStatus.WORKING, starting_hub_id=None,
                          ending_hub_id=self.hubs[0].id, car=CarFactory(capacity=15), ),
            DriverFactory(merchant=self.merchant, work_status=WorkStatus.WORKING, starting_hub_id=self.hubs[0].id,
                          ending_hub_id=self.hubs[0].id, car=CarFactory(capacity=15), )
        ]
        driver_ids = [driver.member_id for driver in drivers]
        orders = OrderFactory.create_batch(
            size=2,
            merchant=self.merchant,
            deliver_after=datetime.combine(self._day, time(9, 0)).astimezone(self.default_timezone),
            deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(self.default_timezone),
            deliver_address=OrderLocationFactory(location='-37.925078, 145.004605'),
            status=OrderStatus.NOT_ASSIGNED,
            driver_id=None, pickup_address=None,
        )
        order = orders[0]

        # ok
        resp = self.client.post(self.api_url_with_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[order.order_id],
                member_ids=driver_ids,
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=self.hubs[0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        # no working_hours
        resp = self.client.post(self.api_url_with_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[order.order_id],
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=self.hubs[0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # no drivers
        resp = self.client.post(self.api_url_with_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[order.order_id],
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=self.hubs[0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # wrong drivers
        resp = self.client.post(self.api_url_with_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                member_ids=['bla'],
                order_ids=[order.order_id],
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=self.hubs[0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # non-exist driver
        resp = self.client.post(self.api_url_with_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                member_ids=[123],
                order_ids=[order.order_id],
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=self.hubs[0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # no orders
        resp = self.client.post(self.api_url_with_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                member_ids=driver_ids,
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=self.hubs[0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # no default hubs
        resp = self.client.post(self.api_url_with_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[order.order_id],
                member_ids=driver_ids,
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # wrong day
        resp = self.client.post(self.api_url_with_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day + timedelta(days=1)),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[order.order_id],
                member_ids=driver_ids,
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=self.hubs[0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # no assigned drivers
        order.driver = drivers[0]
        order.status = order.ASSIGNED
        order.save()
        resp = self.client.post(self.api_url_with_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[order.order_id],
                member_ids=[drivers[1].member_id],
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=self.hubs[0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # no driver with order skill sets
        order.skill_sets.set([self.skill_set])
        resp = self.client.post(self.api_url_with_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[order.order_id],
                member_ids=driver_ids,
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=self.hubs[0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # not working time
        drivers[0].skill_sets.set([self.skill_set])
        resp = self.client.post(self.api_url_with_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[order.order_id],
                member_ids=driver_ids,
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=self.hubs[0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '05:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # ok
        resp = self.client.post(self.api_url_with_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[orders[1].order_id],
                member_ids=driver_ids,
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=self.hubs[0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_cant_use_with_multi_api_key(self):
        multi_key = MerchantAPIKeyFactory(creator=self.manager, merchant=None, key_type=MerchantAPIKey.MULTI,
                                          available=True)
        self.merchant.api_multi_key = multi_key
        self.merchant.save(update_fields=('api_multi_key',))
        url = self.api_url + '?key={}'.format(multi_key)
        resp = self.client.post(url, dict(type=OPTIMISATION_TYPES.ADVANCED, day=str(self._day), options=dict()))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual('You can use this API only with "Single API Key"', resp.data['detail'])


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class ValidationsTestCase(WebhookOptimisationMixin, APITestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hubs = (
            HubFactory(merchant=cls.merchant, location=HubLocationFactory(location='-37.869197,144.82028300000002')),
            HubFactory(merchant=cls.merchant, location=HubLocationFactory(location='-37.7855699,144.84063459999993')),
        )

    def test_create_ro_when_some_drivers_not_available(self):
        with patch_get_distance_matrix_cache():
            self._test_create_ro_when_some_drivers_not_available()

    def _test_create_ro_when_some_drivers_not_available(self):
        url = self.api_url_with_key
        drivers = (
            DriverFactory(first_name='first', last_name='1st',
                          merchant=self.merchant, work_status=WorkStatus.WORKING,
                          starting_hub_id=self.hubs[0].id,
                          ending_hub_id=self.hubs[0].id,
                          car=CarFactory(capacity=15), ),
            DriverFactory(first_name='second', last_name='2nd',
                          merchant=self.merchant, work_status=WorkStatus.WORKING,
                          starting_hub_id=self.hubs[0].id,
                          ending_hub_id=self.hubs[0].id,
                          car=CarFactory(capacity=15), ),
            DriverFactory(first_name='third', last_name='3rd',
                          merchant=self.merchant, work_status=WorkStatus.WORKING,
                          starting_hub_id=self.hubs[0].id,
                          ending_hub_id=self.hubs[0].id,
                          car=CarFactory(capacity=15), ),
        )
        for driver in drivers:
            Schedule.objects.create(member=driver)
        _prev_user = self.client.handler._force_user
        _prev_token = self.client.handler._force_token
        self.client.force_authenticate(self.manager)
        resp = self.client.patch('/api/web/schedules/{0}/'.format(drivers[0].id), {
            'week_schedule': {
                day: {'start': '08:00', 'end': '20:00', 'day_off': True, 'one_time': False}
                for day in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
            },
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.patch('/api/web/schedules/{0}/'.format(drivers[1].id), {
            'week_schedule': {
                day: {'start': '13:00', 'end': '21:00', 'day_off': False, 'one_time': False}
                for day in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
            },
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.patch('/api/web/schedules/{0}/'.format(drivers[2].id), {
            'week_schedule': {
                day: {'start': '08:00', 'end': '20:00', 'day_off': False, 'one_time': False}
                for day in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
            },
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(_prev_user, _prev_token)
        orders = OrderFactory.create_batch(
            size=2,
            merchant=self.merchant,
            deliver_after=datetime.combine(self._day, time(9, 0)).astimezone(self.merchant.timezone),
            deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(self.merchant.timezone),
            deliver_address=OrderLocationFactory(location='-37.925078, 145.004605'),
            status=OrderStatus.NOT_ASSIGNED,
            driver_id=None, pickup_address=None,
        )

        resp = self.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[order.order_id for order in orders],
                member_ids=[driver.member_id for driver in drivers],
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=False,
                working_hours={'lower': '08:00:00', 'upper': '12:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for ro_result in resp.json()['results']:
            self.assertEqual(ro_result['state'], RouteOptimisation.STATE.COMPLETED)
            self.assertEqual(ro_result['task_status'], OptimisationTask.COMPLETED)
            self.assert_message_in_optimisation_log(
                ro_result['log']['messages'],
                'Driver first 1st is unavailable during the Optimisation working hours and will be removed',
            )
            self.assert_message_in_optimisation_log(
                ro_result['log']['messages'],
                'Driver second 2nd is unavailable during the Optimisation working hours and will be removed',
            )
            self.assert_message_in_optimisation_log(ro_result['log']['messages'], '2 new jobs were assigned to')

    def assert_message_in_optimisation_log(self, logs, message):
        for log_item in logs:
            if message in log_item['text']:
                return
        raise self.failureException('Message is not in optimisation log')


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class GetOptimisationTestCaseV1(ORToolsMixin, APITestCase):
    external_api_url = '/api/webhooks/ro/optimisation/v1/'

    def api_url_with_key(self, append_url, api_key):
        return self.external_api_url + append_url + '?key={}'.format(api_key)

    @classmethod
    def setUpTestData(cls):
        super(GetOptimisationTestCaseV1, cls).setUpTestData()
        cls.key = MerchantAPIKeyFactory(creator=cls.manager, merchant=cls.merchant, key_type=MerchantAPIKey.SINGLE,
                                        available=True, is_master_key=True)

    def test_create_solo(self):
        settings = SoloAPISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=15,
                        breaks=[DriverBreakSetting((8, 10), (8, 20), 5)])
        settings.order(1, '-37.6780953, 145.1290807', driver=1, deliver_before_time=(18, 30))
        settings.order(2, '-37.926451, 144.998992', driver=1, deliver_before_time=(15, 30))
        settings.initiator_driver = settings.drivers_map[1]
        settings.initiator_driver_setting = settings.drivers_setting_map[1]
        expectation = OptimisationExpectation(skipped_orders=0)
        expectation.add_check(NumberFieldConsecutiveCheck())
        expectation.add_check(DriverBreaksExactTime(driver_id=settings.drivers_map[1].id,
                                                    breaks=[((8, 10), (8, 20))]))
        opt_id = self.run_solo_optimisation(settings, expectation)

        self.client.logout()
        result = self.client.get(self.api_url_with_key(str(opt_id), self.key)).json()
        self.assertEqual(result['day'], str(self._day))
        self.assertEqual(len(result['routes']), 1)
        route = result['routes'][0]
        self.assertEqual(len(route['points']), 5)
        break_point = route['points'][1]
        self.assertEqual(break_point['point_kind'], RoutePointKind.BREAK)
        self.assertEqual(break_point['start_time'], f'{self._day}T08:10:00+10:00')
        self.assertEqual(break_point['end_time'], f'{self._day}T08:20:00+10:00')
