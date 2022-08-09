from datetime import datetime, time, timedelta
from functools import wraps

from django.test import override_settings
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

import pytz

from base.factories import AdminFactory, CarFactory, DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import HubFactory, HubLocationFactory, MerchantFactory, SkillSetFactory
from merchant.models import Merchant
from route_optimisation.const import OPTIMISATION_TYPES, HubOptions, MerchantOptimisationTypes, RoutePointKind
from route_optimisation.models import OptimisationTask, RouteOptimisation
from route_optimisation.tests.web.mixins import patch_get_distance_matrix_cache
from schedule.models import Schedule
from tasks.mixins.order_status import OrderStatus
from tasks.tests.factories import BarcodesFactory, OrderFactory, OrderLocationFactory
from webhooks.factories import MerchantAPIKeyFactory
from webhooks.models import MerchantAPIKey
from webhooks.tests.route_optimisation.v1.tests_ro import GetOptimisationTestCaseV1
from webhooks.tests.route_optimisation.v2.options_validation_cases import (
    EmptyDrivers,
    NoAssignedDrivers,
    NoAvailableDrivers,
    NoDefaultHubs,
    NoDrivers,
    NoDriverWithOrderSkillSets,
    NonExistDriver,
    NoOrders,
    NoStartHubForMultipleMerchants,
    NoWorkingHours,
    WrongDay,
    WrongDrivers,
)


