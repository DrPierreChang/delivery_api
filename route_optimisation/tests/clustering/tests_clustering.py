import copy
import json
import os
from datetime import date
from operator import attrgetter
from unittest import TestCase

from django.conf import settings as project_settings

import pytz

from route_optimisation.const import MerchantOptimisationFocus
from route_optimisation.engine import EngineParameters, set_dima_cache
from route_optimisation.engine.events import set_event_handler
from route_optimisation.intelligent_clustering import Clustering
from route_optimisation.intelligent_clustering.mini_clusters import MiniClustersManager
from route_optimisation.intelligent_clustering.splitting_jobs import (
    AssignedDriverSplit,
    DistanceSplit,
    InnerDiMaBuilderSplit,
    SkillsSplit,
    TimeSplit,
)
from route_optimisation.tests.engine.tests_engine import TestROEvents
from route_optimisation.tests.test_utils.distance_matrix import TestDiMaCache
from routing.google.registry import merchant_registry

options_file_path_main = os.path.join(project_settings.BASE_DIR, 'route_optimisation', 'tests', 'test_utils', 'cases')


class TestClusteringClass(TestCase):
    lng_separator = 144.6718

    @staticmethod
    def run_clustering(optimisation_options_file_name):
        options_file_path = os.path.join(options_file_path_main, optimisation_options_file_name)
        with open(options_file_path) as options_data_file:
            optimisation_options = json.load(options_data_file)
        params = EngineParameters(
            timezone=pytz.timezone('Australia/Melbourne'),
            day=date(year=2021, month=9, day=16),
            default_job_service_time=5,
            default_pickup_service_time=5,
            focus=MerchantOptimisationFocus.TIME_BALANCE,
            optimisation_options=optimisation_options,
        )
        distance_matrix_cache = TestDiMaCache('cases/clustering_cases_dima_cache.json')
        with merchant_registry.suspend_warning():
            clustering = Clustering(
                params, event_handler=TestROEvents(), distance_matrix_cache=distance_matrix_cache
            )
            clustering.run(20)
        # distance_matrix_cache.save_distance_matrix(force=True, wait=False)  # for dev purposes
        return clustering.clustered_params

    def test_simple_case_2_clusters_4_drivers(self):
        result = self.run_clustering('clustering_case_1.json')
        self.assertEqual(len(result), 2)
        result.sort(key=lambda x: len(x.jobs))
        self.assertEqual(len(result[0].drivers), 2)
        self.assertEqual(len(result[1].drivers), 2)
        self.assertEqual(len(result[0].jobs), 129)
        self.assertEqual(len(result[1].jobs), 132)
        self.assertEqual(sorted(list(map(lambda dr: dr.id, result[0].drivers))), [100, 101])
        self.assertEqual(sorted(list(map(lambda dr: dr.id, result[1].drivers))), [200, 201])
        for job in result[0].jobs:
            lng = float(job.deliver_address.split(',')[1])
            self.assertTrue(lng > self.lng_separator, f'{job.id}')
        for job in result[1].jobs:
            lng = float(job.deliver_address.split(',')[1])
            self.assertTrue(lng < self.lng_separator, f'{job.id}')

    def test_skillset_case_2_clusters_4_drivers(self):
        result = self.run_clustering('clustering_case_2.json')
        self.assertEqual(len(result), 2)
        result.sort(key=lambda x: len(x.jobs))
        self.assertEqual(len(result[0].drivers), 2)
        self.assertEqual(len(result[1].drivers), 2)
        self.assertEqual(len(result[0].jobs), 129)
        self.assertEqual(len(result[1].jobs), 132)
        self.assertEqual(sorted(list(map(lambda dr: dr.id, result[0].drivers))), [101, 200])
        self.assertEqual(sorted(list(map(lambda dr: dr.id, result[1].drivers))), [100, 201])
        for job in result[0].jobs:
            lng = float(job.deliver_address.split(',')[1])
            self.assertTrue(lng > self.lng_separator, f'{job.id}')
        for job in result[1].jobs:
            lng = float(job.deliver_address.split(',')[1])
            self.assertTrue(lng < self.lng_separator, f'{job.id}')

    def test_different_service_time_case_2_clusters_5_drivers(self):
        result = self.run_clustering('clustering_case_3.json')
        self.assertEqual(len(result), 2)
        result.sort(key=lambda x: len(x.jobs))
        self.assertEqual(len(result[0].drivers), 3)
        self.assertEqual(len(result[1].drivers), 2)
        self.assertEqual(len(result[0].jobs), 129)
        self.assertEqual(len(result[1].jobs), 132)
        self.assertEqual(sorted(list(map(lambda dr: dr.id, result[0].drivers))), [100, 101, 300])
        self.assertEqual(sorted(list(map(lambda dr: dr.id, result[1].drivers))), [200, 201])
        for job in result[0].jobs:
            lng = float(job.deliver_address.split(',')[1])
            self.assertTrue(lng > self.lng_separator, f'{job.id}')
        for job in result[1].jobs:
            lng = float(job.deliver_address.split(',')[1])
            self.assertTrue(lng < self.lng_separator, f'{job.id}')

    def test_capacity_case_2_clusters_5_drivers(self):
        result = self.run_clustering('clustering_case_4.json')
        self.assertEqual(len(result), 2)
        result.sort(key=lambda x: len(x.jobs))
        self.assertEqual(len(result[0].drivers), 2)
        self.assertEqual(len(result[1].drivers), 3)
        self.assertEqual(len(result[0].jobs), 129)
        self.assertEqual(len(result[1].jobs), 132)
        self.assertEqual(sorted(list(map(lambda dr: dr.id, result[0].drivers))), [100, 101])
        self.assertEqual(sorted(list(map(lambda dr: dr.id, result[1].drivers))), [200, 201, 300])
        for job in result[0].jobs:
            lng = float(job.deliver_address.split(',')[1])
            self.assertTrue(lng > self.lng_separator, f'{job.id}')
        for job in result[1].jobs:
            lng = float(job.deliver_address.split(',')[1])
            self.assertTrue(lng < self.lng_separator, f'{job.id}')

    def test_pickup_case_2_clusters_5_drivers(self):
        result = self.run_clustering('clustering_case_5.json')
        self.assertEqual(len(result), 2)
        result.sort(key=lambda x: len(x.jobs))
        self.assertEqual(len(result[0].drivers), 3)
        self.assertEqual(len(result[1].drivers), 2)
        self.assertEqual(len(result[0].jobs), 80)
        self.assertEqual(len(result[1].jobs), 92)
        self.assertEqual(sorted(list(map(lambda dr: dr.id, result[0].drivers))), [100, 101, 300])
        self.assertEqual(sorted(list(map(lambda dr: dr.id, result[1].drivers))), [200, 201])
        for job in result[0].jobs:
            lng = float(job.deliver_address.split(',')[1])
            self.assertTrue(lng > self.lng_separator, f'{job.id}')
        for job in result[1].jobs:
            lng = float(job.deliver_address.split(',')[1])
            self.assertTrue(lng < self.lng_separator, f'{job.id}')


