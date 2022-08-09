import operator
from collections import defaultdict
from functools import reduce
from typing import List

from route_optimisation.engine.base_classes.parameters import Driver, Job
from route_optimisation.engine.events import event_handler
from route_optimisation.intelligent_clustering.utils import Cluster, JobObject, LocationPointer, get_location_point
from routing.utils import get_geo_distance


class SplitBase:
    def __init__(self, clusters: List[Cluster], job_objects: List[JobObject],
                 drivers, pickup_locations: List[LocationPointer], **kwargs):
        self.clusters: List[Cluster] = clusters
        self.job_objects: List[JobObject] = job_objects
        self.skipped_job_objects: List[JobObject] = []
        self.drivers: List[Driver] = drivers
        self.clusters_jobs: List[List[JobObject]] = []
        self.clusters_pickups: List[List[LocationPointer]] = []
        self.pickup_locations = pickup_locations

    def fit(self):
        """
        Split and skip clusters. Reassigns pickups locations if needed. Look for skipped jobs.
        :return: True if some cluster was changed. False in case nothing changed.
        """
        has_changed = False
        skipped_job_objects = set(self.job_objects)
        pickups_to_another_cluster: List[Cluster] = []
        for cluster in self.clusters:
            jobs_objects_split = self._split(cluster)

            # cluster is skipping
            if len(jobs_objects_split) == 0:
                has_changed = True
                if len(cluster.pickup_location_pointers) > 0:
                    pickups_to_another_cluster.append(cluster)
                continue

            for jobs_objects in jobs_objects_split:
                skipped_job_objects.difference_update(set(jobs_objects))
            self.clusters_jobs.extend(jobs_objects_split)

            if len(jobs_objects_split) == 1:
                # cluster is not skipping, but jobs count might be changed
                if len(cluster.job_objects) != len(jobs_objects_split[0]):
                    has_changed = True
                self.clusters_pickups.append(cluster.pickup_location_pointers)
                continue

            # len(jobs_objects_split) > 1
            has_changed = True
            self.clusters_pickups.extend(self._split_pickups(cluster, jobs_objects_split))

        self.skipped_job_objects = list(skipped_job_objects)
        # Process pickup locations from skipped clusters
        for cluster in pickups_to_another_cluster:
            new_clusters_pickups = self._split_pickups(cluster, self.clusters_jobs)
            for cluster_pickup, new_pickups in zip(self.clusters_pickups, new_clusters_pickups):
                cluster_pickup.extend(new_pickups)

        return has_changed

    def _split(self, cluster: Cluster) -> List[List[JobObject]]:
        """
        Try to split jobs for passed cluster. Allow to skip whole cluster.
        :return: List of divided jobs. In case nothing to divide returns full list of jobs objects.
        In case all jobs should be skipped - returns empty list.
        """
        raise NotImplementedError()

    @staticmethod
    def _split_pickups(cluster: Cluster, jobs_split: List[List[JobObject]]) -> List[List[LocationPointer]]:
        """
        In case cluster was split, we should also split pickups-location-pointers of current cluster.
        For each pickup-pointer find the nearest jobs cluster.
        :param cluster: Current cluster object.
        :param jobs_split: Splitting of current cluster's jobs.
        """
        result: List[List[LocationPointer]] = [[] for _ in jobs_split]
        for pickup_location_pointer in cluster.pickup_location_pointers:
            closest_index, closest_average = None, 0
            pickup_location_point = get_location_point(pickup_location_pointer.real_location)
            for index, job_objects in enumerate(jobs_split):
                square_sum = 0
                for job_obj in job_objects:
                    job_location_point = get_location_point(job_obj.center_location)
                    square_sum += (pickup_location_point[0] - job_location_point[0])**2 \
                        + (pickup_location_point[1] - job_location_point[1])**2
                average = square_sum/len(job_objects)
                if closest_index is None or average < closest_average:
                    closest_index = index
                    closest_average = average
            result[closest_index].append(pickup_location_pointer)
        return result

    @property
    def clusters_count(self):
        return len(self.clusters_jobs)

    @property
    def cluster_indexes(self):
        cluster_indexes = [-1] * len(self.job_objects)
        for i, jobs in enumerate(self.clusters_jobs):
            for job in jobs:
                cluster_indexes[job.index] = i
        return cluster_indexes

    @property
    def pickup_cluster_indexes(self):
        pickup_cluster_indexes = [-1] * len(self.pickup_locations)
        for i, pickups in enumerate(self.clusters_pickups):
            for pickup in pickups:
                pickup_cluster_indexes[self.pickup_locations.index(pickup)] = i
        return pickup_cluster_indexes


class SkillsSplit(SplitBase):
    """
    Split jobs by skillset. So each mini-cluster should have jobs with similar skillset.
    """

    def _split(self, cluster: Cluster) -> List[List[JobObject]]:
        unique_skills = defaultdict(list)
        for job in cluster.job_objects:
            skill_hash = ','.join(map(str, sorted(job.skill_set)))
            unique_skills[skill_hash].append(job)
        return list(unique_skills.values())


