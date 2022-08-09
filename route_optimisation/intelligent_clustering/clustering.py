from collections import defaultdict
from operator import attrgetter
from typing import List, Optional

from route_optimisation.engine import EngineParameters
from routing.context_managers import GoogleApiRequestsTracker

from ..const import GOOGLE_API_REQUESTS_LIMIT
from ..engine.dima import DistanceMatrixCache, set_dima_cache
from ..engine.events import EventHandler, set_event_handler
from ..logging import EventType
from .big_clusters import BigClustersManager
from .merge import MergeMiniClusters
from .mini_clusters import MergeConstraint, MiniClustersManager


class Clustering:
    def __init__(self, params: EngineParameters, event_handler: EventHandler,
                 distance_matrix_cache: DistanceMatrixCache = None):
        self.params = params
        self.mini_clusters = MiniClustersManager(params.jobs, params.drivers, params)
        self.big_clusters: Optional[BigClustersManager] = None
        self.clusters_merger: Optional[MergeMiniClusters] = None
        self.event_handler: EventHandler = event_handler
        self.distance_matrix_cache: DistanceMatrixCache = distance_matrix_cache or DistanceMatrixCache()
        self.api_requests_tracker = GoogleApiRequestsTracker(limit=GOOGLE_API_REQUESTS_LIMIT)

    def run(self, steps_count):
        with self.api_requests_tracker:
            with set_event_handler(self.event_handler), set_dima_cache(self.get_distance_matrix_cache()):
                self.mini_clusters.simple_clustering_kmeans_by_location()
                self.mini_clusters.build_inner_dima_and_split()
                self.mini_clusters.build_outer_dima()

                if self.mini_clusters.skipped_drivers:
                    skipped_drivers_ids = list(map(attrgetter('member_id'), self.mini_clusters.skipped_drivers))
                    event_kwargs = {'objects': skipped_drivers_ids, 'code': 'not_accessible_drivers'}
                    self.event_handler.info(EventType.SKIPPED_OBJECTS, msg=None, **event_kwargs)
                if self.mini_clusters.skipped_jobs:
                    skipped_orders_ids = list(map(attrgetter('id'), self.mini_clusters.skipped_jobs))
                    event_kwargs = {'objects': skipped_orders_ids, 'code': 'not_accessible_orders'}
                    self.event_handler.info(EventType.SKIPPED_OBJECTS, msg=None, **event_kwargs)

                self.big_clusters = BigClustersManager(
                    self.params.jobs, self.params.drivers, self.mini_clusters, self.params
                )
                constraints: List[MergeConstraint] = self.mini_clusters.collect_constraints()
                self.clusters_merger = MergeMiniClusters(self.big_clusters, constraints)
                clusters = self.clusters_merger.merge_mini_clusters(steps_count)
                if clusters is not None:
                    self.big_clusters.set_clusters(clusters)

    @property
    def clustered_params(self) -> List[EngineParameters]:
        clusters = defaultdict(lambda: defaultdict(list))
        for cluster_index, job in zip(self.big_clusters.clusters_indexes, self.params.jobs):
            clusters[cluster_index]['jobs'].append(job)
        for cluster_index, driver in zip(self.big_clusters.drivers_clusters_indexes, self.params.drivers):
            clusters[cluster_index]['drivers'].append(driver)
        clusters.pop(-1, None)  # -1 - skipped jobs and drivers, so ignore them
        result_params = []
        for cluster_data in clusters.values():
            params = EngineParameters(
                timezone=self.params.timezone,
                default_job_service_time=self.params.default_job_service_time,
                default_pickup_service_time=self.params.default_pickup_service_time,
                day=self.params.day,
                focus=self.params.focus,
                use_vehicle_capacity=self.params.use_vehicle_capacity,
                jobs=[],
                drivers=[],
                required_start_sequence=None,
            )
            params.jobs = cluster_data['jobs']
            params.drivers = cluster_data['drivers']
            required_start_sequence = [
                req for req in self.params.required_start_sequence
                if req.driver_member_id in list(map(attrgetter('member_id'), params.drivers))
            ] if self.params.required_start_sequence else None
            if required_start_sequence:
                params.required_start_sequence = required_start_sequence
            result_params.append(params)
        return result_params

    @property
    def jobs_indexes_in_mini_clusters(self):
        return self.mini_clusters.clusters_indexes

    @property
    def jobs_indexes_in_big_clusters(self):
        return self.big_clusters.clusters_indexes

    @property
    def drivers_indexes_in_big_clusters(self):
        return self.big_clusters.drivers_clusters_indexes

    @property
    def history(self):
        result = []
        for item_name, item_result in self.clusters_merger.history:
            jobs, drivers = self.big_clusters.recalc_cluster_indexes_for_big_clusters(item_result.clusters)
            result.append(dict(name=item_name, jobs=jobs, drivers=drivers))
        return result

    def get_distance_matrix_cache(self):
        return self.distance_matrix_cache
