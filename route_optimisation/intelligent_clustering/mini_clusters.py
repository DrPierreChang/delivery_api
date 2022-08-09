import copy
import operator
from collections import defaultdict
from functools import reduce
from operator import attrgetter
from typing import Dict, List, Type

import numpy as np
from sklearn.cluster import KMeans

from route_optimisation.engine import ROError
from route_optimisation.engine.base_classes.parameters import Driver, EngineParameters, Job
from route_optimisation.engine.events import event_handler
from route_optimisation.engine.ortools.distance_matrix import DistanceMatrixBuilder
from route_optimisation.intelligent_clustering.splitting_jobs import (
    AssignedDriverSplit,
    DistanceSplit,
    InnerDiMaBuilderSplit,
    OuterDiMaBuilderSplit,
    SkillsSplit,
    SplitBase,
    TimeSplit,
)
from route_optimisation.intelligent_clustering.utils import (
    Cluster,
    JobObject,
    LocationPointer,
    MergeConstraint,
    MiniCluster,
    PickupJobObject,
    get_location_point,
)
from routing.utils import latlng_dict_from_str


class MiniClustersManager:
    def __init__(self, jobs: List[Job], drivers: List[Driver], params: EngineParameters):
        self.jobs: List[Job] = jobs
        self.job_objects: List[JobObject] = [JobObject(index, job) for index, job in enumerate(jobs)]
        self.skipped_jobs: List[Job] = []
        self.skipped_job_objects: List[JobObject] = []
        self.unique_pickups_location_pointers_map: Dict[LocationPointer, List[PickupJobObject]] = {}
        self.unique_pickups_locations: List[LocationPointer] = []
        self._init_pickup()
        self.drivers: List[Driver] = drivers
        self.skipped_drivers: List[Driver] = []
        self.params: EngineParameters = params
        self.clusters_indexes = []
        self.pickup_clusters_indexes = []
        self.clusters_count = None
        self.clusters: List[MiniCluster] = []
        self.inner_matrix = None
        self.outer_matrix = None

    def _init_pickup(self):
        unique_pickups_locations_str_map: Dict[str, List[PickupJobObject]] = defaultdict(list)
        for job_obj in self.job_objects:
            for pickup in job_obj.pickups:
                unique_pickups_locations_str_map[pickup.pickup_address].append(pickup)
        self.unique_pickups_location_pointers_map: Dict[LocationPointer, List[PickupJobObject]] = {
            LocationPointer(pickup_location): pickups
            for pickup_location, pickups in unique_pickups_locations_str_map.items()
        }
        for pickup_location_pointer, pickups in self.unique_pickups_location_pointers_map.items():
            for pickup in pickups:
                pickup.bound_location_pointer(pickup_location_pointer)
        self.unique_pickups_locations: List[LocationPointer] = list(self.unique_pickups_location_pointers_map.keys())

    def _recalc_clusters_list(self):
        self.clusters = []
        cluster_index_jobs_map = defaultdict(list)
        cluster_index_pickups_map = defaultdict(list)
        for index, job in zip(self.clusters_indexes, self.job_objects):
            cluster_index_jobs_map[index].append(job)
        for index, pickup_location in zip(self.pickup_clusters_indexes, self.unique_pickups_locations):
            cluster_index_pickups_map[index].append(pickup_location)
        cluster_index_jobs_map.pop(-1, None)  # -1 - skipped jobs and drivers, so ignore them
        self.clusters = [
            Cluster(index, jobs, pickup_location_pointers=cluster_index_pickups_map.get(index))
            for index, jobs in cluster_index_jobs_map.items()
        ]
        for cluster in self.clusters:
            cluster.inner_matrix = self.inner_matrix

    def simple_clustering_kmeans_by_location(self):
        points_count, jobs_locations = 0, []
        for job_obj in self.job_objects:
            jobs_locations.append(get_location_point(job_obj.center_location))
            points_count += job_obj.size
        pickups_locations = list(
            map(get_location_point, map(attrgetter('real_location'), self.unique_pickups_locations))
        )

        mini_cluster_average_size = (2*points_count)**(1/3)
        self.clusters_count = min(int(points_count / mini_cluster_average_size), 70)
        event_handler.dev_msg(
            f'[MiniClustersManager] Pickup+Delivery count: {points_count}; '
            f'Mini-Clusters count: {self.clusters_count}; '
            f'Mini-Clusters average size {int(points_count / self.clusters_count)}'
        )

        locations_array, pickup_locations_array = np.array(jobs_locations), np.array(pickups_locations)
        kmeans = KMeans(n_clusters=self.clusters_count, random_state=0)
        self.clusters_indexes = kmeans.fit_predict(locations_array)
        if len(pickup_locations_array):
            self.pickup_clusters_indexes = kmeans.predict(pickup_locations_array)
        self._recalc_clusters_list()

    def build_inner_dima_and_split(self):
        """
        Split clusters with different jobs settings into clusters with similar jobs settings.
        """
        self.do_split(SkillsSplit)
        self.do_split(TimeSplit)
        self.do_split(AssignedDriverSplit)
        for cluster in self.clusters:
            cluster.build_inner_dima()
            if self.inner_matrix is None:
                self.inner_matrix = copy.copy(cluster.inner_matrix)
            else:
                self.inner_matrix.update(cluster.inner_matrix)
        self.do_split(InnerDiMaBuilderSplit)
        self.do_split(DistanceSplit)

    def do_split(self, splitter: Type[SplitBase], **kwargs):
        """
        Split cluster if cluster's objects are not common by 'splitter'-class parameters.
        Update variables from new clusters.
        """
        splitting = splitter(self.clusters, self.job_objects, self.drivers, self.unique_pickups_locations, **kwargs)
        if splitting.fit():
            self.clusters_count = splitting.clusters_count
            event_handler.dev_msg(
                f'[MiniClustersManager] Mini-Clusters count({splitter.__name__}): {self.clusters_count}')
            self.clusters_indexes = splitting.cluster_indexes
            self.pickup_clusters_indexes = splitting.pickup_cluster_indexes
            self._recalc_clusters_list()
            self.skipped_job_objects = splitting.skipped_job_objects
            self.skipped_jobs = list(map(attrgetter('center_job'), self.skipped_job_objects))

    def build_outer_dima(self):
        """
        Build distance matrix between all locations of clusters and drivers.
        """
        from .utils import LocationPointMap
        center_jobs = list(map(attrgetter('center_job'), self.clusters))
        location_job_driver_map = LocationPointMap()
        for job in center_jobs:
            location_job_driver_map[job.deliver_address].append(job)
        for driver in self.drivers:
            if driver.start_hub is not None:
                location_job_driver_map[driver.start_hub.location].append(driver)
            elif driver.start_location is not None:
                location_job_driver_map[driver.start_location.location].append(driver)
            if driver.end_hub is not None:
                location_job_driver_map[driver.end_hub.location].append(driver)
            elif driver.end_location is not None:
                location_job_driver_map[driver.end_location.location].append(driver)
        locations = list(map(latlng_dict_from_str, location_job_driver_map.keys()))
        builder = DistanceMatrixBuilder(locations)
        builder.build_via_directions_api()
        self.outer_matrix = builder.matrix

        good_components = list(filter(lambda c: not c.base_graph.has_edges, builder.components))
        bad_components = list(filter(operator.attrgetter('base_graph.has_edges'), builder.components))
        if len(good_components) == 1 and len(bad_components) == 0:
            return
        if len(good_components) == 0:
            raise ROError('Can not build distance matrix.')

        bigger_component_objs, bigger_component, bigger_size = None, None, -1
        for component in good_components:
            component_locations = component.get_used_locations()
            objects_getter = map(lambda loc: location_job_driver_map[loc], component_locations)
            component_objs = reduce(operator.add, objects_getter, [])
            component_size = sum(cluster.size for cluster in self.clusters if cluster.center_job in component_objs)
            if bigger_size < component_size:
                bigger_component_objs, bigger_component, bigger_size = component_objs, component, component_size

        good_cluster_center_jobs = [obj for obj in bigger_component_objs if isinstance(obj, Job)]
        self.do_split(OuterDiMaBuilderSplit, good_cluster_center_jobs=good_cluster_center_jobs)

        skipped_components = [c for c in builder.components if c != bigger_component]
        skipped_drivers = set()
        for component in skipped_components:
            component_locations = component.get_used_locations()
            objects_getter = map(lambda loc: location_job_driver_map[loc], component_locations)
            component_objs = reduce(operator.add, objects_getter, [])
            skipped_drivers.update(obj for obj in component_objs if isinstance(obj, Driver))
        self.drivers = [d for d in self.drivers if d not in skipped_drivers]
        self.skipped_drivers = list(skipped_drivers)
        if self.skipped_drivers:
            event_handler.dev_msg(f'Skipped Drivers {self.skipped_drivers}. Left {len(self.drivers)} drivers')

    def collect_constraints(self) -> List[MergeConstraint]:
        """
        Collect constraints of what drivers could be assigned on what clusters.
        """
        statistic_clusters: Dict[Cluster, List[Driver]] = defaultdict(list)
        for cluster in self.clusters:
            for driver in self.drivers:
                if self._driver_good_for_cluster(cluster, driver):
                    statistic_clusters[cluster].append(driver)
        unique_groups: Dict[tuple, List[Cluster]] = defaultdict(list)
        for cl, dr in statistic_clusters.items():
            key = tuple(sorted(d.id for d in dr))
            unique_groups[key].append(cl)
        drivers_map = {d.id: d for d in self.drivers}
        return [MergeConstraint(clusters, [drivers_map[d] for d in drivers_ids])
                for drivers_ids, clusters in unique_groups.items()]

    def _driver_good_for_cluster(self, cluster: Cluster, driver):
        """
        Find out if the driver could be assigned on cluster.
        """
        cluster_skills = set(cluster.jobs[0].skill_set or [])
        driver_skills = set(driver.skill_set or [])
        if cluster_skills.difference(driver_skills):
            return False
        driver_start, driver_end = driver.start_time_sec, driver.end_time_sec
        cluster_start, cluster_end = cluster.jobs[0].deliver_after_sec, cluster.jobs[0].deliver_before_sec
        start, end = max(driver_start, cluster_start), min(driver_end, cluster_end)
        cluster_service_time = 0
        for job in cluster.jobs:
            cluster_service_time += (job.service_time or self.params.default_job_service_time) * 60
            for pickup in job.pickups:
                cluster_service_time += (pickup.service_time or self.params.default_pickup_service_time or 0) * 60
        if end - start - cluster_service_time < 0:
            return False
        job_driver_member_id = cluster.jobs[0].driver_member_id
        if job_driver_member_id is not None and job_driver_member_id != driver.member_id:
            return False
        return True
