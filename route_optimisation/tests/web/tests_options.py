from django.test import override_settings

from rest_framework.test import APITestCase

from route_optimisation.const import OPTIMISATION_TYPES
from route_optimisation.engine.base_classes.parameters import EngineParameters
from route_optimisation.models import RouteOptimisation

from .api_settings import APISettings
from .mixins import ORToolsMixin


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class OptimisationOptionsTestCase(ORToolsMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.manager)
        self.settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                                    self.merchant, self.manager)
        self.settings.hub('-37.869197,144.820283', hub_id=1)
        self.settings.hub('-37.868197,144.820183', hub_id=2)
        self.settings.skill(1)
        self.settings.skill(2)

    def test_use_working_hours(self):
        self.settings.driver(member_id=1, start_hub=1, end_hub=1, start_time=(9, 0), end_time=(11, 0),)
        self.settings.driver(member_id=2, start_hub=1, end_hub=1, start_time=(19, 0), end_time=(21, 0),)
        self.settings.driver(member_id=3, start_hub=1, end_hub=1, start_time=(9, 0), end_time=(19, 0),)
        self.settings.driver(member_id=4, start_hub=1, end_hub=1, start_time=(9, 0), end_time=(15, 0),)
        self.settings.driver(member_id=5, start_hub=1, end_hub=1, start_time=(13, 0), end_time=(17, 0),)
        self.settings.driver(member_id=6, start_hub=1, end_hub=1, start_time=(15, 0), end_time=(21, 0),)
        expected_valid_drivers = set(self.settings.drivers_map[driver_id].member_id for driver_id in range(3, 7))
        self.settings.order(1, '-37.8421644,144.9399743', deliver_after_time=(9, 0,), deliver_before_time=(11, 0))
        self.settings.order(2, '-37.8238154,145.0108082', deliver_after_time=(19, 0,), deliver_before_time=(21, 0))
        self.settings.order(3, '-37.755938,145.706767', deliver_before_time=(11, 0))
        self.settings.order(4, '-37.8485871,144.6670881', deliver_after_time=(9, 0,), deliver_before_time=(19, 0))
        self.settings.order(5, '-37.8485871,144.6670881', deliver_after_time=(9, 0,), deliver_before_time=(15, 0))
        self.settings.order(6, '-37.755938,145.706767', deliver_after_time=(13, 00,), deliver_before_time=(17, 0))
        self.settings.order(7, '-37.755938,145.706767', deliver_after_time=(15, 00,), deliver_before_time=(21, 0))
        self.settings.order(8, '-37.755938,145.706767', deliver_before_time=(15, 0))
        self.settings.order(9, '-37.755938,145.706767', deliver_before_time=(21, 0))
        expected_valid_orders = set(self.settings.orders_map[order_id].id for order_id in range(4, 10))
        self.settings.service_time(10)
        self.settings.set_working_hours(lower=(12,), upper=(17,))
        optimisation_id = self.create_with_validation(self.settings)
        optimisation = RouteOptimisation.objects.get(id=optimisation_id)
        params: EngineParameters = optimisation.backend.get_params_for_engine()
        self.assertEqual(len(params.jobs), len(expected_valid_orders))
        self.assertEqual(len(params.drivers), len(expected_valid_drivers))
        valid_orders = set(job.id for job in params.jobs)
        valid_drivers = set(driver.member_id for driver in params.drivers)
        self.assertEqual(expected_valid_orders, valid_orders)
        self.assertEqual(expected_valid_drivers, valid_drivers)

    def test_set_start_end_place(self):
        self.settings.driver(member_id=1, start_hub=None, end_hub=1)
        self.settings.driver(member_id=2, start_hub=1, end_hub=2)
        self.settings.driver(member_id=3, start_hub=2, end_hub=None)
        self.settings.order(1, '-37.8485871,144.6670881')
        optimisation_id = self.create_with_validation(self.settings)
        optimisation = RouteOptimisation.objects.get(id=optimisation_id)
        params: EngineParameters = optimisation.backend.get_params_for_engine()
        self.assertEqual(len(params.drivers), 1)
        self.assertEqual(params.drivers[0].member_id, self.settings.drivers_map[2].member_id)
        self.assertEqual(params.drivers[0].start_hub.id, self.settings.hubs_map[1].id)
        self.assertEqual(params.drivers[0].end_hub.id, self.settings.hubs_map[2].id)
        optimisation.delete()

        self.settings.set_start_place(hub=1)
        optimisation_id = self.create_with_validation(self.settings)
        optimisation = RouteOptimisation.objects.get(id=optimisation_id)
        params: EngineParameters = optimisation.backend.get_params_for_engine()
        self.assertEqual(len(params.drivers), 2)
        drivers_dict = {driver.id: driver for driver in params.drivers}
        driver_1, driver_2 = self.settings.drivers_map[1], self.settings.drivers_map[2]
        self.assertEqual(drivers_dict[driver_1.id].start_hub.id, self.settings.hubs_map[1].id)
        self.assertEqual(drivers_dict[driver_1.id].end_hub.id, self.settings.hubs_map[1].id)
        self.assertEqual(drivers_dict[driver_2.id].start_hub.id, self.settings.hubs_map[1].id)
        self.assertEqual(drivers_dict[driver_2.id].end_hub.id, self.settings.hubs_map[2].id)
        optimisation.delete()

        self.settings.set_end_place(hub=2)
        optimisation_id = self.create_with_validation(self.settings)
        optimisation = RouteOptimisation.objects.get(id=optimisation_id)
        params: EngineParameters = optimisation.backend.get_params_for_engine()
        self.assertEqual(len(params.drivers), 3)
        for driver_params in params.drivers:
            self.assertEqual(driver_params.start_hub.id, self.settings.hubs_map[1].id)
            self.assertEqual(driver_params.end_hub.id, self.settings.hubs_map[2].id)