def enable_pickup_for_merchants(func):
    @wraps(func)
    def patched(self, *args, **kwargs):
        for merchant in self.merchants:
            merchant.use_pick_up_status = True
            merchant.save(update_fields=('use_pick_up_status',))
        result = func(self, *args, **kwargs)
        for merchant in self.merchants:
            merchant.use_pick_up_status = False
            merchant.save(update_fields=('use_pick_up_status',))
        return result
    return patched


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class CreateOptimisationTestCase(APITestCase):
    api_url = '/api/webhooks/ro/optimisation/v2/'

    merchants = None
    managers = None
    api_keys = None
    multi_key = None

    def api_url_with_key(self, api_key):
        return self.api_url + '?key={}'.format(api_key)

    @property
    def api_url_with_multi_key(self):
        return self.api_url + '?key={}'.format(self.multi_key)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.merchants = [
            MerchantFactory(route_optimization=MerchantOptimisationTypes.OR_TOOLS,
                            timezone=pytz.timezone('Australia/Melbourne'), job_service_time=10,
                            enable_job_capacity=True,),
            MerchantFactory(route_optimization=MerchantOptimisationTypes.OR_TOOLS,
                            timezone=pytz.timezone('Australia/Melbourne'), job_service_time=20,
                            enable_job_capacity=False,)
        ]

        cls.default_timezone = cls.merchants[0].timezone
        cls.admin = AdminFactory(merchant=cls.merchants[0])
        now = timezone.now().astimezone(cls.default_timezone)
        cls._day = (now + timedelta(days=1)).date()

        cls.managers, cls.api_keys, cls.skill_sets, cls.hubs, cls.drivers = {}, {}, {}, {}, {}
        for merchant in cls.merchants:
            cls.managers[merchant] = ManagerFactory(merchant=merchant)
            cls.api_keys[merchant] = MerchantAPIKeyFactory(creator=cls.managers[merchant], merchant=merchant)
            cls.skill_sets[merchant] = (SkillSetFactory(merchant=merchant),)
            cls.hubs[merchant] = (
                HubFactory(merchant=merchant, location=HubLocationFactory(location='-37.869197,144.82028300000002')),
                HubFactory(merchant=merchant, location=HubLocationFactory(location='-37.7855699,144.84063459999993')),
            )
            cls.drivers[merchant] = (
                DriverFactory(merchant=merchant, work_status=WorkStatus.WORKING,
                              starting_hub_id=None,
                              ending_hub_id=cls.hubs[merchant][0].id,
                              car=CarFactory(capacity=15), ),
                DriverFactory(merchant=merchant, work_status=WorkStatus.WORKING,
                              starting_hub_id=cls.hubs[merchant][0].id,
                              ending_hub_id=cls.hubs[merchant][0].id,
                              car=CarFactory(capacity=30), ),
                DriverFactory(merchant=merchant, work_status=WorkStatus.WORKING,
                              starting_hub_id=cls.hubs[merchant][1].id,
                              ending_hub_id=None,
                              car=CarFactory(capacity=15), ),
            )
            for driver in cls.drivers[merchant]:
                driver.skill_sets.set(cls.skill_sets[merchant])

        cls.multi_key = MerchantAPIKeyFactory(creator=cls.admin, merchant=None, key_type=MerchantAPIKey.MULTI,
                                              available=True)
        for merchant in cls.merchants:
            merchant.api_multi_key = cls.multi_key
            merchant.save(update_fields=('api_multi_key',))

    def test_capacity_disabled(self):
        with patch_get_distance_matrix_cache():
            self._test_capacity_disabled(self.merchants, expected_fail=True, multi_key=True)
            self._test_capacity_disabled((self.merchants[0], ), expected_fail=False, multi_key=True)
            self._test_capacity_disabled((self.merchants[1], ), expected_fail=True, multi_key=True)
            self._test_capacity_disabled((self.merchants[0], ), expected_fail=False, multi_key=False)
            self._test_capacity_disabled((self.merchants[1], ), expected_fail=True, multi_key=False)

    def _test_capacity_disabled(self, merchants, expected_fail=False, multi_key=False):
        url = self.api_url_with_multi_key if multi_key else self.api_url_with_key(self.api_keys[merchants[0]])
        orders = []
        for merchant in merchants:
            orders.append(OrderFactory(
                merchant=merchant,
                deliver_after=datetime.combine(self._day, time(9, 0)).astimezone(merchant.timezone),
                deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(merchant.timezone),
                deliver_address=OrderLocationFactory(location='-37.925078, 145.004605'),
                status=OrderStatus.NOT_ASSIGNED,
                driver_id=None, pickup_address=None,
            ))
        order_ids = list(i.order_id for i in orders)
        members_ids = list(driver.member_id for merchant in merchants for driver in self.drivers[merchant][1:-1])
        resp = self.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=order_ids,
                member_ids=members_ids,
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        if expected_fail:
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('Vehicle Capacity feature is disabled',
                          str(resp.data['errors']['options']['use_vehicle_capacity']))
        else:
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
            self.assertEqual(len(resp.data), len(merchants))

    @enable_pickup_for_merchants
    def test_create_two_advanced(self):
        orders_1 = {}
        for merchant in self.merchants:
            orders_1[merchant] = (
                OrderFactory(
                    merchant=merchant,
                    deliver_after=datetime.combine(self._day, time(9, 50)).astimezone(merchant.timezone),
                    deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(merchant.timezone),
                    deliver_address=OrderLocationFactory(location='-37.8421644,144.9399743'),
                    status=OrderStatus.NOT_ASSIGNED,
                    driver_id=None, pickup_address=OrderLocationFactory(location='-37.755938,145.706767'),
                ),
                OrderFactory(
                    merchant=merchant,
                    deliver_after=datetime.combine(self._day, time(9, 50)).astimezone(merchant.timezone),
                    deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(merchant.timezone),
                    deliver_address=OrderLocationFactory(location='-37.8485871,144.6670881'),
                    status=OrderStatus.NOT_ASSIGNED,
                    driver_id=None, pickup_address=OrderLocationFactory(location='-37.755938,145.706767'),
                ),
                OrderFactory(
                    merchant=merchant,
                    deliver_after=datetime.combine(self._day, time(9, 50)).astimezone(merchant.timezone),
                    deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(merchant.timezone),
                    deliver_address=OrderLocationFactory(location='-37.8238154,145.0108082'),
                    status=OrderStatus.NOT_ASSIGNED,
                    driver_id=None, pickup_address=None,
                ),
                OrderFactory(
                    merchant=merchant,
                    deliver_after=datetime.combine(self._day, time(9, 50)).astimezone(merchant.timezone),
                    deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(merchant.timezone),
                    deliver_address=OrderLocationFactory(location='-37.755938,145.706767'),
                    status=OrderStatus.NOT_ASSIGNED,
                    driver_id=None, pickup_address=None,
                ),
            )
            BarcodesFactory(order_id=orders_1[merchant][0].id)
            BarcodesFactory(order_id=orders_1[merchant][0].id)
        orders_2 = {}
        for merchant in self.merchants:
            orders_2[merchant] = (
                OrderFactory(
                    merchant=merchant,
                    deliver_after=datetime.combine(self._day, time(9, 0)).astimezone(merchant.timezone),
                    deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(merchant.timezone),
                    deliver_address=OrderLocationFactory(location='-37.925078, 145.004605'),
                    status=OrderStatus.NOT_ASSIGNED,
                    driver_id=None, pickup_address=None,
                ),
                OrderFactory(
                    merchant=merchant,
                    deliver_after=datetime.combine(self._day, time(9, 0)).astimezone(merchant.timezone),
                    deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(merchant.timezone),
                    deliver_address=OrderLocationFactory(location='-37.6737777, 144.5943217'),
                    status=OrderStatus.NOT_ASSIGNED,
                    driver_id=None, pickup_address=None,
                ),
            )
        with patch_get_distance_matrix_cache():
            self._test_create_two_advanced(self.merchants, orders_1, orders_2, multi_key=True)
            self._test_create_two_advanced((self.merchants[0],), orders_1, orders_2, multi_key=True)
            self._test_create_two_advanced((self.merchants[1],), orders_1, orders_2, multi_key=True)
            self._test_create_two_advanced((self.merchants[0],), orders_1, orders_2, multi_key=False)
            self._test_create_two_advanced((self.merchants[1],), orders_1, orders_2, multi_key=False)

    def _test_create_two_advanced(self, merchants, orders_1, orders_2, multi_key=False):
        url = self.api_url_with_multi_key if multi_key else self.api_url_with_key(self.api_keys[merchants[0]])
        order_ids = list(i.order_id for merchant in merchants for i in orders_1[merchant])
        members_ids = list(driver.member_id for merchant in merchants for driver in self.drivers[merchant][1:])
        resp = self.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=True,
                order_ids=order_ids,
                member_ids=members_ids,
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                service_time=12,
                working_hours={'lower': '14:00:00', 'upper': '19:00:00'},
                use_vehicle_capacity=False,
            ),
        ))
        # The last driver does not have a default end hub
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('driver with member_id "%s" has no default end hub' % self.drivers[merchants[0]][-1].member_id,
                      resp.data['detail'])

        order_ids_2 = list(i.order_id for merchant in merchants for i in orders_2[merchant])
        members_ids = list(driver.member_id for merchant in merchants for driver in self.drivers[merchant][1:-1])
        resp = self.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=order_ids + order_ids_2,
                member_ids=members_ids,
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=False,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        self.assertEqual(len(resp.data), len(merchants))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        for merchant_resp in resp.data:
            deliveries_count, pickups_count = 0, 0
            for route in merchant_resp['routes']:
                for point in route['points']:
                    if point['point_kind'] == RoutePointKind.PICKUP:
                        pickups_count += 1
                    if point['point_kind'] == RoutePointKind.DELIVERY:
                        deliveries_count += 1
            self.assertEqual(deliveries_count, 6)
            self.assertEqual(pickups_count, 2)
            _prev_user = self.client.handler._force_user
            _prev_token = self.client.handler._force_token
            self.client.force_authenticate(self.managers[Merchant.objects.get(id=merchant_resp['merchant'])])
            delete_url = '/api/web/ro/optimisation/{}'.format(merchant_resp['id'])
            resp = self.client.delete(delete_url, data={'unassign': True})
            self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
            self.client.force_authenticate(_prev_user, _prev_token)

    def test_create_no_data(self):
        resp = self.client.post(self.api_url_with_multi_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED, day=str(self._day), options=dict(
                member_ids=[],
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('This field is required', str(resp.data['errors']['options']['end_place']))
        self.assertIn('This field is required', str(resp.data['errors']['options']['working_hours']))

        for merchant in self.merchants:
            resp = self.client.post(self.api_url_with_key(self.api_keys[merchant]), dict(
                type=OPTIMISATION_TYPES.ADVANCED, day=str(self._day), options=dict(
                    member_ids=[],
                    start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                    end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                    working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
                ),
            ))
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('No drivers passed', str(resp.data['errors']['options']['member_ids']))

    def test_create_past(self):
        for merchant in self.merchants:
            resp = self.client.post(self.api_url_with_key(self.api_keys[merchant]), dict(
                type=OPTIMISATION_TYPES.ADVANCED, day='2020-06-11',
                options=dict(
                    start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                    end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                    member_ids=list([i.member_id for i in self.drivers[merchant]]),
                    working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
                ),
            ))
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('Cannot create optimisation in the past', str(resp.data['errors']['day']))

        members = list(driver.member_id for drivers in self.drivers.values() for driver in drivers)
        resp = self.client.post(self.api_url_with_multi_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED, day='2020-06-11',
            options=dict(
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                member_ids=members,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot create optimisation in the past', str(resp.data['errors']['day']))

    def test_validations(self):
        with patch_get_distance_matrix_cache():
            self.merchants[1].enable_job_capacity = True
            self.merchants[1].save(update_fields=('enable_job_capacity',))
            self._test_validations(self.merchants, multi_key=True)
            self._test_validations((self.merchants[0],), multi_key=True)
            self._test_validations((self.merchants[1],), multi_key=True)
            self._test_validations((self.merchants[0],), multi_key=False)
            self._test_validations((self.merchants[1],), multi_key=False)
            self.merchants[1].enable_job_capacity = False
            self.merchants[1].save(update_fields=('enable_job_capacity',))

    def _test_validations(self, merchants, multi_key=False):
        url = self.api_url_with_multi_key if multi_key else self.api_url_with_key(self.api_keys[merchants[0]])
        orders = {}
        drivers = {}
        for merchant in merchants:
            drivers[merchant] = (
                DriverFactory(merchant=merchant, work_status=WorkStatus.WORKING,
                              starting_hub_id=None,
                              ending_hub_id=self.hubs[merchant][0].id,
                              car=CarFactory(capacity=15), ),
                DriverFactory(merchant=merchant, work_status=WorkStatus.WORKING,
                              starting_hub_id=self.hubs[merchant][0].id,
                              ending_hub_id=self.hubs[merchant][0].id,
                              car=CarFactory(capacity=15), ),
                DriverFactory(merchant=merchant, work_status=WorkStatus.WORKING,
                              starting_hub_id=self.hubs[merchant][0].id,
                              ending_hub_id=self.hubs[merchant][0].id,
                              car=CarFactory(capacity=15), ),
            )
            for driver in drivers[merchant]:
                Schedule.objects.create(member=driver)
            orders[merchant] = OrderFactory.create_batch(
                size=2,
                merchant=merchant,
                deliver_after=datetime.combine(self._day, time(9, 0)).astimezone(merchant.timezone),
                deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(merchant.timezone),
                deliver_address=OrderLocationFactory(location='-37.925078, 145.004605'),
                status=OrderStatus.NOT_ASSIGNED,
                driver_id=None, pickup_address=None,
            )
        driver_ids = {merchant: [driver.member_id for driver in drivers_list]
                      for merchant, drivers_list in drivers.items()}

        # ok
        resp = self.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[_orders[0].order_id for _orders in orders.values()],
                member_ids=[_driver_ids[2] for _driver_ids in driver_ids.values()],
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        cases = (
            NoWorkingHours,
            NoDrivers,
            EmptyDrivers,
            WrongDrivers,
            NonExistDriver,
            NoOrders,
            NoStartHubForMultipleMerchants,
            NoDefaultHubs,
            WrongDay,
            NoAssignedDrivers,
            NoDriverWithOrderSkillSets,
            NoAvailableDrivers,
        )

        for case in cases:
            resp = case.request(self, url, self._day, orders, drivers, driver_ids, self.hubs, merchants,
                                self.skill_sets)
            case.assert_response(self, resp, merchants)

        # ok
        resp = self.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[_orders[1].order_id for _orders in orders.values()],
                member_ids=[_driver_ids[0] for _driver_ids in driver_ids.values()],
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=self.hubs[merchants[0]][0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        if len(merchants) == 1:
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        else:
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('You cannot set start hub for multiple merchants',
                          str(resp.data['errors']['options']['start_hub']))

    def test_cant_use_when_optimisation_disabled(self):
        self.merchants[0].route_optimization = Merchant.ROUTE_OPTIMIZATION_DISABLED
        self.merchants[0].save(update_fields=('route_optimization',))
        resp = self.client.post(self.api_url_with_multi_key,
                                dict(type=OPTIMISATION_TYPES.ADVANCED, day=str(self._day), options=dict()))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual('Route optimisation is not active for you', str(resp.data['detail']))
        self.merchants[0].route_optimization = MerchantOptimisationTypes.OR_TOOLS
        self.merchants[0].save(update_fields=('route_optimization',))


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class MerchantApiKeyTestCase(APITestCase):
    api_url = '/api/webhooks/ro/optimisation/v2/'

    merchants = None
    managers = None
    api_keys = None
    multi_key = None

    def api_url_with_key(self, api_key):
        return self.api_url + '?key={}'.format(api_key)

    @property
    def api_url_with_multi_key(self):
        return self.api_url + '?key={}'.format(self.multi_key)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.merchants = [
            MerchantFactory(route_optimization=MerchantOptimisationTypes.OR_TOOLS,
                            timezone=pytz.timezone('Australia/Melbourne'), job_service_time=10,
                            enable_job_capacity=True,),
            MerchantFactory(route_optimization=MerchantOptimisationTypes.OR_TOOLS,
                            timezone=pytz.timezone('Europe/Minsk'), job_service_time=20,
                            enable_job_capacity=False,)
        ]

        cls.default_timezone = cls.merchants[0].timezone
        cls.admin = AdminFactory(merchant=cls.merchants[0])
        now = timezone.now().astimezone(cls.default_timezone)
        cls._day = (now + timedelta(days=1)).date()

        cls.managers, cls.api_keys, cls.master_api_keys, cls.drivers, cls.hubs = {}, {}, {}, {}, {}
        for merchant in cls.merchants:
            cls.managers[merchant] = ManagerFactory(merchant=merchant)
            cls.api_keys[merchant] = MerchantAPIKeyFactory(creator=cls.managers[merchant], merchant=merchant)
            cls.master_api_keys[merchant] = MerchantAPIKeyFactory(creator=cls.managers[merchant], merchant=merchant,
                                                                  is_master_key=True)
            cls.hubs[merchant] = HubFactory(merchant=merchant,
                                            location=HubLocationFactory(location='-37.869197,144.82028300000002'))
            cls.drivers[merchant] = (
                DriverFactory(merchant=merchant, work_status=WorkStatus.WORKING,
                              starting_hub_id=cls.hubs[merchant].id,
                              ending_hub_id=cls.hubs[merchant].id,
                              car=CarFactory(capacity=15), ),
            )

        cls.multi_key = MerchantAPIKeyFactory(creator=cls.admin, merchant=None, key_type=MerchantAPIKey.MULTI,
                                              available=True)
        for merchant in cls.merchants:
            merchant.api_multi_key = cls.multi_key
            merchant.save(update_fields=('api_multi_key',))

    def test_get_via_single_api_key(self):
        with patch_get_distance_matrix_cache():
            self._test_get_via_single_api_key()

    def _test_get_via_single_api_key(self):
        orders = {}
        for merchant in self.merchants:
            orders[merchant] = OrderFactory.create_batch(
                size=3,
                merchant=merchant,
                deliver_after=datetime.combine(self._day, time(9, 0)).astimezone(merchant.timezone),
                deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(merchant.timezone),
                deliver_address=OrderLocationFactory(location='-37.925078, 145.004605'),
                status=OrderStatus.NOT_ASSIGNED,
                driver_id=None, pickup_address=None,
            )

            resp = self.client.post(self.api_url_with_key(self.api_keys[merchant]), dict(
                type=OPTIMISATION_TYPES.ADVANCED,
                day=str(self._day),
                options=dict(
                    re_optimise_assigned=False,
                    order_ids=[orders[merchant][0].order_id],
                    member_ids=[self.drivers[merchant][0].member_id],
                    start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                    end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                    working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
                ),
            ))
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

            resp = self.client.post(self.api_url_with_key(self.master_api_keys[merchant]), dict(
                type=OPTIMISATION_TYPES.ADVANCED,
                day=str(self._day),
                options=dict(
                    re_optimise_assigned=False,
                    order_ids=[orders[merchant][1].order_id],
                    member_ids=[self.drivers[merchant][0].member_id],
                    start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                    end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                    working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
                ),
            ))
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
            resp = self.client.get(self.api_url_with_key(self.api_keys[merchant]))
            self.assertEqual(resp.data['count'], 1)
            resp = self.client.get(self.api_url_with_key(self.master_api_keys[merchant]))
            self.assertEqual(resp.data['count'], 2)

        resp = self.client.post(self.api_url_with_multi_key, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[_orders[2].order_id for _orders in orders.values()],
                member_ids=[_drivers[0].member_id for _drivers in self.drivers.values()],
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        for merchant in self.merchants:
            resp = self.client.get(self.api_url_with_key(self.api_keys[merchant]))
            self.assertEqual(resp.data['count'], 1)
            resp = self.client.get(self.api_url_with_key(self.master_api_keys[merchant]))
            self.assertEqual(resp.data['count'], 3)

        resp = self.client.get(self.api_url_with_multi_key)
        self.assertEqual(resp.data['count'], 2)
        self.multi_key.is_master_key = True
        self.multi_key.save(update_fields=('is_master_key',))
        resp = self.client.get(self.api_url_with_multi_key)
        self.assertEqual(resp.data['count'], 6)


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class ValidationsTestCase(APITestCase):
    api_url = '/api/webhooks/ro/optimisation/v2/'

    merchants = None
    managers = None
    api_keys = None
    multi_key = None

    def api_url_with_key(self, api_key):
        return self.api_url + '?key={}'.format(api_key)

    @property
    def api_url_with_multi_key(self):
        return self.api_url + '?key={}'.format(self.multi_key)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.merchants = [
            MerchantFactory(route_optimization=MerchantOptimisationTypes.OR_TOOLS,
                            timezone=pytz.timezone('Australia/Melbourne'), job_service_time=10,
                            enable_job_capacity=True,),
            MerchantFactory(route_optimization=MerchantOptimisationTypes.OR_TOOLS,
                            timezone=pytz.timezone('Australia/Melbourne'), job_service_time=20,
                            enable_job_capacity=False,)
        ]

        cls.default_timezone = cls.merchants[0].timezone
        cls.admin = AdminFactory(merchant=cls.merchants[0])
        now = timezone.now().astimezone(cls.default_timezone)
        cls._day = (now + timedelta(days=1)).date()

        cls.managers, cls.api_keys, cls.hubs, cls.drivers = {}, {}, {}, {}
        for merchant in cls.merchants:
            cls.managers[merchant] = ManagerFactory(merchant=merchant)
            cls.api_keys[merchant] = MerchantAPIKeyFactory(creator=cls.managers[merchant], merchant=merchant)
            cls.hubs[merchant] = (
                HubFactory(merchant=merchant, location=HubLocationFactory(location='-37.869197,144.82028300000002')),
                HubFactory(merchant=merchant, location=HubLocationFactory(location='-37.7855699,144.84063459999993')),
            )

        cls.multi_key = MerchantAPIKeyFactory(creator=cls.admin, merchant=None, key_type=MerchantAPIKey.MULTI,
                                              available=True)
        for merchant in cls.merchants:
            merchant.api_multi_key = cls.multi_key
            merchant.save(update_fields=('api_multi_key',))

    def test_create_ro_when_some_drivers_not_available(self):
        with patch_get_distance_matrix_cache():
            self._test_create_ro_when_some_drivers_not_available(self.merchants, multi_key=True)
            self._test_create_ro_when_some_drivers_not_available((self.merchants[0],), multi_key=True)
            self._test_create_ro_when_some_drivers_not_available((self.merchants[1],), multi_key=True)
            self._test_create_ro_when_some_drivers_not_available((self.merchants[0],), multi_key=False)
            self._test_create_ro_when_some_drivers_not_available((self.merchants[1],), multi_key=False)

    def _test_create_ro_when_some_drivers_not_available(self, merchants, multi_key):
        url = self.api_url_with_multi_key if multi_key else self.api_url_with_key(self.api_keys[merchants[0]])
        orders = {}
        drivers = {}
        for merchant in merchants:
            drivers[merchant] = (
                DriverFactory(first_name='first', last_name='1st',
                              merchant=merchant, work_status=WorkStatus.WORKING,
                              starting_hub_id=self.hubs[merchant][0].id,
                              ending_hub_id=self.hubs[merchant][0].id,
                              car=CarFactory(capacity=15), ),
                DriverFactory(first_name='second', last_name='2nd',
                              merchant=merchant, work_status=WorkStatus.WORKING,
                              starting_hub_id=self.hubs[merchant][0].id,
                              ending_hub_id=self.hubs[merchant][0].id,
                              car=CarFactory(capacity=15), ),
                DriverFactory(first_name='third', last_name='3rd',
                              merchant=merchant, work_status=WorkStatus.WORKING,
                              starting_hub_id=self.hubs[merchant][0].id,
                              ending_hub_id=self.hubs[merchant][0].id,
                              car=CarFactory(capacity=15), ),
            )
            for driver in drivers[merchant]:
                Schedule.objects.create(member=driver)
            _prev_user = self.client.handler._force_user
            _prev_token = self.client.handler._force_token
            self.client.force_authenticate(self.managers[merchant])
            resp = self.client.patch('/api/web/schedules/{0}/'.format(drivers[merchant][0].id), {
                'week_schedule': {
                    day: {'start': '08:00', 'end': '20:00', 'day_off': True, 'one_time': False}
                    for day in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
                },
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            resp = self.client.patch('/api/web/schedules/{0}/'.format(drivers[merchant][1].id), {
                'week_schedule': {
                    day: {'start': '13:00', 'end': '21:00', 'day_off': False, 'one_time': False}
                    for day in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
                },
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            resp = self.client.patch('/api/web/schedules/{0}/'.format(drivers[merchant][2].id), {
                'week_schedule': {
                    day: {'start': '08:00', 'end': '20:00', 'day_off': False, 'one_time': False}
                    for day in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
                },
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.client.force_authenticate(_prev_user, _prev_token)
            orders[merchant] = OrderFactory.create_batch(
                size=2,
                merchant=merchant,
                deliver_after=datetime.combine(self._day, time(9, 0)).astimezone(merchant.timezone),
                deliver_before=datetime.combine(self._day, time(19, 0)).astimezone(merchant.timezone),
                deliver_address=OrderLocationFactory(location='-37.925078, 145.004605'),
                status=OrderStatus.NOT_ASSIGNED,
                driver_id=None, pickup_address=None,
            )
        driver_ids = {merchant: [driver.member_id for driver in drivers_list]
                      for merchant, drivers_list in drivers.items()}

        resp = self.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(self._day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[o.order_id for _orders in orders.values() for o in _orders],
                member_ids=[dr for _driver_ids in driver_ids.values() for dr in _driver_ids],
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
class GetOptimisationTestCaseV2(GetOptimisationTestCaseV1):
    external_api_url = '/api/webhooks/ro/optimisation/v2/'

    @classmethod
    def setUpTestData(cls):
        super(GetOptimisationTestCaseV2, cls).setUpTestData()
        cls.key = MerchantAPIKeyFactory(creator=cls.manager, merchant=None, key_type=MerchantAPIKey.MULTI,
                                        available=True, is_master_key=True)
        cls.merchant.api_multi_key = cls.key
        cls.merchant.save(update_fields=('api_multi_key',))
