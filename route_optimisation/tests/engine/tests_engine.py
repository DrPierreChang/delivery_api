import json
import logging
import os
from datetime import date, timedelta

from django.conf import settings as project_settings
from django.test import TestCase, override_settings, tag
from django.utils import timezone

import pytz

from radaro_utils.tests.utils import PerformanceMeasure
from route_optimisation.engine import Engine
from route_optimisation.engine.base_classes.parameters import EngineParameters, JobKind
from route_optimisation.engine.const import Algorithms
from route_optimisation.engine.events import EventHandler
from route_optimisation.tests.engine.optimisation_expectation import (
    OptimisationExpectation,
    OrderExistsInRoute,
    ServiceTimeCheck,
)
from route_optimisation.tests.test_utils.distance_matrix import TestDiMaCache, TestFakeDiMaCache

from ...const import MerchantOptimisationFocus, RoutePointKind
from ...engine.base_classes.result import AssignmentResult
from .engine_settings import EngineSettings

options_file_path_local = os.path.join(project_settings.BASE_DIR, 'route_optimisation', 'tests', 'test_utils',
                                       'cases', 'local')
options_file_path_main = os.path.join(project_settings.BASE_DIR, 'route_optimisation', 'tests', 'test_utils', 'cases')

logger_dev = logging.getLogger('radaro-dev')


class TestROEvents(EventHandler):
    # def dev(self, event: str, msg: str, **kwargs):
    #     logger_dev.debug(f'dev\n{event} {msg} {kwargs}')
    #
    # def dev_msg(self, msg: str, **kwargs):
    #     logger_dev.debug(f'dev msg\n{msg} {kwargs}')
    #
    # def msg(self, msg: str, **kwargs):
    #     logger_dev.info(f'msg\n{msg} {kwargs}')
    #
    # def info(self, event: str, msg: str, **kwargs):
    #     logger_dev.info(f'\n{event} {msg} {kwargs}')
    #
    # def progress(self, **kwargs):
    #     logger_dev.debug(f'progress\n{kwargs}')

    def error(self, error_msg):
        logger_dev.error(f'error\n{error_msg}')


class BaseTestEngineMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timezone = pytz.timezone('Europe/Minsk')
        self.day = (timezone.now().astimezone(self.timezone) + timedelta(days=1)).date()
        self.distance_matrix_cache = TestDiMaCache()

    def optimise(self, params=None, settings: EngineSettings = None, distance_matrix_cache=None,
                 expectation: OptimisationExpectation = None, optimisation_options=None, alg=Algorithms.GROUP):
        params = params or EngineParameters(
            timezone=settings.timezone,
            day=settings.day,
            focus=settings.focus,
            default_job_service_time=settings.job_service_time,
            default_pickup_service_time=settings.pickup_service_time,
            optimisation_options=optimisation_options or dict(
                jobs=[order.to_dict() for order in settings.orders],
                drivers=[driver.to_dict() for driver in settings.drivers],
                use_vehicle_capacity=settings.use_vehicle_capacity,
                required_start_sequence=settings.start_sequences,
            ),
        )
        engine = Engine(
            algorithm=alg,
            event_handler=TestROEvents(),
            distance_matrix_cache=distance_matrix_cache or self.distance_matrix_cache,
        )
        result = engine.run(params=params)
        if expectation:
            expectation.check(self, result, input_params=params)
        return result


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class TestEngineCase(BaseTestEngineMixin, TestCase):

    def test_simple_ro_minsk(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'))
        settings.hub('53.907175,27.449568', hub_id=1)

        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=10)

        settings.order(1, '53.906771,27.532308', driver=1)
        settings.order(2, '53.898275,27.503641')
        expectation = OptimisationExpectation(max_distance=19000, skipped_orders=0)
        result = self.optimise(settings=settings, expectation=expectation)

    @override_settings(ORTOOLS_SEARCH_TIME_LIMIT=30)
    def test_big_ro_melbourne(self):
        return
        distance_matrix_cache = TestFakeDiMaCache()
        settings = EngineSettings(self.day, pytz.timezone('Australia/Melbourne'))
        settings.hub('-37.737002, 144.947164', hub_id=1)
        settings.hub('-37.799676, 144.984108', hub_id=2)
        settings.hub('-37.818369, 145.049278', hub_id=3)
        settings.hub('-37.812139, 145.069618', hub_id=4)
        settings.hub('-37.794428, 145.239808', hub_id=5)

        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=50)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=50)
        settings.driver(member_id=3, start_hub=2, end_hub=2, capacity=50)
        settings.driver(member_id=4, start_hub=2, end_hub=2, capacity=20)
        settings.driver(member_id=5, start_hub=3, end_hub=3, capacity=50)
        settings.driver(member_id=6, start_hub=3, end_hub=3, capacity=20)
        settings.driver(member_id=7, start_hub=4, end_hub=4, capacity=50)
        settings.driver(member_id=8, start_hub=4, end_hub=4, capacity=10)
        settings.driver(member_id=9, start_hub=5, end_hub=5, capacity=50)

        settings.driver(member_id=10, start_hub=5, end_hub=5, capacity=10)
        settings.driver(member_id=11, start_hub=1, end_hub=1, capacity=50)
        settings.driver(member_id=12, start_hub=1, end_hub=1, capacity=50)
        settings.driver(member_id=13, start_hub=2, end_hub=2, capacity=50)
        settings.driver(member_id=14, start_hub=2, end_hub=2, capacity=20)
        settings.driver(member_id=15, start_hub=3, end_hub=3, capacity=50)
        settings.driver(member_id=16, start_hub=3, end_hub=3, capacity=20)
        settings.driver(member_id=17, start_hub=4, end_hub=4, capacity=50)
        settings.driver(member_id=18, start_hub=4, end_hub=4, capacity=10)
        settings.driver(member_id=19, start_hub=5, end_hub=5, capacity=50)

        settings.driver(member_id=20, start_hub=5, end_hub=5, capacity=10)
        settings.driver(member_id=21, start_hub=1, end_hub=1, capacity=50)
        settings.driver(member_id=22, start_hub=1, end_hub=1, capacity=50)
        settings.driver(member_id=23, start_hub=2, end_hub=2, capacity=50)
        settings.driver(member_id=24, start_hub=2, end_hub=2, capacity=20)
        settings.driver(member_id=25, start_hub=3, end_hub=3, capacity=50)
        settings.driver(member_id=26, start_hub=3, end_hub=3, capacity=20)
        settings.driver(member_id=27, start_hub=4, end_hub=4, capacity=50)
        settings.driver(member_id=28, start_hub=4, end_hub=4, capacity=10)
        settings.driver(member_id=29, start_hub=5, end_hub=5, capacity=50)

        settings.driver(member_id=30, start_hub=5, end_hub=5, capacity=10)
        settings.driver(member_id=31, start_hub=1, end_hub=1, capacity=50)
        settings.driver(member_id=32, start_hub=1, end_hub=1, capacity=50)
        settings.driver(member_id=33, start_hub=2, end_hub=2, capacity=50)
        settings.driver(member_id=34, start_hub=2, end_hub=2, capacity=20)
        # settings.driver(member_id=35, start_hub=3, end_hub=3, capacity=50)
        # settings.driver(member_id=36, start_hub=3, end_hub=3, capacity=20)
        # settings.driver(member_id=37, start_hub=4, end_hub=4, capacity=50)
        # settings.driver(member_id=38, start_hub=4, end_hub=4, capacity=10)
        # settings.driver(member_id=39, start_hub=5, end_hub=5, capacity=50)

        settings.order(1, '-37.8421644,144.9399743', capacity=2)
        settings.order(2, '-37.8485871,144.6670881', driver=2)
        settings.order(3, '-37.8238154,145.0108082', driver=3)
        settings.order(4, '-37.755938,145.706767', capacity=2)
        settings.order(5, '-37.8266637,145.2561718', capacity=3)
        settings.order(6, '-37.5860885,144.1168696', capacity=2)
        settings.order(7, '-37.8155292,144.9379085', driver=3)
        settings.order(8, '-37.640818,145.059025', capacity=4)
        settings.order(9, '-37.857186,145.300464')
        settings.order(10, '-38.082057,145.141831', driver=3)
        settings.order(11, '-37.5795883,143.8387151')
        settings.order(12, '-37.698763,145.054753', capacity=3)
        _id = 13

        pickups = [
            '-37.729572, 144.984174',
            '-37.708245, 145.174404',
            '-37.760773, 145.090994',
            '-37.779901, 145.017368',
            '-37.833191, 144.970514',
            '-37.804314, 144.922117',
        ]

        for i in range(225):
            nn = 25
            x, y = i % nn, i // nn
            min_lat, min_lng = -37.673812, 144.848703
            max_lat, max_lng = -37.868878, 145.180675
            lat = min_lat + (max_lat - min_lat) / nn * x
            lng = min_lng + (max_lng - min_lng) / nn * y
            _id += 1
            capacity = (i % 3) + 1
            # pickup_address = None
            # pickup_index = (i + 4) % nn
            # if pickup_index < len(pickups):
            #     pickup_address = pickups[pickup_index]
            # settings.order(_id, '%s,%s' % (lat, lng), pickup_address=pickup_address, capacity=capacity)
            settings.order(_id, '%s,%s' % (lat, lng), capacity=capacity)

        print(_id - 1)

        settings.service_time(5)
        settings.use_vehicle_capacity = True
        expectation = OptimisationExpectation(max_distance=1950000, skipped_orders=3)
        result = self.optimise(
            settings=settings, distance_matrix_cache=distance_matrix_cache, expectation=expectation,
        )
        print(result)

    @override_settings(ORTOOLS_SEARCH_TIME_LIMIT=5, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=7)
    def test_ro_minsk_with_required_jobs_and_required_sequence(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'))
        settings.hub('53.907175,27.449568', hub_id=1)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=10, start_time=(8,), end_time=(10, 0))
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=7, start_time=(8,), end_time=(9, 0))
        settings.order(1, '53.906771,27.532308', pickup_address='53.925965,27.501122', driver=1, capacity=3)
        settings.order(2, '53.898275,27.503641', pickup_address='53.897700, 27.521235', capacity=3)
        settings.order(3, '53.881996,27.512813', pickup_address='53.919803,27.478715', capacity=3)
        settings.order(4, '53.929806, 27.588599', driver=2, capacity=2, allow_skip=False)
        settings.order(5, '53.889130, 27.608861', capacity=3)
        settings.order(6, '53.880998, 27.541758', pickup_address='53.916452, 27.579531', capacity=3, allow_skip=False)
        settings.add_start_sequence({
            'driver_member_id': settings.drivers_map[1].driver_id,
            'sequence': [
                {'point_id': 1, 'point_kind': JobKind.HUB},
                {'point_id': 1, 'point_kind': JobKind.PICKUP},
                {'point_id': 3, 'point_kind': JobKind.PICKUP},
                {'point_id': 3, 'point_kind': JobKind.DELIVERY},
            ]
        })
        expectation = OptimisationExpectation(max_distance=80000, skipped_orders=1)
        expectation.add_check(OrderExistsInRoute(4))
        expectation.add_check(OrderExistsInRoute(6))
        result = self.optimise(settings=settings, expectation=expectation)

    def test_ro_minsk_pickup_no_capacity(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'))
        settings.hub('53.907175,27.449568', hub_id=1)

        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=10)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=7)

        settings.order(1, '53.906771,27.532308', pickup_address='53.925965,27.501122', driver=1, capacity=3)
        settings.order(2, '53.898275,27.503641', pickup_address='53.897700, 27.521235', capacity=3)
        settings.order(3, '53.881996,27.512813', pickup_address='53.919803,27.478715', capacity=3)
        settings.order(4, '53.929806, 27.588599', driver=2, capacity=2)
        settings.order(5, '53.889130, 27.608861', capacity=3)
        settings.order(6, '53.880998, 27.541758', pickup_address='53.916452, 27.579531', capacity=3)
        expectation = OptimisationExpectation(max_distance=70000, skipped_orders=0)
        result = self.optimise(settings=settings, expectation=expectation)

    @override_settings(ORTOOLS_SEARCH_TIME_LIMIT=5, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=7)
    def test_ro_minsk_pickup_with_capacity(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'))
        settings.hub('53.907175,27.449568', hub_id=1)
        settings.hub('53.879482,27.551453', hub_id=2)

        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=11)
        settings.driver(member_id=2, start_hub=2, end_hub=2, capacity=7)

        settings.order(1, '53.906771,27.532308', pickup_address='53.925965,27.501122', capacity=3)
        settings.order(2, '53.898275,27.503641', pickup_address='53.897700, 27.521235', capacity=2)
        settings.order(3, '53.881996,27.512813', pickup_address='53.919803,27.478715', capacity=3)
        settings.order(4, '53.929806, 27.588599', capacity=2)
        settings.order(5, '53.889130, 27.608861', capacity=3)
        settings.order(6, '53.880998, 27.541758', pickup_address='53.916452, 27.579531', capacity=4)
        settings.service_time(5)
        settings.set_pickup_service_time(13)
        settings.use_vehicle_capacity = True
        expectation = OptimisationExpectation(max_distance=63000, skipped_orders=0)
        expectation.add_check(ServiceTimeCheck(settings.orders[1].order_id, 5))
        expectation.add_check(ServiceTimeCheck(settings.orders[1].order_id, 13, is_pickup=True))
        result = self.optimise(settings=settings, expectation=expectation)

    def test_ro_minsk_no_pickup_with_capacity(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'))
        settings.hub('53.907175,27.449568', hub_id=1)

        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=10)
        settings.driver(member_id=2, start_hub=1, end_hub=1, capacity=7)

        settings.order(1, '53.906771,27.532308', driver=1, capacity=3)
        settings.order(2, '53.898275,27.503641', capacity=3)
        settings.order(3, '53.881996,27.512813', capacity=3)
        settings.order(4, '53.929806, 27.588599', driver=2, capacity=2)
        settings.order(5, '53.889130, 27.608861', capacity=3)
        settings.order(6, '53.880998, 27.541758', capacity=3)
        settings.use_vehicle_capacity = True
        expectation = OptimisationExpectation(max_distance=51000, skipped_orders=1)
        result = self.optimise(settings=settings, expectation=expectation)

    def test_ro_minsk_no_pickup_no_capacity(self):
        settings = EngineSettings(self.day, pytz.timezone('Europe/Minsk'))
        settings.hub('53.907175,27.449568', hub_id=1)
        settings.hub('53.879482,27.551453', hub_id=2)
        settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=10)
        settings.driver(member_id=2, start_hub=2, end_hub=2, capacity=7)
        settings.order(1, '53.906771,27.532308', driver=1, capacity=3)
        settings.order(2, '53.898275,27.503641', capacity=3)
        settings.order(3, '53.881996,27.512813', capacity=3)
        settings.order(4, '53.929806, 27.588599', driver=2, capacity=2)
        settings.order(5, '53.889130, 27.608861', capacity=3)
        settings.order(6, '53.880998, 27.541758', capacity=3)
        expectation = OptimisationExpectation(max_distance=45000, skipped_orders=0)
        result = self.optimise(settings=settings, expectation=expectation)

    def test_simple_ro_melbourne_with_memory(self):
        measurements = []
        performance = PerformanceMeasure()
        for _ in range(5):
            settings = EngineSettings(self.day, pytz.timezone('Australia/Melbourne'))
            settings.hub('-37.869197,144.82028300000002', hub_id=1)
            settings.hub('-37.7855699,144.84063459999993', hub_id=2)
            settings.driver(member_id=1, start_hub=2, end_hub=2, capacity=10)
            settings.driver(member_id=2, start_hub=2, end_hub=2, capacity=10)
            settings.driver(member_id=3, start_hub=1, end_hub=1, capacity=10)
            settings.order(1, '-37.8421644,144.9399743')
            settings.order(2, '-37.8485871,144.6670881', driver=2)
            settings.order(3, '-37.8238154,145.0108082', driver=3)
            settings.order(4, '-37.755938,145.706767')
            settings.order(5, '-37.8266637,145.2561718')
            settings.order(6, '-37.5860885,144.1168696')
            settings.order(7, '-37.8155292,144.9379085', driver=3)
            settings.order(8, '-37.640818,145.059025')
            settings.order(9, '-37.857186,145.300464')
            settings.order(10, '-38.082057,145.141831', driver=3)
            settings.order(11, '-37.5795883,143.8387151')
            settings.order(12, '-37.698763,145.054753')
            settings.service_time(5)
            expectation = OptimisationExpectation(max_distance=650000, skipped_orders=0)
            self.optimise(settings=settings, expectation=expectation)
            perf, diff = performance.measure()
            print(perf, diff)
            measurements.append(diff)
        print('Average time: {} sec'.format(sum(m.time for m in measurements) / 3.))
        print('Afterall memory growth: {} MB'.format(sum(m.memory for m in measurements)))
        memory_growth_mb = sum(m.memory for m in measurements)
        self.assertLess(memory_growth_mb, 40)

    def test_skills(self):
        settings = EngineSettings(self.day, pytz.timezone('Australia/Melbourne'))
        settings.hub('-37.869197,144.82028300000002', hub_id=1)
        settings.hub('-37.7855699,144.84063459999993', hub_id=2)

        settings.skill(1, service_time=10)
        settings.skill(2, service_time=0)

        settings.driver(member_id=1, start_hub=2, skill_set=[1, 2], end_time=(18, 0), capacity=4)
        settings.driver(member_id=2, start_hub=2, end_hub=2, skill_set=[1, 2], end_time=(15, 0), capacity=10)
        settings.driver(member_id=3, start_hub=1, end_hub=1, skill_set=[2], end_time=(18, 0), capacity=10)

        settings.order(1, '-37.8421644,144.9399743', skill_set=[1], deliver_after_time=(14,))
        settings.order(2, '-37.8485871,144.6670881', driver=2)
        settings.order(3, '-37.8238154,145.0108082', driver=3)
        settings.order(4, '-37.755938,145.706767', skill_set=[1])
        settings.order(5, '-37.8266637,145.2561718', skill_set=[1, 2])
        settings.order(6, '-37.5860885,144.1168696', skill_set=[1])
        settings.order(7, '-37.8155292,144.9379085', driver=3)
        settings.order(8, '-37.640818,145.059025', skill_set=[1, 2])
        settings.order(9, '-37.857186,145.300464')
        settings.order(10, '-38.082057,145.141831', driver=3)
        settings.order(11, '-37.5795883,143.8387151')
        settings.order(12, '-37.698763,145.054753', skill_set=[2])
        settings.service_time(100)
        expectation = OptimisationExpectation(max_distance=610000, skipped_orders=0)
        result = self.optimise(settings=settings, expectation=expectation)

    def test_simple_ro_use_start_location(self):
        settings = EngineSettings(self.day, pytz.timezone('Australia/Melbourne'))
        settings.location('-37.869197,144.820283', 1)
        settings.location('-37.868197,144.821283', 2)

        settings.driver(1, start_location=1, capacity=10)
        settings.driver(2, start_location=1, capacity=10)
        settings.driver(3, start_location=1, capacity=10)
        settings.driver(4, start_location=1, capacity=10)
        settings.driver(5, start_location=2, capacity=10)
        settings.driver(6, start_location=2, capacity=10)

        _ = [
            settings.order(1, '-37.996221, 145.095882'), settings.order(2, '-38.1836795, 144.467737'),
            settings.order(3, '-38.155597, 145.198333'), settings.order(4, '-37.7719904, 145.4606916'),
            settings.order(5, '-38.1608813, 144.3398197'), settings.order(6, '-37.8095779, 144.9691985'),
            settings.order(7, '-37.925078, 145.004605'), settings.order(8, '-37.6737777, 144.5943217'),
        ]
        settings.service_time(5)
        expectation = OptimisationExpectation(max_distance=350000, skipped_orders=0, skipped_drivers=0)
        result = self.optimise(settings=settings, expectation=expectation)

    def test_assign_4_jobs_to_6_drivers(self):
        settings = EngineSettings(self.day, pytz.timezone('Australia/Melbourne'))
        settings.hub('-37.869197,144.82028300000002', hub_id=1)

        settings.driver(1, start_hub=1, capacity=10)
        settings.driver(2, start_hub=1, capacity=10)
        settings.driver(3, start_hub=1, capacity=10)
        settings.driver(4, start_hub=1, capacity=10)
        settings.driver(5, start_hub=1, capacity=10)
        settings.driver(6, start_hub=1, capacity=10)
        settings.order(1, '-37.6780953, 145.1290807')
        settings.order(2, '-37.926451, 144.998992')
        settings.order(3, '-35.5418094, 144.9643013')
        settings.order(4, '-37.9202176, 145.2230781')
        settings.service_time(5)
        expectation = OptimisationExpectation(max_distance=440000, skipped_orders=0, skipped_drivers=2)
        result = self.optimise(settings=settings, expectation=expectation)

    def test_ro_no_hubs_no_locations(self):
        settings = EngineSettings(self.day, pytz.timezone('Australia/Melbourne'))
        settings.driver(1, capacity=10)
        settings.order(1, '-37.6780953, 145.1290807')
        settings.order(2, '-37.926451, 144.998992')
        settings.order(3, '-35.5418094, 144.9643013')
        settings.order(4, '-37.9202176, 145.2230781')
        settings.service_time(5)
        expectation = OptimisationExpectation(max_distance=355000, skipped_orders=0)
        result = self.optimise(settings=settings, expectation=expectation)

    @override_settings(ORTOOLS_SEARCH_TIME_LIMIT=5, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=7)
    def test_prod_case_wrong_skill_set(self):
        """
        Real case from production. There was problem with assigning jobs by skill_set constraints
        """
        options_file_path = os.path.join(
            options_file_path_main, 'prod_case_wrong_skill_set_options.json')
        with open(options_file_path) as options_data_file:
            options = json.load(options_data_file)

        settings = EngineSettings(date(year=2021, month=2, day=14), pytz.timezone('Australia/Melbourne'))
        expectation = OptimisationExpectation(skipped_orders_max=20, skipped_drivers=0)
        self.optimise(settings=settings, expectation=expectation, optimisation_options=options,
                      distance_matrix_cache=TestDiMaCache('cases/prod_case_wrong_skill_set_dima_cache.json'))

    @override_settings(ORTOOLS_SEARCH_TIME_LIMIT=5, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=7)
    def test_prod_case_use_all_drivers(self):
        """
        Real case from production. There was problem with assigning jobs to all drivers
        """
        options_file_path = os.path.join(
            options_file_path_main, 'prod_case_use_all_drivers_options.json')
        with open(options_file_path) as options_data_file:
            options = json.load(options_data_file)

        settings = EngineSettings(date(year=2021, month=8, day=6), pytz.timezone('Australia/Melbourne'))
        settings.service_time(3)
        settings.set_pickup_service_time(5)
        expectation = OptimisationExpectation(skipped_orders=0, skipped_drivers=0, max_distance=400000)
        result = self.optimise(settings=settings, expectation=expectation, optimisation_options=options,
                               distance_matrix_cache=TestDiMaCache('cases/prod_case_use_all_drivers_dima_cache.json'))

    @override_settings(ORTOOLS_SEARCH_TIME_LIMIT=8, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=8)
    def test_staging_case_use_all_drivers(self):
        """
        Test case from staging. There was problem with assigning jobs to all drivers
        """
        options_file_path = os.path.join(
            options_file_path_main, 'staging_case_use_all_drivers_options.json')
        with open(options_file_path) as options_data_file:
            options = json.load(options_data_file)

        settings = EngineSettings(date(year=2021, month=8, day=29), pytz.timezone('Australia/Melbourne'),
                                  focus=MerchantOptimisationFocus.TIME_BALANCE)
        settings.service_time(5)
        settings.set_pickup_service_time(5)
        expectation = OptimisationExpectation(skipped_orders=0, skipped_drivers=0, max_distance=460000)
        result = self.optimise(
            settings=settings, expectation=expectation, optimisation_options=options,
            distance_matrix_cache=TestDiMaCache('cases/staging_case_use_all_drivers_dima_cache.json')
        )

    @override_settings(ORTOOLS_SEARCH_TIME_LIMIT=5, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=7)
    def test_prod_case_s5_optimisation_855(self):
        options_file_path = os.path.join(
            options_file_path_main, 'prod_case_s5_optimisation_855_options.json')
        with open(options_file_path) as options_data_file:
            options = json.load(options_data_file)
        settings = EngineSettings(date(year=2021, month=9, day=6), pytz.timezone('Australia/Melbourne'),
                                  focus=MerchantOptimisationFocus.MINIMAL_TIME)
        settings.service_time(10)
        settings.set_pickup_service_time(5)
        settings.use_vehicle_capacity = False
        expectation = OptimisationExpectation(skipped_orders=0, skipped_drivers=0, max_distance=700000)
        dima_cache = TestDiMaCache('cases/prod_case_s5_optimisation_855_dima_cache.json')
        self.optimise(
            settings=settings, expectation=expectation,
            optimisation_options=options, distance_matrix_cache=dima_cache,
        )

    @tag('ro_long_running')
    @override_settings(ORTOOLS_SEARCH_TIME_LIMIT=10, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=10,
                       ORTOOLS_ASSIGNMENT_TIME_LIMIT=240, ORTOOLS_MAX_ASSIGNMENT_TIME_LIMIT=360)
    def test_prod_case_s5_optimisation_855_breaks(self):
        options_file_path = os.path.join(
            options_file_path_main, 'prod_case_s5_optimisation_855_options_breaks.json')
        with open(options_file_path) as options_data_file:
            options = json.load(options_data_file)
        settings = EngineSettings(date(year=2021, month=9, day=6), pytz.timezone('Australia/Melbourne'),
                                  focus=MerchantOptimisationFocus.TIME_BALANCE)
        settings.service_time(10)
        settings.set_pickup_service_time(5)
        settings.use_vehicle_capacity = False
        expectation = OptimisationExpectation(skipped_orders=0, skipped_drivers=0, max_distance=700000)
        dima_cache = TestDiMaCache('cases/prod_case_s5_optimisation_855_dima_cache.json')
        result = self.optimise(
            settings=settings, expectation=expectation,
            optimisation_options=options, distance_matrix_cache=dima_cache,
        )
        breaks_count = sum(
            int(point.point_kind == RoutePointKind.BREAK)
            for tour in result.drivers_tours.values()
            for point in tour.points
        )
        self.assertEqual(breaks_count, 7)

    def test_staging_case_s1_optimisation_4141_options(self):
        options_file_path = os.path.join(
            options_file_path_main,
            'staging_case_s1_optimisation_4141_options.json'
        )
        with open(options_file_path) as options_data_file:
            options = json.load(options_data_file)

        settings = EngineSettings(date(year=2022, month=2, day=17), pytz.timezone('Australia/Melbourne'),
                                  focus=MerchantOptimisationFocus.TIME_BALANCE)
        settings.service_time(5)
        settings.set_pickup_service_time(2)
        settings.use_vehicle_capacity = True
        expectation = OptimisationExpectation(skipped_orders=0, skipped_drivers=0, max_distance=85000)
        dima_cache = TestDiMaCache('cases/staging_case_s1_optimisation_4141_dima_cache.json')
        result: AssignmentResult = self.optimise(
            settings=settings, expectation=expectation,
            optimisation_options=options, distance_matrix_cache=dima_cache,
        )

    def test_prod_case_s5_optimisation_8070_options(self):
        options_file_path = os.path.join(
            options_file_path_main,
            'prod_case_s5_optimisation_8070_options.json'
        )
        with open(options_file_path) as options_data_file:
            options = json.load(options_data_file)

        settings = EngineSettings(date(year=2022, month=8, day=1), pytz.timezone('Australia/Melbourne'),
                                  focus=MerchantOptimisationFocus.MINIMAL_TIME)
        settings.service_time(3)
        settings.set_pickup_service_time(3)
        settings.use_vehicle_capacity = False
        expectation = OptimisationExpectation(skipped_orders=0, skipped_drivers=0, max_distance=150000)
        dima_cache = TestDiMaCache('cases/prod_case_s5_optimisation_8070_dima_cache.json')
        result: AssignmentResult = self.optimise(
            settings=settings, expectation=expectation,
            optimisation_options=options, distance_matrix_cache=dima_cache,
        )


