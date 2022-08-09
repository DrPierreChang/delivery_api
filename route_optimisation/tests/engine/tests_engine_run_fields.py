from datetime import date, datetime, time
from unittest import TestCase

import pytz

from merchant.models import Hub
from route_optimisation.const import MerchantOptimisationFocus, RoutePointKind
from route_optimisation.engine import AssignmentResult, EngineParameters
from route_optimisation.engine.base_classes.result import DriverTour, Point
from route_optimisation.engine.errors import NoSolutionFoundError
from route_optimisation.models import DriverRouteLocation
from tasks.models import Order


class TestEngineParametersDict(TestCase):

    def test_engine_parameters(self):
        params = EngineParameters(
            timezone=pytz.timezone('Australia/Melbourne'),
            day=date(year=2021, month=8, day=29),
            default_job_service_time=5,
            default_pickup_service_time=5,
            focus=MerchantOptimisationFocus.TIME_BALANCE,
            optimisation_options={
                'jobs': [
                    {
                        'id': 1, 'order_id': 1000001, 'driver_member_id': None,
                        'deliver_address': '53.30,27.30',
                        'deliver_after': None, 'deliver_before': '2021-08-29T19:00:00+10:00',
                        'pickups': [{
                            'pickup_id': 31, 'pickup_address': '53.40,27.40',
                            'pickup_after': '2021-08-29T11:00:00+10:00',
                            'pickup_before': '2021-08-29T19:00:00+10:00',
                            'capacity': 100, 'service_time': 2
                        }],
                        'capacity': None, 'skill_set': [1, 2], 'service_time': None,
                        'allow_skip': True,
                    },
                    {
                        'id': 2, 'order_id': 1000002, 'driver_member_id': 1000001,
                        'deliver_address': '53.31,27.31',
                        'deliver_after': None, 'deliver_before': '2021-08-29T19:00:00+10:00',
                        'pickups': [
                            {
                                'pickup_id': 32, 'pickup_address': '53.40,27.40',
                                'pickup_after': None,
                                'pickup_before': None,
                                'capacity': None, 'service_time': None
                            },
                            {
                                'pickup_id': 33, 'pickup_address': '53.40,27.40',
                                'pickup_after': None,
                                'pickup_before': '2021-08-29T19:00:00+10:00',
                                'capacity': 100, 'service_time': 22
                            },
                        ],
                        'capacity': None, 'skill_set': [1, 2, 3], 'service_time': None,
                        'allow_skip': False,
                    },
                ],
                'drivers': [
                    {
                        'id': 1, 'member_id': 1000001,
                        'start_time': '08:00:00', 'end_time': '17:00:00',
                        'start_hub': {'id': 21, 'location': '53.1,27.1'},
                        'end_hub': {'id': 22, 'location': '53.2,27.2'},
                        'start_location': None, 'end_location': None,
                        'capacity': None, 'skill_set': [1, 2, 3, 4],
                        'breaks': [
                            {'start_time': '11:00:00', 'end_time': '11:30:00', 'diff_allowed': None},
                            {'start_time': '14:00:00', 'end_time': '14:30:00', 'diff_allowed': 15}
                        ]
                    },
                    {
                        'id': 2, 'member_id': 1000002,
                        'start_time': '08:00:00', 'end_time': '17:00:00',
                        'start_hub': None,
                        'end_hub': None,
                        'start_location': {'id': 121, 'location': '53.1,27.1', 'address': 'Adr1'},
                        'end_location': {'id': 122, 'location': '53.2,27.2', 'address': 'Adr2'},
                        'capacity': None, 'skill_set': [1, 2, 3, 4],
                        'breaks': [
                            {'start_time': '11:00:00', 'end_time': '11:30:00', 'diff_allowed': None},
                            {'start_time': '14:00:00', 'end_time': '14:30:00', 'diff_allowed': 15}
                        ]
                    },
                ],
                'use_vehicle_capacity': False,
                'service_time': 5,
                'pickup_service_time': 5,
                'required_start_sequence': [
                    {
                        'driver_member_id': 1000001,
                        'sequence': [
                            {
                                'point_id': 21,
                                'point_kind': 'hub',
                            },
                            {
                                'point_id': 2,
                                'point_kind': 'delivery',
                            },
                        ]
                    }
                ],
            }
        )
        self.maxDiff = None
        dict_result = params.to_dict()
        object_result = EngineParameters.from_dict(dict_result)
        dict_result_2 = object_result.to_dict()
        self.assertEqual(dict_result, dict_result_2)
        self.assertEqual(object_result.timezone, pytz.timezone('Australia/Melbourne'))
        self.assertEqual(object_result.day, date(year=2021, month=8, day=29))
        self.assertEqual(object_result.default_job_service_time, 5)
        self.assertEqual(object_result.default_pickup_service_time, 5)
        self.assertFalse(object_result.use_vehicle_capacity)
        self.assertEqual(object_result.focus, MerchantOptimisationFocus.TIME_BALANCE)
        self.assertEqual(len(object_result.jobs), 2)
        self.assertEqual(len(object_result.jobs[1].pickups), 2)
        self.assertEqual(len(object_result.drivers), 2)
        self.assertEqual(len(object_result.drivers[0].breaks), 2)
        self.assertIsNotNone(object_result.drivers[0].start_hub)
        self.assertIsNone(object_result.drivers[0].end_location)
        self.assertIsNone(object_result.drivers[1].end_hub)
        self.assertIsNotNone(object_result.drivers[1].start_location)
        self.assertEqual(len(object_result.required_start_sequence), 1)
        self.assertEqual(object_result.required_start_sequence[0].driver_member_id, 1000001)
        self.assertEqual(len(object_result.required_start_sequence[0].sequence), 2)


