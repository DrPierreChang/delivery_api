from datetime import date

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

import numpy as np
import pytz
from sklearn.cluster import KMeans

from route_optimisation.engine import Algorithms, Engine, EngineParameters
from route_optimisation.tests.engine.tests_engine import TestROEvents
from route_optimisation.tests.test_utils.distance_matrix import TestDiMaCache

from ....const import MerchantOptimisationFocus
from ....intelligent_clustering import Clustering


class IntelligentClusteringView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, **kwargs):
        params = EngineParameters(
            timezone=pytz.timezone('Australia/Melbourne'),
            day=date(year=2021, month=8, day=29),
            default_job_service_time=5,
            default_pickup_service_time=5,
            focus=MerchantOptimisationFocus.TIME_BALANCE,
            optimisation_options=request.data['ro'],
        )
        distance_matrix_cache = TestDiMaCache(request.data['distance_matrix_cache_path'])
        clustering = Clustering(
            # params,  event_handler=TestROEvents(), distance_matrix_cache=RadaroDimaCache()
            params, event_handler=TestROEvents(), distance_matrix_cache=distance_matrix_cache
        )
        clustering.run(request.data.get('merge_steps'))
        distance_matrix_cache.save_distance_matrix(force=True, wait=False)
        # return Response({
        #     'jobs': clustering.jobs_indexes_in_mini_clusters,
        #     'drivers': []
        # })
        # distance_matrix_cache.save_distance_matrix(force=True, wait=False)
        # print(clustering.jobs_indexes_in_big_clusters)
        # print(clustering.drivers_indexes_in_big_clusters)
        return Response({
            'jobs': clustering.jobs_indexes_in_big_clusters,
            'drivers': clustering.drivers_indexes_in_big_clusters,
            'history': clustering.history,
        })


class ClusteringView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, **kwargs):
        jobs_locations = []
        for job in request.data['ro']['jobs']:
            locs = list(map(float, map(str.strip, job['deliver_address'].split(','))))
            jobs_locations.append(locs)

        X = np.array(jobs_locations)
        kmeans = KMeans(n_clusters=request.data['n_clusters'], random_state=0)
        y = kmeans.fit_predict(X)
        return Response(y)


class OptimisationExampleView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, **kwargs):
        optimisation_options = request.data['optimisation_options']
        distance_matrix_cache_path = request.data['distance_matrix_cache_path']
        params = EngineParameters(
            timezone=pytz.timezone('Australia/Melbourne'),
            day=date(year=2021, month=8, day=29),
            default_job_service_time=5,
            default_pickup_service_time=5,
            optimisation_options=optimisation_options,
        )
        # distance_matrix_cache = TestDiMaCache('cases/staging_case_use_all_drivers_dima_cache.json')
        distance_matrix_cache = TestDiMaCache(distance_matrix_cache_path)
        engine = Engine(
            algorithm=Algorithms.ONE_DRIVER,
            event_handler=TestROEvents(),
            distance_matrix_cache=distance_matrix_cache,
            algorithm_params={'search_time_limit': 2}
        )
        result = engine.run(params=params)

        routes = []
        for dr, tour in result.drivers_tours.items():
            points = []
            for point in tour.points:
                points.append({'kind': point.point_kind, 'loc': point.location})
            routes.append({'driver_id': dr, 'points': points})
        return Response({'routes': routes})
