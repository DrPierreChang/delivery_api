from typing import Dict, List

from route_optimisation.engine.base_classes.parameters import Driver, EngineParameters, Job
from route_optimisation.engine.events import event_handler
from routing.utils import latlng_dict_from_str

from .mini_clusters import Cluster, MiniClustersManager
from .utils import BigCluster, ClusterBaseObject, LocationPointer, MiniCluster


class BigClustersManager:
    min_max_cluster_size_diff = 1.25

    def __init__(self, jobs: List[Job], drivers: List[Driver],
                 mini_manager: MiniClustersManager, params: EngineParameters):
        self.drivers: List[Driver] = drivers
        self.skipped_drivers: List[Driver] = mini_manager.skipped_drivers
        self.matter_drivers = [d for d in self.drivers if d not in self.skipped_drivers]
        self.jobs: List[Job] = jobs
        self.skipped_jobs: List[Job] = mini_manager.skipped_jobs
        self.matter_jobs = [j for j in self.jobs if j not in self.skipped_jobs]
        self.matrix = mini_manager.outer_matrix
        self.mini_manager = mini_manager
        self.params: EngineParameters = params

        self.clusters_count = None
        self.max_cluster_size = None
        self.min_cluster_size = None
        self._calc_clusters_meta()
        self.mini_clusters: List[MiniCluster] = list(mini_manager.clusters)
        self.clusters_indexes = None
        self.drivers_clusters_indexes = None
        self.set_clusters([Cluster(index, [cluster]) for index, cluster in enumerate(self.mini_clusters)], debug=False)

    def set_clusters(self, clusters: List[BigCluster], debug=True):
        if debug:
            event_handler.dev_msg('\n'.join(cl.log() for cl in clusters))
        self.clusters_indexes, self.drivers_clusters_indexes = self.recalc_cluster_indexes_for_big_clusters(clusters)

    def time_with_service_for_cluster(self, cluster_center: ClusterBaseObject, obj: ClusterBaseObject,
                                      scale_transit_time=1):
        value = 0
        for job in obj.jobs:
            value += (job.service_time or self.params.default_job_service_time) * 60
            for pickup in job.pickups:
                value += (pickup.service_time or self.params.default_pickup_service_time or 0) * 60
        matrix_elem = (
            latlng_dict_from_str(cluster_center.center_location),
            latlng_dict_from_str(obj.center_location)
        )
        value += int(self.matrix[matrix_elem]['duration']*scale_transit_time)

        if isinstance(obj, Cluster) and len(obj.objects) > 2:
            sum_duration_inside_obj = 0
            for inside_object in obj.objects:
                matrix_elem = (
                    latlng_dict_from_str(obj.center_location),
                    latlng_dict_from_str(inside_object.center_location),
                )
                sum_duration_inside_obj += obj.inner_matrix[matrix_elem]['duration']
            avg_duration_inside_obj = sum_duration_inside_obj / len(obj.objects)
            final_duration_inside_obj = min(len(obj.objects)-2, 3) * avg_duration_inside_obj
            value += int(final_duration_inside_obj * scale_transit_time)

        return value

    def time_for_cluster_to_location_pointer(self, cluster_center: ClusterBaseObject,
                                             location_pointer: LocationPointer, scale_transit_time=1) -> int:
        """
        Time duration that needs to drive from cluster center to some location.

        :param cluster_center: Cluster
        :param location_pointer: LocationPointer
        :param scale_transit_time: In case we need to increase or decrease return value for some reasons.
        :return: Seconds
        """
        matrix_elem = (
            latlng_dict_from_str(cluster_center.center_location),
            latlng_dict_from_str(location_pointer.pointed_location)
        )
        return int(self.matrix[matrix_elem]['duration'] * scale_transit_time)

    def time_between_cluster_and_driver(self, cluster: ClusterBaseObject, driver: Driver) -> int:
        """
        Time duration that driver needs to drive from start point to cluster center and return to end point.
        :return: Seconds
        """
        start_location, end_location = None, None
        if driver.start_hub is not None:
            start_location = driver.start_hub.location
        elif driver.start_location is not None:
            start_location = driver.start_location.location
        if driver.end_hub is not None:
            end_location = driver.end_hub.location
        elif driver.end_location is not None:
            end_location = driver.end_location.location
        result = 0
        if start_location:
            result += self.matrix[
                (latlng_dict_from_str(start_location), latlng_dict_from_str(cluster.center_location))
            ]['duration']
        if end_location:
            result += self.matrix[
                (latlng_dict_from_str(cluster.center_location), latlng_dict_from_str(end_location))
            ]['duration']
        return result

    def distance_between_clusters(self, cluster_a: ClusterBaseObject, cluster_b: ClusterBaseObject) -> float:
        """
        Average distance between sub clusters.
        :return: Meters
        """
        dists = []
        for cl_a in cluster_a.clusters_objects:
            for cl_b in cluster_b.clusters_objects:
                matrix_elem = (
                    latlng_dict_from_str(cl_a.center_location),
                    latlng_dict_from_str(cl_b.center_location)
                )
                dists.append(self.matrix[matrix_elem]['distance'])
        return sum(dists)/len(dists)

    def recalc_cluster_indexes_for_big_clusters(self, big_clusters):
        clusters_indexes = [-1] * len(self.jobs)
        drivers_clusters_indexes = [-1] * len(self.drivers)
        drivers_indexes: Dict[Driver, int] = {driver: i for i, driver in enumerate(self.drivers)}
        for cluster in big_clusters:
            for job_object in cluster.job_objects:
                clusters_indexes[job_object.index] = cluster.index
            for driver in (cluster.drivers or []):
                drivers_clusters_indexes[drivers_indexes[driver]] = cluster.index
        return clusters_indexes, drivers_clusters_indexes

    def _calc_clusters_meta(self):
        points_count = BigClustersManager._calc_points_count(self.matter_jobs)
        self.clusters_count = self.calc_clusters_count(self.matter_jobs, self.matter_drivers)
        self.min_cluster_size = int(points_count/self.clusters_count/self.min_max_cluster_size_diff)
        self.max_cluster_size = int(points_count/self.clusters_count*self.min_max_cluster_size_diff)
        event_handler.dev_msg(
            f'[BigClustersManager] Pickup+Delivery count: {points_count}; '
            f'Big Clusters count: {self.clusters_count}; '
            f'min_size: {self.min_cluster_size}, max_size: {self.max_cluster_size}; '
            f'matter jobs count {len(self.matter_jobs)} out of {len(self.jobs)}; '
            f'matter drivers count {len(self.matter_drivers)} out of {len(self.drivers)}'
        )

    @staticmethod
    def calc_clusters_count(jobs: List[Job], drivers: List[Driver]):
        points_count = BigClustersManager._calc_points_count(jobs)
        if points_count <= 250:
            clusters_count = 1
        else:
            clusters_count = 2
            while int(points_count/clusters_count) >= 195:
                clusters_count += 1
            while int(points_count/(clusters_count+1)) >= 160:
                clusters_count += 1
        return min(clusters_count, len(drivers))

    @staticmethod
    def _calc_points_count(jobs: List[Job]):
        return sum((1 + len(job.pickups)) for job in jobs)