class TimeSplit(SplitBase):
    """
    Split jobs by delivery time window. So each mini-cluster should have jobs with similar delivery window.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.min_driver_start = min(driver.start_time_sec for driver in self.drivers)
        self.max_driver_end = max(driver.end_time_sec for driver in self.drivers)

    def _split(self, cluster: Cluster) -> List[List[JobObject]]:
        unique_times = defaultdict(list)
        for job in cluster.job_objects:
            job_start = max(job.deliver_after_sec, self.min_driver_start)
            job_end = min(job.deliver_before_sec, self.max_driver_end)
            time_hash = ','.join(map(str, (job_start, job_end)))
            unique_times[time_hash].append(job)
        return list(unique_times.values())


class AssignedDriverSplit(SplitBase):
    """
    Split jobs by assigned driver. So each mini-cluster should have jobs with same driver if the driver is specified.
    """

    def _split(self, cluster: Cluster) -> List[List[JobObject]]:
        unique_drivers = defaultdict(list)
        for job in cluster.job_objects:
            unique_drivers[job.driver_member_id].append(job)
        return list(unique_drivers.values())


class InnerDiMaBuilderSplit(SplitBase):
    """
    Split jobs by information from DistanceMatrixBuilder and maps api. In case some jobs are not available.
    """

    def _split(self, cluster: Cluster) -> List[List[JobObject]]:
        good_components = list(filter(lambda c: not c.base_graph.has_edges, cluster.builder.components))
        bad_components = list(filter(operator.attrgetter('base_graph.has_edges'), cluster.builder.components))
        if len(good_components) == 1 and len(bad_components) == 0:
            return [cluster.job_objects]
        if len(good_components) == 0:
            locations = list(map(lambda c: c.get_used_locations(), cluster.builder.components))
            event_handler.dev_msg(
                f'[{self.__class__.__name__}] cluster have no built distance matrix. So will be skipped. '
                f'Locations: {locations}. Cluster: {cluster.complete_log()}.'
            )
            return []

        locations_by_components = list(map(lambda c: c.get_used_locations(), good_components))
        job_objects_by_components = []
        for locations in locations_by_components:
            job_objects_getter = map(lambda loc: cluster.location_point_map[loc], locations)
            job_objects_by_components.append(reduce(operator.add, job_objects_getter, []))
        event_handler.dev_msg(
            f'[{self.__class__.__name__}] cluster will be split into {len(good_components)} clusters. '
            f'Locations: {locations_by_components}. Cluster: {cluster.complete_log()}.'
        )
        return job_objects_by_components


class OuterDiMaBuilderSplit(SplitBase):
    """
    Skip clusters by information from DistanceMatrixBuilder and maps api. In case some clusters are not available.
    """

    def __init__(self, clusters: List[Cluster], job_objects: List[JobObject], drivers,
                 pickup_locations: List[LocationPointer], good_cluster_center_jobs: List[Job], **kwargs):
        super().__init__(clusters, job_objects, drivers, pickup_locations, **kwargs)
        self.good_clusters = [cluster for cluster in self.clusters if cluster.center_job in good_cluster_center_jobs]
        self.bad_clusters = [cl for cl in self.clusters if cl not in self.good_clusters]

    def _split(self, cluster: Cluster) -> List[List[JobObject]]:
        if cluster in self.good_clusters:
            return [cluster.job_objects]
        event_handler.dev_msg(
            f'[{self.__class__.__name__}] cluster is not connected with other clusters while building outer matrix. '
            f'So will be skipped. Center location: {cluster.center_location}. Cluster: {cluster.complete_log()}.'
        )
        return []


class DistanceSplit(SplitBase):
    """
    Split jobs by distance between them. So each mini-cluster should have jobs with similar location.
    """

    def _split(self, cluster: Cluster) -> List[List[JobObject]]:
        unique_clusters = [[0]]
        for i in range(1, len(cluster.locations)):
            missed = True
            for unique in unique_clusters:
                if self.is_good_for_temp_cluster(cluster, unique, i):
                    unique.append(i)
                    missed = False
                    break
            if missed:
                unique_clusters.append([i])
        result = []
        for unique in unique_clusters:
            jobs = []
            for unique_location_index in unique:
                location = cluster.locations[unique_location_index]
                location_jobs = cluster.location_point_map[location]
                jobs.extend(location_jobs)
            result.append(jobs)
        return result

    @staticmethod
    def is_good_for_temp_cluster(cluster: Cluster, unique, point):
        for index in unique:
            start, end = cluster.locations[point], cluster.locations[index]
            is_close = DistanceSplit.is_real_distance_close_to_direct(cluster, start, end)
            if not is_close:
                return False
        return True

    @staticmethod
    def is_real_distance_close_to_direct(cluster: Cluster, from_location, to_location):
        direct_distance = get_geo_distance(
            *map(float, (from_location['lng'], from_location['lat'], to_location['lng'], to_location['lat']))
        )
        real_distance = cluster.inner_matrix[(from_location, to_location)]['distance']
        ratio = round(real_distance/direct_distance, 2)
        if direct_distance < 500 and ratio >= 30:
            return False
        elif 500 <= direct_distance < 2000 and ratio >= 20:
            return False
        elif direct_distance >= 2000 and ratio >= 10:
            return False
        return True