class TestClusteringParts(TestCase):

    @staticmethod
    def do_kmeans_sample():
        options_file_path = os.path.join(options_file_path_main, 'clustering_case_small.json')
        with open(options_file_path) as options_data_file:
            options = json.load(options_data_file)
        params = EngineParameters(
            timezone=pytz.timezone('Australia/Melbourne'),
            day=date(year=2021, month=9, day=16),
            default_job_service_time=5,
            default_pickup_service_time=5,
            focus=MerchantOptimisationFocus.TIME_BALANCE,
            optimisation_options=options,
        )
        with set_event_handler(TestROEvents()), set_dima_cache(TestDiMaCache('cases/clustering_cases_dima_cache.json')):
            mini_clusters = MiniClustersManager(params.jobs, params.drivers, params)
            mini_clusters.simple_clustering_kmeans_by_location()
        return mini_clusters

    def test_kmeans(self):
        mini_clusters = self.do_kmeans_sample()
        self.assertEqual(sorted(list(map(attrgetter('index'), mini_clusters.clusters))), list(range(8)))
        clusters_with_pickup_pointer = list(filter(lambda cl: cl.pickup_location_pointers, mini_clusters.clusters))
        self.assertEqual(len(clusters_with_pickup_pointer), 1)
        cluster_with_pickup_pointer = clusters_with_pickup_pointer[0]
        self.assertEqual(cluster_with_pickup_pointer.center_location, '-38.313877,144.687243')
        pickup_counter = 0
        for cluster in mini_clusters.clusters:
            if cluster == cluster_with_pickup_pointer:
                continue
            for job_obj in cluster.job_objects:
                for pickup_obj in job_obj.pickups:
                    self.assertEqual(pickup_obj.location_pointer.pointer_object, cluster_with_pickup_pointer)
                    self.assertEqual(pickup_obj.location_pointer.pointed_location,
                                     cluster_with_pickup_pointer.center_location)
                    pickup_counter += 1
        self.assertEqual(pickup_counter, 3)
        expected_centers = {
            '-38.2912325,144.9978405', '-38.313877,144.687243', '-38.36713779999999,145.1872337',
            '-38.3690667,144.9023724', '-38.19444379999999,144.4670924', '-38.3334194,144.0379958',
            '-38.1730141,144.3368884', '-38.326597,144.3096471',
        }
        for cluster in mini_clusters.clusters:
            expected_centers.remove(cluster.center_location)
        self.assertEqual(len(expected_centers), 0)

    def test_splitters(self):
        mini_clusters = self.do_kmeans_sample()
        distance_matrix_cache = TestDiMaCache('cases/clustering_cases_dima_cache.json')
        with merchant_registry.suspend_warning(), set_event_handler(TestROEvents()), \
                set_dima_cache(distance_matrix_cache):
            mini_clusters.do_split(SkillsSplit)
            self.assertEqual(mini_clusters.clusters_count, 10)
            mini_clusters.do_split(TimeSplit)
            self.assertEqual(mini_clusters.clusters_count, 12)
            mini_clusters.do_split(AssignedDriverSplit)
            self.assertEqual(mini_clusters.clusters_count, 13)

            for cluster in mini_clusters.clusters:
                cluster.build_inner_dima()
                if mini_clusters.inner_matrix is None:
                    mini_clusters.inner_matrix = copy.copy(cluster.inner_matrix)
                else:
                    mini_clusters.inner_matrix.update(cluster.inner_matrix)

            mini_clusters.do_split(InnerDiMaBuilderSplit)
            self.assertEqual(mini_clusters.clusters_count, 14)
            mini_clusters.do_split(DistanceSplit)
            self.assertEqual(mini_clusters.clusters_count, 15)

            self.assertEqual(len(mini_clusters.skipped_job_objects), 0)
            self.assertEqual(len(mini_clusters.skipped_drivers), 0)
            mini_clusters.build_outer_dima()
            self.assertEqual(mini_clusters.clusters_count, 14)
            self.assertEqual(len(mini_clusters.skipped_jobs), 1)
            self.assertEqual(mini_clusters.skipped_jobs[0].id, 110017)
            self.assertEqual(len(mini_clusters.skipped_drivers), 2)
            self.assertIn(mini_clusters.skipped_drivers[0].id, (101, 102))
            self.assertIn(mini_clusters.skipped_drivers[1].id, (101, 102))

        expected_centers = {
            '-38.2912325,144.9978405', '-38.31968200000001,144.7073346', '-38.313877,144.687243',
            '-38.3374831,145.1684034', '-38.3690667,144.9023724', '-38.313709,145.193742',
            '-38.3802623,144.8509846', '-38.19444379999999,144.4670924', '-38.288297,144.612241',
            '-38.3334194,144.0379958', '-38.1546862,144.3038567', '-38.326597,144.3096471',
            '-38.1818969,144.3415457', '-38.1845189,144.3124051'
        }
        for cluster in mini_clusters.clusters:
            expected_centers.remove(cluster.center_location)
        self.assertEqual(len(expected_centers), 0)

    def test_collect_constraints(self):
        mini_clusters = self.do_kmeans_sample()
        distance_matrix_cache = TestDiMaCache('cases/clustering_cases_dima_cache.json')
        with merchant_registry.suspend_warning(), set_event_handler(TestROEvents()), \
                set_dima_cache(distance_matrix_cache):
            mini_clusters.build_inner_dima_and_split()
            mini_clusters.build_outer_dima()
            constraints = mini_clusters.collect_constraints()
        self.assertEqual(len(constraints), 4)
        constraints_by_drivers_count = {
            1: [(100,), (200,), (201,)],
            3: [(100, 200, 201,)],
        }
        constraints_by_clusters_count = [11, 1, 1, 1]
        for constraint in constraints:
            drivers_ids = tuple(sorted(map(attrgetter('id'), constraint.drivers)))
            constraints_by_drivers_count[len(drivers_ids)].remove(drivers_ids)
            constraints_by_clusters_count.remove(len(constraint.clusters))
        for v in constraints_by_drivers_count.values():
            self.assertEqual(len(v), 0)
        self.assertEqual(len(constraints_by_clusters_count), 0)
