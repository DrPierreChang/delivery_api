from django.test import override_settings

from rest_framework import status
from rest_framework.test import APITestCase

from route_optimisation.const import OPTIMISATION_TYPES

from ..web.api_settings import SoloAPISettings
from ..web.mixins import ORToolsMixin
from ..web.optimisation_expectation import (
    EndPointIsDriverLocationCheck,
    LogCheck,
    OptimisationExpectation,
    StartPointIsDriverLocationCheck,
)


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class CreateOptimisationTestCase(ORToolsMixin, APITestCase):
    settings = None

    def setUp(self):
        super().setUp()
        settings = SoloAPISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)
        settings.skill(1, service_time=5)
        settings.skill(2, service_time=0)
        settings.skill(3)
        settings.driver(member_id=1, start_hub=1, end_hub=2, skill_set=(1, 2, 3), end_time=(18, 0), capacity=15)
        settings.driver(member_id=2, skill_set=(1, 2, 3), end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743', skill_set=(1, 2, 3), driver=1,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881', skill_set=(1,), driver=1,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(3, '-37.8238154,145.0108082', skill_set=(2, 3), driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(4, '-37.755938,145.706767', driver=2,
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.service_time(12)
        settings.skip_day = True
        self.settings = settings

    def test_create_solo_with_locations(self):
        self.settings.set_initiator_driver(2)
        self.settings.location('-37.869197,144.82028300000002', 1)
        self.settings.location('-37.7855699,144.84063459999993', 2)
        self.settings.set_start_place(location=1)
        self.settings.set_end_place(location=2)

        success_expected = OptimisationExpectation(skipped_orders=0)
        success_expected.add_check(LogCheck('2 jobs were included into Optimisation'))
        success_expected.add_check(StartPointIsDriverLocationCheck(
            driver_id=self.settings.drivers_map[2].id, location={'lat': -37.869197, 'lng': 144.820283}
        ))
        success_expected.add_check(EndPointIsDriverLocationCheck(
            driver_id=self.settings.drivers_map[2].id, location={'lat': -37.7855699, 'lng': 144.8406346}
        ))
        ro_id = self.run_solo_optimisation(self.settings, success_expected)

        self.client.force_authenticate(self.settings.manager)
        resp = self.client.delete(self.api_url + str(ro_id))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.settings.set_end_place(hub=2)
        success_expected = OptimisationExpectation(skipped_orders=0)
        success_expected.add_check(LogCheck('2 jobs were included into Optimisation'))
        success_expected.add_check(StartPointIsDriverLocationCheck(
            driver_id=self.settings.drivers_map[2].id, location={'lat': -37.869197, 'lng': 144.820283}
        ))
        self.run_solo_optimisation(self.settings, success_expected)

    def test_create_solo_with_hub_options(self):
        self.settings.set_initiator_driver(2)
        self.settings.set_start_place(hub=2)
        fail_expected = OptimisationExpectation(skipped_orders=0, fail=True)
        fail_expected.add_check(LogCheck('hasn\'t set a default hub and will be removed from the Optimisation',
                                         partly=True))
        self.run_solo_optimisation(self.settings, fail_expected)
        self.settings.set_start_place()
        self.settings.set_end_place(hub=1)
        self.run_solo_optimisation(self.settings, fail_expected)
        self.settings.set_start_place(hub=2)
        success_expected = OptimisationExpectation(skipped_orders=0)
        success_expected.add_check(LogCheck('2 jobs were included into Optimisation'))
        self.run_solo_optimisation(self.settings, success_expected)

    def test_create_solo(self):
        self.settings.set_initiator_driver(1)
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(LogCheck('2 jobs were included into Optimisation'))
        ro_id = self.run_solo_optimisation(self.settings, expected)

        self.client.force_authenticate(self.settings.manager)
        resp = self.client.delete(self.api_url + str(ro_id))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.settings.skip_day = False
        self.run_solo_optimisation(self.settings, expected)

    def test_cant_create_past(self):
        self.client.force_authenticate(self.settings.drivers_map[1])
        resp = self.client.post(self.mobile_solo_api_url, dict(day='2020-06-11', options={}))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('day', resp.data['errors'])
