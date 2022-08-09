import csv

from django.test import override_settings

from rest_framework import status
from rest_framework.test import APITestCase

from reporting.models import ExportReportInstance
from route_optimisation.const import OPTIMISATION_TYPES
from route_optimisation.logging import EventType, log_item_registry
from route_optimisation.models import RouteOptimisation
from tasks.tests.factories import BarcodesFactory

from ..test_utils.setting import DriverBreakSetting
from .api_settings import APISettings, SoloAPISettings
from .mixins import ORToolsMixin
from .optimisation_expectation import (
    DriverBreaksExactTime,
    EndPointIsDefaultLocationCheck,
    EndPointIsOrderCheck,
    NumberFieldConsecutiveCheck,
    OptimisationExpectation,
    ServiceTimeCheck,
)


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class NormalCreateOptimisationTestCase(ORToolsMixin, APITestCase):

    @override_settings(ORTOOLS_SEARCH_TIME_LIMIT=5, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=5)
    def test_create_two_advanced(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)
        settings.skill(1, service_time=5)
        settings.skill(2, service_time=0)
        settings.skill(3)
        settings.driver(member_id=1, start_hub=None, end_hub=1, skill_set=(1, 2, 3), end_time=(19, 0), capacity=15,
                        breaks=[DriverBreakSetting((12, 20), (12, 30), 5),
                                DriverBreakSetting((18, 40), (19, 10), 15), ])
        settings.driver(member_id=2, start_hub=1, end_hub=1, skill_set=(1, 2, 3), end_time=(15, 0), capacity=15,
                        breaks=[DriverBreakSetting((7, 40), (8, 10), 15), DriverBreakSetting((11, 40), (15, 10), 15)])
        settings.driver(member_id=3, start_hub=2, end_hub=None, skill_set=(1, 2, 3),
                        start_time=(8,), end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743', skill_set=(1, 2, 3),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881', skill_set=(1,),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(3, '-37.8238154,145.0108082', skill_set=(2, 3),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(4, '-37.755938,145.706767', deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.service_time(12)
        settings.set_re_optimise_assigned(True)
        settings.set_start_place(hub=1)
        settings.set_working_hours(lower=(12,), upper=(19,))
        expected = OptimisationExpectation(skipped_orders=0)
        ro_one_id = self.run_optimisation(settings, expected)

        self.merchant.enable_concatenated_orders = True
        self.merchant.save()
        new_settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        new_settings.copy_hubs(settings)
        new_settings.copy_skills(settings)
        new_settings.copy_drivers(settings)
        new_settings.order(5, '-37.925078, 145.004605', deliver_after_time=(9, 0,), deliver_before_time=(19, 0))
        new_settings.order(6, '-37.6737777, 144.5943217', deliver_after_time=(9, 0,), deliver_before_time=(19, 0))

        new_settings.order(7, '-37.8485871,144.6670881', deliver_after_time=(9, 0,), deliver_before_time=(19, 0))
        new_settings.order(8, '-37.8485871,144.6670881', deliver_after_time=(9, 0,), deliver_before_time=(19, 0))
        new_settings.concatenated_order(9, (7, 8))

        new_settings.set_use_vehicle_capacity(True)
        new_settings.set_end_place(hub=2)

        BarcodesFactory(order_id=new_settings.orders_map[5].id, code_data='barcode_1')
        BarcodesFactory(order_id=new_settings.orders_map[6].id, code_data='barcode_2')
        BarcodesFactory(order_id=new_settings.orders_map[6].id, code_data='barcode_3')
        BarcodesFactory(order_id=new_settings.orders_map[6].id, code_data='barcode_4')

        expected = OptimisationExpectation(skipped_orders=0)
        ro_two_id = self.run_optimisation(new_settings, expected)
        self._check_driver_time_filtering_logs(ro_one_id, settings, ro_two_id, new_settings)
        response = self.client.get(f'/api/web/ro/optimisation/{ro_one_id}/export/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        export = ExportReportInstance.objects.get(id=response.json()['id'])
        with export.file.open('rt') as _file:
            csv_data = csv.DictReader(_file)
            for line in csv_data:
                if line['point_type_exact'] == 'break':
                    self.assertEqual(line['point_type'], '')
                    self.assertEqual(line['job_sequence_number'], '2')
                    self.assertEqual(line['predicted_arrival_time'], '12:20')
                    self.assertEqual(line['predicted_departure_time'], '12:30')
                    break
            else:
                self.fail('Break is not found in csv export')

        self.merchant.enable_concatenated_orders = False
        self.merchant.save()

    def _check_driver_time_filtering_logs(self, ro_one_id, settings_one: APISettings,
                                          ro_two_id, settings_two: APISettings):
        optimisation_one = RouteOptimisation.objects.get(id=ro_one_id)
        optimisation_two = RouteOptimisation.objects.get(id=ro_two_id)

        check_count = 0
        for log_item in optimisation_one.optimisation_log.log['full']:
            if log_item.get('event') != EventType.DRIVER_TIME:
                continue
            log_class = log_item_registry.get(log_item.get('event'))
            msg = log_class.build_message(log_item, optimisation_one, [])
            if log_item['params']['driver_id'] == settings_one.drivers_map[1].id:
                self.assertIn('Change max time to 18:40:00 by driver break(18:40:00-19:10:00).', msg)
                check_count += 1
            elif log_item['params']['driver_id'] == settings_one.drivers_map[2].id:
                self.assertIn('Exclude driver time by driver break(11:40:00-15:10:00).', msg)
                check_count += 1

        for log_item in optimisation_two.optimisation_log.log['full']:
            if log_item.get('event') != EventType.DRIVER_TIME:
                continue
            log_class = log_item_registry.get(log_item.get('event'))
            msg = log_class.build_message(log_item, optimisation_two, [])
            if log_item['params']['driver_id'] == settings_two.drivers_map[1].id:
                self.assertIn('Change max time to 18:40:00 by driver break(18:40:00-19:10:00).', msg)
                check_count += 1
            elif log_item['params']['driver_id'] == settings_two.drivers_map[2].id:
                self.assertIn('Change min time to 08:10:00 by driver break(07:40:00-08:10:00).', msg)
                self.assertIn('Change max time to 11:40:00 by driver break(11:40:00-15:10:00).', msg)
                check_count += 1
        self.assertEqual(check_count, 4)

    def test_cant_create_past(self):
        resp = self.client.post(self.api_url, dict(type=OPTIMISATION_TYPES.ADVANCED, day='2020-06-11', options={}))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('day', resp.data['errors'])

    def test_create_advanced_skill_set_service_time(self):
        settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)
        settings.skill(1, service_time=5)
        settings.skill(2, service_time=3)
        settings.skill(3, service_time=0)
        settings.skill(4)
        settings.driver(member_id=1, start_hub=None, end_hub=1, skill_set=(1, 2, 3, 4), end_time=(18, 0), capacity=15)
        settings.driver(member_id=2, start_hub=1, end_hub=1, skill_set=(1, 2, 3, 4), end_time=(18, 0), capacity=15)
        settings.driver(member_id=3, start_hub=2, end_hub=None, skill_set=(1, 2, 3, 4), end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743', skill_set=(1, 2, 3, 4),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881', skill_set=(1, 2),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(3, '-37.8238154,145.0108082', skill_set=(3, 4),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(4, '-37.755938,145.706767', skill_set=(4,),
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.service_time(12)
        settings.set_start_place(hub=1)
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(ServiceTimeCheck(settings.orders_map[1], 5))
        expected.add_check(ServiceTimeCheck(settings.orders_map[2], 5))
        expected.add_check(ServiceTimeCheck(settings.orders_map[3], 0))
        expected.add_check(ServiceTimeCheck(settings.orders_map[4], 12))
        self.run_optimisation(settings, expected)

    def test_create_solo(self):
        settings = SoloAPISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                                   self.merchant, self.manager)
        settings.hub('-37.869197,144.820283', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=15,
                        breaks=[DriverBreakSetting((16, 30), (17, 0), 15)], )
        settings.order(1, '-37.6780953, 145.1290807', driver=1, deliver_before_time=(18, 30))
        settings.order(2, '-37.926451, 144.998992', driver=1, deliver_before_time=(15, 30))
        settings.initiator_driver = settings.drivers_map[1]
        settings.initiator_driver_setting = settings.drivers_setting_map[1]
        expectation = OptimisationExpectation(skipped_orders=0)
        expectation.add_check(NumberFieldConsecutiveCheck())
        # TODO: fix this big waiting
        expectation.add_check(DriverBreaksExactTime(driver_id=settings.drivers_map[1].id,
                                                    breaks=[((9, 46, 22), (16, 45))]))
        self.run_solo_optimisation(settings, expectation)

    def test_optimise_to_last_job(self):
        settings = APISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=None, end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(3, '-37.8238154,145.0108082',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(4, '-37.755938,145.706767',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.set_end_place(last_job=True)
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(EndPointIsOrderCheck(settings.drivers_map[1].id))
        self.run_optimisation(settings, expected)

    def test_optimise_to_default_point(self):
        settings = APISettings(OPTIMISATION_TYPES.SOLO, self._day, self.merchant.timezone,
                               self.merchant, self.manager)
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.location('-37.698763,145.054753', 1, address='19 Rayner St, Altona VIC 3018, Australia')
        settings.driver(member_id=1, start_hub=1, end_hub=None, end_location=1, default_point=1,
                        end_time=(18, 0), capacity=15)
        settings.order(1, '-37.8421644,144.9399743',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.order(2, '-37.8485871,144.6670881',
                       deliver_after_time=(9, 50,), deliver_before_time=(19, 0))
        settings.set_end_place(default_point=True)
        expected = OptimisationExpectation(skipped_orders=0)
        expected.add_check(EndPointIsDefaultLocationCheck(
            driver_id=settings.drivers_map[1].id,
            location={
                'location': {
                    'lat': -37.698763,
                    'lng': 145.054753
                },
                'address': '19 Rayner St, Altona VIC 3018, Australia'
            }
        ))
        self.run_optimisation(settings, expected)