class RealCase(BaseTestEngineMixin, TestCase):
    __unittest_skip__ = True
    __unittest_skip_why__ = 'This case only for development'

    def test_case_prod_s5(self):
        ro1_options_name = 'prod_case_s5_optimisation_6457_options.json'
        ro2_options_name = 'prod_case_s5_optimisation_6458_options.json'

        ro1_options_file_path = os.path.join(options_file_path_main, ro1_options_name)
        ro2_options_file_path = os.path.join(options_file_path_main, ro2_options_name)
        with open(ro1_options_file_path) as options_data_file:
            ro1_options = json.load(options_data_file)
        with open(ro2_options_file_path) as options_data_file:
            ro2_options = json.load(options_data_file)

        settings = EngineSettings(date(year=2022, month=5, day=16), pytz.timezone('Australia/Melbourne'),
                                  focus=MerchantOptimisationFocus.TIME_BALANCE)
        settings.service_time(10)
        settings.set_pickup_service_time(3)
        settings.use_vehicle_capacity = False

        from ...dima import RadaroDimaCache
        dima_cache = RadaroDimaCache()
        result: AssignmentResult = self.optimise(
            settings=settings, optimisation_options=ro1_options, distance_matrix_cache=dima_cache,
        )

        result: AssignmentResult = self.optimise(
            settings=settings, optimisation_options=ro2_options, distance_matrix_cache=dima_cache,
        )
