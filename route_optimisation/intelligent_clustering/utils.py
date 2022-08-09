import math
import operator
from collections import defaultdict
from math import sqrt
from operator import itemgetter
from typing import Generic, List, Optional, Tuple, TypeVar

from route_optimisation.engine.base_classes.parameters import Driver, Job, Pickup
from route_optimisation.engine.ortools.distance_matrix import DistanceMatrixBuilder
from routing.utils import latlng_dict_from_str, location_to_point

TCluster = TypeVar('TCluster', bound='Cluster')
TJobObject = TypeVar('TJobObject', bound='JobObject')


class ClusterBaseObject:
    def __init__(self, index):
        self.index: int = index

    @property
    def capacity(self) -> int:
        raise NotImplementedError()

    @property
    def center_job(self) -> Job:
        raise NotImplementedError()

    @property
    def center_location(self) -> str:
        return self.center_job.deliver_address

    @property
    def jobs(self) -> List[Job]:
        raise NotImplementedError()

    @property
    def job_objects(self) -> List[TJobObject]:
        return []

    @property
    def pickups_count(self) -> int:
        raise NotImplementedError()

    @property
    def size(self) -> int:
        raise NotImplementedError()

    @property
    def clusters_objects(self) -> List[TCluster]:
        raise NotImplementedError()


class LocationPointMap(defaultdict):
    def __init__(self):
        super().__init__()
        self.default_factory = list

    @staticmethod
    def _transform_key(key) -> str:
        if isinstance(key, dict):
            return '{lat},{lng}'.format(**key)
        return key

    def __setitem__(self, key, value: List):
        return super().__setitem__(self._transform_key(key), value)

    def __getitem__(self, item) -> List:
        return super().__getitem__(self._transform_key(item))


class CenterObjectFinder:
    @staticmethod
    def find(objects: List[ClusterBaseObject]) -> ClusterBaseObject:
        if len(objects) < 3:
            return objects[0]

        jobs = [job for obj in objects for job in obj.jobs]
        jobs_locations: List[Tuple[float, float]] = []
        for job in jobs:
            location = list(map(float, map(str.strip, job.deliver_address.split(','))))
            location = {'lat':  location[0], 'lng': location[1]}
            jobs_locations.append(location_to_point(location))

        center_x, center_y = CenterObjectFinder._find_center_location(jobs_locations)
        return CenterObjectFinder._find_closest_object_to_center_location(
            objects, center_x, center_y
        )

    @staticmethod
    def _find_center_location(jobs_locations: List[Tuple[float, float]]) -> Tuple[float, float]:
        return sum(map(itemgetter(0), jobs_locations))/len(jobs_locations), \
               sum(map(itemgetter(1), jobs_locations))/len(jobs_locations)

    @staticmethod
    def _find_closest_object_to_center_location(objects: List[ClusterBaseObject], center_x: float, center_y: float) \
            -> ClusterBaseObject:
        min_idx, min_value = None, 1000000
        for idx, obj in enumerate(objects):
            location = list(map(float, map(str.strip, obj.center_location.split(','))))
            location = {'lat': location[0], 'lng': location[1]}
            loc = location_to_point(location)
            diff_to_center = sqrt((loc[0] - center_x) ** 2 + (loc[1] - center_y) ** 2)
            if diff_to_center < min_value:
                min_value = diff_to_center
                min_idx = idx
        return objects[min_idx]


class LocationPointer:
    """
    Main purpose of this class is to point on some specified location. Mainly using with pickup points.
    """

    def __init__(self, real_location: str):
        self.pointer_object: Optional[ClusterBaseObject] = None
        self.real_location = real_location

    @property
    def pointed_location(self) -> str:
        return self.pointer_object.center_location


class PickupJobObject:
    """
    Corresponds to some pickup point. Pickup are not storing in Clusters.
    They are storing in JobObjects. And JobObjects are storing in Clusters.
    But we need to know with what location we should work with pickups.
    So PickupJobObject is pointing to LocationPointer. And Clusters have LocationPointer.
    So with this chain of pointing we know approximate location of pickup point.
    """

    def __init__(self, pickup: Pickup):
        self.pickup_address = pickup.pickup_address
        self.location_pointer: Optional[LocationPointer] = None

    def bound_location_pointer(self, location_pointer: LocationPointer):
        self.location_pointer = location_pointer