class TestEngineResultDict(TestCase):
    def test_exception(self):
        self.maxDiff = None
        assignment_result = AssignmentResult.failed_assignment(NoSolutionFoundError('No solution found'))
        dict_result = assignment_result.to_dict()
        assignment_result_2 = AssignmentResult.from_dict(dict_result)
        dict_result_2 = assignment_result_2.to_dict()
        self.assertEqual(dict_result, dict_result_2)
        self.assertFalse(assignment_result_2.good)
        self.assertIsNone(assignment_result_2.drivers_tours)
        self.assertIsNone(assignment_result_2.skipped_drivers)
        self.assertIsNone(assignment_result_2.skipped_orders)
        self.assertIsNone(assignment_result_2.driving_distance)
        self.assertIsNone(assignment_result_2.driving_time)

    @staticmethod
    def get_time(t):
        return datetime.combine(date(2021, 8, 29), time(*t)).astimezone(pytz.timezone('Australia/Melbourne'))

    def test_results(self):
        self.maxDiff = None
        assignment_result = AssignmentResult(
            drivers_tours={
                1: DriverTour(
                    points=[
                        Point(point_prototype={'id': 21}, model_class=Hub, point_kind=RoutePointKind.HUB,
                              location='53.1,27.1', previous=None, service_time=0, driving_time=0, distance=0,
                              start_time=self.get_time((8, 0)), end_time=self.get_time((8, 0)),
                              polyline=None, utilized_capacity=0),
                        Point(point_prototype={'id': 31, 'parent_order_id': 32},
                              model_class=Order, point_kind=RoutePointKind.PICKUP,
                              location='53.1,27.2', previous=None, service_time=300, driving_time=600, distance=100,
                              start_time=self.get_time((8, 10)), end_time=self.get_time((8, 15)),
                              polyline='asdasdqwdasd', utilized_capacity=5),
                        Point(point_prototype=None, model_class=None, point_kind=RoutePointKind.BREAK,
                              location=None, previous=None, service_time=300, driving_time=0, distance=0,
                              start_time=self.get_time((8, 25)), end_time=self.get_time((8, 30)),
                              polyline=None, utilized_capacity=5),
                        Point(point_prototype={'id': 32}, model_class=Order, point_kind=RoutePointKind.DELIVERY,
                              location='53.1,27.3', previous=None, service_time=300, driving_time=100, distance=100,
                              start_time=self.get_time((8, 40)), end_time=self.get_time((8, 45)),
                              polyline=None, utilized_capacity=0),
                        Point(point_prototype={'id': 41, 'location': '', 'address': 'Addr1'},
                              model_class=DriverRouteLocation, point_kind=RoutePointKind.LOCATION,
                              location='53.1,27.4', previous=None, service_time=0, driving_time=100, distance=100,
                              start_time=self.get_time((9, 0)), end_time=self.get_time((9, 0)),
                              polyline=None, utilized_capacity=0),
                    ],
                    driving_time=100, full_time=1000, driving_distance=10000
                ),
            },
            skipped_orders=[1010, 1011],
            skipped_drivers=[2, 3],
            driving_time=10000,
            driving_distance=100000,
        )
        dict_result = assignment_result.to_dict()
        assignment_result_2 = AssignmentResult.from_dict(dict_result)
        dict_result_2 = assignment_result_2.to_dict()
        self.assertEqual(dict_result, dict_result_2)
        self.assertTrue(assignment_result_2.good)
        self.assertEqual(len(assignment_result_2.drivers_tours), 1)
        self.assertEqual(assignment_result_2.drivers_tours[1].points[0].point_prototype, {'id': 21})
        self.assertEqual(assignment_result_2.drivers_tours[1].points[0].model_class, Hub)
        self.assertEqual(assignment_result_2.drivers_tours[1].points[2].point_kind, RoutePointKind.BREAK)
        self.assertEqual(assignment_result_2.drivers_tours[1].points[2].location, None)
        self.assertEqual(assignment_result_2.drivers_tours[1].points[3].service_time, 300)
        self.assertEqual(assignment_result_2.drivers_tours[1].points[3].driving_time, 100)
        self.assertEqual(assignment_result_2.drivers_tours[1].points[4].distance, 100)
        self.assertEqual(assignment_result_2.drivers_tours[1].points[4].start_time, self.get_time((9, 0)))
        self.assertEqual(assignment_result_2.drivers_tours[1].points[3].end_time, self.get_time((8, 45)))
        self.assertEqual(assignment_result_2.drivers_tours[1].points[1].polyline, 'asdasdqwdasd')
        self.assertEqual(assignment_result_2.drivers_tours[1].points[1].utilized_capacity, 5)

        self.assertEqual(len(assignment_result_2.skipped_drivers), 2)
        self.assertEqual(len(assignment_result_2.skipped_orders), 2)
        self.assertIsNotNone(assignment_result_2.driving_distance)
        self.assertIsNotNone(assignment_result_2.driving_time)