class JobObject(ClusterBaseObject):
    def __init__(self, index, job: Job):
        super().__init__(index)
        self._job: Job = job
        self._pickups: List[PickupJobObject] = list(map(PickupJobObject, self._job.pickups))

    @property
    def capacity(self) -> int:
        return math.ceil((self._job.capacity if self.pickups_count == 0 else self._job.capacity/2))
        # return self._job.capacity

    @property
    def center_job(self) -> Job:
        return self._job

    @property
    def jobs(self) -> List[Job]:
        return [self._job]

    @property
    def job_objects(self) -> List[TJobObject]:
        return [self]

    @property
    def pickups(self) -> List[PickupJobObject]:
        return self._pickups

    @property
    def pickups_count(self) -> int:
        return len(self._job.pickups)

    @property
    def size(self) -> int:
        return 1 + self.pickups_count

    @property
    def skill_set(self):
        return self._job.skill_set

    @property
    def deliver_after_sec(self):
        return self._job.deliver_after_sec

    @property
    def deliver_before_sec(self):
        return self._job.deliver_before_sec

    @property
    def driver_member_id(self):
        return self._job.driver_member_id

    @property
    def clusters_objects(self) -> List[TCluster]:
        raise ValueError('Job Object does not have Cluster objects')


T = TypeVar('T', JobObject, TCluster)


class Cluster(Generic[T], ClusterBaseObject):
    def __init__(self, index, objects: List[T], drivers: Optional[List[Driver]] = None,
                 pickup_location_pointers: Optional[List[LocationPointer]] = None):
        super().__init__(index)
        self._objects: List[T] = objects
        self._center_location_object: ClusterBaseObject = CenterObjectFinder.find(self._objects)

        self.location_point_map = LocationPointMap()
        for obj in self._objects:
            self.location_point_map[obj.center_location].append(obj)
        self.locations: List[str] = list(map(latlng_dict_from_str, self.location_point_map.keys()))

        self.inner_matrix = None
        self.builder: Optional[DistanceMatrixBuilder] = None

        self.drivers: List[Driver] = drivers or []

        self.pickup_location_pointers: List[LocationPointer] = pickup_location_pointers or []
        for location_pointer in self.pickup_location_pointers:
            location_pointer.pointer_object = self

    @property
    def capacity(self) -> int:
        return math.ceil(sum(
            (job.capacity if len(job.pickups) == 0 else job.capacity/2)
            for job in self.jobs
        ))
        # return sum(map(operator.attrgetter('capacity'), self._objects))

    @property
    def center_job(self) -> Job:
        return self._center_location_object.center_job

    @property
    def jobs(self) -> List[Job]:
        return [job for obj in self._objects for job in obj.jobs]

    @property
    def pickups_count(self) -> int:
        return sum(map(operator.attrgetter('pickups_count'), self._objects))

    @property
    def size(self) -> int:
        return sum(map(operator.attrgetter('size'), self._objects))

    @property
    def objects(self) -> List[T]:
        return self._objects

    @property
    def job_objects(self) -> List[JobObject]:
        result = []
        for obj in self._objects:
            result.extend(obj.job_objects)
        return result

    @property
    def clusters_objects(self) -> List[TCluster]:
        result = []
        for obj in self._objects:
            if isinstance(obj, Cluster):
                result.append(obj)
        return result or [self]

    def build_inner_dima(self):
        self.builder = DistanceMatrixBuilder(self.locations)
        self.builder.build_via_directions_api()
        self.inner_matrix = self.builder.matrix

    def log(self):
        return f'[Cluster index {self.index}, {len(self._objects)} objects, cluster_size {self.size}, ' \
               f'drivers_count {len(self.drivers or [])}]'

    def complete_log(self):
        return f'{self.log()} Jobs: {self.jobs}'


MiniCluster = Cluster[JobObject]
BigCluster = Cluster[MiniCluster]


class MergeConstraint:
    """
    Constraint have the list of drivers that could be assigned on specified list of clusters.
    Specified drivers could be assigned on these clusters.
    """

    def __init__(self, clusters: List[Cluster], drivers: List[Driver]):
        self.clusters = clusters
        self.drivers = drivers


def get_location_point(loc: str) -> Tuple[float, float]:
    locations = list(map(float, map(str.strip, loc.split(','))))
    locations = {'lat': locations[0], 'lng': locations[1]}
    return location_to_point(locations)
