import math
import random
from collections import defaultdict
from operator import attrgetter, itemgetter
from typing import Dict, List, Optional, Tuple, Type, TypeVar, Union

from ortools.sat.python import cp_model

from route_optimisation.engine.base_classes.parameters import Driver, Job

from ..engine.events import event_handler
from .big_clusters import BigClustersManager
from .mini_clusters import Cluster, MergeConstraint
from .utils import BigCluster, ClusterBaseObject, JobObject, LocationPointer, MiniCluster


class BackendResult:
    def __init__(self, initial_big_clusters_centers, clusters, score, time_coefficient):
        self.initial_big_clusters_centers: List[MiniCluster] = initial_big_clusters_centers
        self.clusters: List[BigCluster] = clusters
        self.score: float = score
        self.time_coefficient: float = time_coefficient


TPlugin = TypeVar('TPlugin', bound='BackendPlugin')


class DataStore:
    """
    Store all the data useful for merge mini clusters into big clusters.
    """

    def __init__(self, big_clusters: BigClustersManager, centers: List[MiniCluster],
                 objects: List[MiniCluster], drivers: List[Driver], constraints: List[MergeConstraint]):
        self.big_clusters: BigClustersManager = big_clusters
        self.clusters_centers: List[MiniCluster] = centers
        self.objects: List[ClusterBaseObject] = []
        self.pickups: List[LocationPointer] = []
        self.pickups_objects_map: Dict[Tuple[int, int], int] = {}
        self.drivers: List[Driver] = drivers
        self.constraints: List[MergeConstraint] = constraints

        self.driver_time_to_center = []  # Time that driver needs to driver to each big cluster center and back.
        self.object_time_to_center = []  # Time to drive from center of each big cluster to each object.
        self.pickup_time_to_center = []  # Time to drive from center of each big cluster to each pickup location.
        for cluster_center in self.clusters_centers:
            driver_times = [
                int(self.big_clusters.time_between_cluster_and_driver(cluster_center, driver))
                for driver in self.drivers
            ]
            self.driver_time_to_center.append(driver_times)
        self.num_clusters = len(self.clusters_centers)
        self.num_objects: int = 0
        self.num_pickups: int = 0
        self.num_drivers = len(self.drivers)
        self.object_sizes: List[int] = []
        self.cluster_size_max = self.big_clusters.max_cluster_size
        self.cluster_size_min = self.big_clusters.min_cluster_size
        self.pin_object_to_cluster: Dict[int, int] = {}

        self.init_objects(objects)
        self.init_pickups()

    def init_objects(self, objects: List[MiniCluster]):
        raise NotImplementedError()

    def find_object_indexes(self, cluster: MiniCluster) -> List[int]:
        raise NotImplementedError()

    @property
    def capacity_penalty_scale(self):
        raise NotImplementedError()

    def init_pickups(self):
        pickup_locations_map: Dict[LocationPointer, List[int]] = defaultdict(list)
        for obj_index, obj in enumerate(self.objects):
            for job_obj in obj.job_objects:
                for pickup_obj in job_obj.pickups:
                    pickup_locations_map[pickup_obj.location_pointer].append(obj_index)
        self.pickups = list(pickup_locations_map.keys())
        self.num_pickups = len(self.pickups)
        for pickup_index, pickup in enumerate(self.pickups):
            for obj_index in range(self.num_objects):
                self.pickups_objects_map[obj_index, pickup_index] = int(obj_index in pickup_locations_map[pickup])

        for cluster_center in self.clusters_centers:
            pickup_times = [
                int(self.big_clusters.time_for_cluster_to_location_pointer(cluster_center, pickup))
                for pickup in self.pickups
            ]
            self.pickup_time_to_center.append(pickup_times)


class ClustersDataStore(DataStore):
    """
    Store all the data useful for merge mini clusters into big clusters.
    Objects of this data store are MiniClusters
    """

    def init_objects(self, objects):
        self.objects: List[MiniCluster] = objects
        self.num_objects = len(self.objects)
        event_handler.dev_msg(f'[{self.__class__.__name__}] objects count {self.num_objects}')

        for cluster_center in self.clusters_centers:
            object_times = [
                int(self.big_clusters.time_with_service_for_cluster(cluster_center, obj))
                for obj in self.objects
            ]
            self.object_time_to_center.append(object_times)
        self.object_sizes = [cluster.size for cluster in self.objects]

    def find_object_indexes(self, cluster: MiniCluster) -> List[int]:
        return [self.objects.index(cluster)]

    @property
    def capacity_penalty_scale(self):
        """
        For current DataStore capacity penalty should not have a big effect.
        """
        return 1 / sum(d.capacity for d in self.drivers)


class VirtualJobObject(JobObject):
    """
    Like Job object, but it has another center job and center location.
    """

    def __init__(self, job_obj: JobObject, cluster: MiniCluster):
        super().__init__(job_obj.index, job_obj.center_job)
        self.initial_job_object: JobObject = job_obj
        self._virtual_center_cluster: MiniCluster = cluster

    @property
    def center_job(self) -> Job:
        return self._virtual_center_cluster.center_job

    @property
    def clusters_objects(self) -> List[Cluster]:
        return [self._virtual_center_cluster]


class MiniClustersDivide:
    __slots__ = ('cluster', 'distance_diff')

    def __init__(self, distance_to_closer_big_cluster, distance_to_self_big_cluster, cluster: MiniCluster):
        self.cluster = cluster
        self.distance_diff = distance_to_closer_big_cluster - distance_to_self_big_cluster


class MixClustersAndJobObjectsDataStore(DataStore):
    """
    Store all the data useful for merge mini clusters into big clusters.
    Objects of this data store are mix of MiniClusters and JobObjects.
    """

    def __init__(self, *args, related_results: BackendResult, **kwargs):
        self.related_results = related_results
        super().__init__(*args, **kwargs)

    def init_objects(self, objects):
        clusters_to_divide = self.get_clusters_to_divide(self.related_results, self.clusters_centers)
        self.objects: List[Union[VirtualJobObject, Cluster]] = []
        used_clusters = set()
        for cluster in clusters_to_divide:
            self.objects.extend([
                VirtualJobObject(job_obj, cluster) for job_obj in cluster.job_objects
            ])
            used_clusters.add(cluster.index)
        for mini_cluster in objects:
            if mini_cluster.index in used_clusters:
                continue
            self.objects.append(mini_cluster)
            big_cluster_number = list(
                filter(lambda x: mini_cluster in x.objects, self.related_results.clusters)
            )[0].index
            self.pin_object_to_cluster[len(self.objects)-1] = big_cluster_number
        self.num_objects = len(self.objects)
        event_handler.dev_msg(f'[{self.__class__.__name__}] objects count {self.num_objects}')

        for cluster_center in self.clusters_centers:
            object_times = [
                int(self.big_clusters.time_with_service_for_cluster(
                    cluster_center, obj, scale_transit_time=self._get_scale_transit_time(obj)
                ))
                for obj in self.objects
            ]
            self.object_time_to_center.append(object_times)
        self.object_sizes = [cluster.size for cluster in self.objects]

    def get_clusters_to_divide(self, related_results: BackendResult, centers: List[MiniCluster]) -> List[MiniCluster]:
        """
        Find mini clusters that have to be broken. These mini clusters will be taken from some of big clusters
        :param related_results: Last results of merge.
        :param centers: Current centers of big clusters.
        :return: Mini clusters that have to be broken.
        """
        clusters_to_take = []  # big clusters that could take new jobs
        clusters_to_give = []  # big clusters that have to give up jobs
        for big_cluster, big_center in zip(related_results.clusters, centers):
            jobs_capacities = sum(job_obj.capacity for job_obj in big_cluster.job_objects)
            drivers_capacities = sum(driver.capacity for driver in big_cluster.drivers)
            diff = jobs_capacities - drivers_capacities
            if diff > 0:  # too many orders, not enough drivers capacity
                clusters_to_give.append((big_cluster, big_center))
            elif diff < 0:  # not so many orders, enough drivers capacity
                clusters_to_take.append((big_cluster, big_center))

        mini_clusters_to_divide_info: List[MiniClustersDivide] = []
        for big_cluster_to_give, big_center_to_give in clusters_to_give:
            for mini_cluster in big_cluster_to_give.objects:
                distance_to_self = self.big_clusters.distance_between_clusters(mini_cluster, big_center_to_give)
                # For each mini-cluster find the closest big cluster that could take current mini-cluster.
                distance_to_closer = min([
                    self.big_clusters.distance_between_clusters(mini_cluster, big_center_to_take)
                    for big_cluster_to_take, big_center_to_take in clusters_to_take
                ])
                mini_clusters_to_divide_info.append(
                    MiniClustersDivide(distance_to_closer, distance_to_self, mini_cluster)
                )
        # Sort mini-clusters by closeness to another big cluster compared to self big cluster.
        mini_clusters_to_divide_info.sort(key=attrgetter('distance_diff'))
        # Take 15% of available-to-take mini-clusters.
        count = math.ceil(len(mini_clusters_to_divide_info)*0.15)
        return list(map(attrgetter('cluster'), mini_clusters_to_divide_info[:count]))

    @staticmethod
    def _get_scale_transit_time(obj: Union[VirtualJobObject, Cluster]):
        if isinstance(obj, VirtualJobObject):
            return 1/len(obj.clusters_objects[0].objects)
        return 1

    def _find_job_object_index(self, job_obj: JobObject) -> int:
        for i, obj in enumerate(self.objects):
            if obj.initial_job_object == job_obj:
                return i
        raise ValueError(f'{job_obj} not found')

    def find_object_indexes(self, cluster: MiniCluster) -> List[int]:
        if cluster in self.objects:
            return [self.objects.index(cluster)]
        return [self._find_job_object_index(job_obj) for job_obj in cluster.job_objects]

    @property
    def capacity_penalty_scale(self):
        """
        For current DataStore capacity penalty should have an effect.
        """
        return 1


class Coefficient:
    rounding = 2
    min_allowed_changing = 0.019

    def __init__(self, start_coefficient=None):
        self.coefficient_strategy = self.get_coefficient_linear \
            if start_coefficient is not None else self.get_coefficient_binary
        self.coefficients = [start_coefficient or 1.0]
        self.next_is_up = None

    def __call__(self, *args, **kwargs):
        for _ in range(30):
            if self.coefficients[0] < 0.01:
                break
            if len(self.coefficients) > 1 and self.coefficients[0] in self.coefficients[1:]:
                break

            yield self.coefficients[0]

            if self.next_is_up is None:
                break
            c = round(self.coefficient_strategy(self.next_is_up, *self.coefficients), self.rounding)
            if abs(self.coefficients[0] - c) < self.min_allowed_changing:
                break
            self.coefficients.insert(0, c)
            self.next_is_up = None

    def up_coefficient(self):
        self.next_is_up = True

    def down_coefficient(self):
        self.next_is_up = False

    @staticmethod
    def get_coefficient_binary(up, c1, c2=None, *args) -> float:
        all_c = list(filter(None, [c1, c2, *args]))
        only_rising = all(map(lambda x: x[0] > x[1], zip(all_c[:-1], all_c[1:])))
        if (up and only_rising) or c2 is None:
            result = c1 * 2 if up else c1 / 2
        else:
            others = list(filter(None, [c2, *args]))
            c2_boundary = Coefficient.get_next_coefficient_boundary(up, c1, others)
            _c2 = c2_boundary or c2
            diff = abs(c1 - _c2) / 2
            result = c1 + diff if up else c1 - diff
        return result

    @staticmethod
    def get_coefficient_linear(up, c1, *args) -> float:
        c2_boundary = Coefficient.get_next_coefficient_boundary(up, c1, args)
        if c2_boundary is not None:
            # In case we have c2 boundary, then we should find coefficient with binary search
            diff = abs(c1 - c2_boundary) / 2
            result = c1 + diff if up else c1 - diff
        else:
            # In case we do not have c2 boundary, then we should find coefficient with linear search
            result = c1 + 0.05 if up else c1 - 0.05
        return result

    @staticmethod
    def get_next_coefficient_boundary(up, c1, others):
        if up:
            greater = list(filter(lambda x: x > c1, others))
            return greater[0] if greater else None
        lesser = list(filter(lambda x: x < c1, others))
        return lesser[0] if lesser else None


class MergeBackend:
    setup_plugins: List[Type[TPlugin]] = []
    objectives: List[Type[TPlugin]] = []
    data_store = None
    min_computation_seconds = None

    def __init__(self, big_clusters: BigClustersManager, centers: List[MiniCluster],
                 objects: List[MiniCluster], drivers: List[Driver], constraints: List[MergeConstraint], **kwargs):
        self.initial_big_clusters_centers = list(centers)
        self.data: DataStore = self.data_store(big_clusters, centers, objects, drivers, constraints, **kwargs)
        self.model = None
        self.object_variables = {}
        self.driver_variables = {}
        self.pickup_variables = {}

    def max_computation_seconds(self, fast=True):
        seconds = self.min_computation_seconds * len(self.initial_big_clusters_centers)
        return seconds if fast else seconds * 4

    def merge(self, start_coefficient=None, final_improving=False) -> BackendResult:
        results_cache, last_result = {}, None
        coefficient_finder = Coefficient(start_coefficient)
        coefficient_generator = coefficient_finder()
        for coefficient in coefficient_generator:
            if coefficient in results_cache:
                result = results_cache[coefficient]
            else:
                result = self._merge(coefficient)
                results_cache[coefficient] = result
            if result is not None:
                last_result = result, coefficient
                coefficient_finder.up_coefficient()
                continue
            coefficient_finder.down_coefficient()

        if final_improving:
            coefficient = last_result[1]
            result = self._merge(coefficient, fast=False), coefficient
            if last_result[0][1] > result[0][1]:
                last_result = result
        return BackendResult(self.initial_big_clusters_centers, last_result[0][0], last_result[0][1], last_result[1])

    def _merge(self, coefficient: float, fast=True) -> Optional[Tuple[List[Cluster[Cluster]], float]]:
        self._init_variables()
        for plugin_class in self.setup_plugins:
            plugin = plugin_class(self)
            plugin.setup(coefficient=coefficient)
        self._define_objective()

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.max_computation_seconds(fast)
        solver.parameters.num_search_workers = 2 if fast else 3
        # status = solver.Solve(self.model, cp_model.ObjectiveSolutionPrinter())
        status = solver.Solve(self.model)
        msgs = [
            f'[_merge] with coefficient {coefficient}. Start cp solver. '
            f'max_computation_seconds {solver.parameters.max_time_in_seconds}',
            f'End cp solver with status {status}'
        ]
        for_return = None
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            result, cost, _msgs = ResultParser(self).setup(solver)
            msgs.extend(_msgs)
            for_return = result, cost
        else:
            msgs.append('No solution found.')
        event_handler.dev_msg('\n'.join(msgs))
        return for_return

    def _init_variables(self):
        self.model = cp_model.CpModel()
        self.object_variables = {}
        self.driver_variables = {}
        self.pickup_variables = {}
        for cluster in range(self.data.num_clusters):
            for obj in range(self.data.num_objects):
                if obj in self.data.pin_object_to_cluster:
                    variable = self.model.NewConstant(int(self.data.pin_object_to_cluster[obj] == cluster))
                else:
                    variable = self.model.NewBoolVar(f'object_var[{cluster},{obj}]')
                self.object_variables[cluster, obj] = variable
            for driver in range(self.data.num_drivers):
                self.driver_variables[cluster, driver] = self.model.NewBoolVar(f'driver_var[{cluster},{driver}]')

    def _define_objective(self):
        objective_terms = []
        for cluster in range(self.data.num_clusters):
            for objective_class in self.objectives:
                objective = objective_class(self)
                objective_terms.extend(objective.setup(cluster=cluster))
        self.model.Minimize(sum(objective_terms))


class BackendPlugin:
    def __init__(self, backend: MergeBackend):
        self.backend = backend

    def setup(self, *args, **kwargs):
        return self._setup(self.backend, self.backend.data, *args, **kwargs)

    @staticmethod
    def _setup(backend: MergeBackend, data_store: DataStore, *args, **kwargs):
        raise NotImplementedError()


class ResultParser(BackendPlugin):
    @staticmethod
    def _setup(backend: MergeBackend, data_store: DataStore, solver=None, **kwargs):
        result_clusters = [[] for _ in data_store.clusters_centers]
        result_drivers = [[] for _ in data_store.clusters_centers]
        msgs = [f'Total cost = {solver.ObjectiveValue()}']
        for cluster in range(data_store.num_clusters):
            jobs_capacities = []
            drivers_capacities = []
            for obj in range(data_store.num_objects):
                if solver.BooleanValue(backend.object_variables[cluster, obj]):
                    result_clusters[cluster].append(data_store.objects[obj])
                    jobs_capacities.append(data_store.objects[obj].capacity)
            for driver in range(data_store.num_drivers):
                if solver.BooleanValue(backend.driver_variables[cluster, driver]):
                    result_drivers[cluster].append(data_store.drivers[driver])
                    drivers_capacities.append(data_store.drivers[driver].capacity)
            if data_store.big_clusters.params.use_vehicle_capacity:
                msgs.append(f'CAPACITIES {sum(jobs_capacities) - sum(drivers_capacities)} {sum(drivers_capacities)}')
        if len(data_store.pickups):
            _msgs = ['PICKUPS']
            for cluster in range(data_store.num_clusters):
                for pickup_index, pickup_location in zip(range(data_store.num_pickups), data_store.pickups):
                    _msgs.append(f'cluster {cluster}, pickup {pickup_index} '
                                 f'{pickup_location.real_location} {pickup_location.pointed_location} |'
                                 f'{solver.Value(backend.pickup_variables[cluster, pickup_index])} |'
                                 f'{data_store.pickup_time_to_center[cluster][pickup_index]}')
            if _msgs:
                msgs.append('\n'.join(_msgs))

        result: List[BigCluster] = []
        for index, (clusters, drivers) in enumerate(zip(result_clusters, result_drivers)):
            result.append(Cluster(index, clusters, drivers))
        return result, float(solver.ObjectiveValue()), msgs


class ClustersSize(BackendPlugin):
    @staticmethod
    def _setup(backend: MergeBackend, data_store: DataStore, **kwargs):
        for cluster in range(data_store.num_clusters):
            cluster_size = sum(data_store.object_sizes[obj] * backend.object_variables[cluster, obj]
                               for obj in range(data_store.num_objects))
            backend.model.Add(cluster_size <= data_store.cluster_size_max)
            backend.model.Add(cluster_size >= data_store.cluster_size_min)


class GroupsConstraints(BackendPlugin):
    @staticmethod
    def _setup(backend: MergeBackend, data_store: DataStore, **kwargs):
        for constraint_index, constraint in enumerate(data_store.constraints):
            object_indexes = [
                index
                for cl in constraint.clusters
                for index in data_store.find_object_indexes(cl)
            ]
            driver_indexes = [data_store.drivers.index(dr) for dr in constraint.drivers]
            clusters_have_this_group = []
            for cluster in range(data_store.num_clusters):
                has_this_group = backend.model.NewBoolVar(f'constraint{constraint_index} have indexes at {cluster}]')
                group_objects_count = sum(backend.object_variables[cluster, obj] for obj in object_indexes)
                group_drivers_count = sum(backend.driver_variables[cluster, driver] for driver in driver_indexes)
                backend.model.Add(group_objects_count > 0).OnlyEnforceIf(has_this_group)
                backend.model.Add(group_drivers_count > 0).OnlyEnforceIf(has_this_group)
                backend.model.Add(group_objects_count <= 0).OnlyEnforceIf(has_this_group.Not())
                clusters_have_this_group.append(has_this_group)
            if len(constraint.drivers) < data_store.big_clusters.clusters_count:
                count_of_used_big_clusters = sum(clusters_have_this_group)
                backend.model.Add(count_of_used_big_clusters <= len(constraint.drivers))


class MiniClusterOnlyOneOnBig(BackendPlugin):
    @staticmethod
    def _setup(backend: MergeBackend, data_store: DataStore, **kwargs):
        # Each 'obj' is assigned to exactly one 'cluster'.
        for obj in range(data_store.num_objects):
            backend.model.Add(
                sum([backend.object_variables[cluster, obj] for cluster in range(data_store.num_clusters)]) == 1
            )


class DriverTimeOnClusterConstraints(BackendPlugin):
    @staticmethod
    def _setup(backend: MergeBackend, data_store: DataStore, coefficient=None, **kwargs):
        driver_times_available = [(driver.end_time_sec - driver.start_time_sec) for driver in data_store.drivers]
        for cluster in range(data_store.num_clusters):
            # Time that drivers have for work on current cluster
            drivers_time = sum(
                driver_times_available[driver] * backend.driver_variables[cluster, driver]
                for driver in range(data_store.num_drivers)
            )
            # Minimal time that drivers need to work on this cluster
            driving_time_to_cluster = sum(
                int(data_store.driver_time_to_center[cluster][driver]) * backend.driver_variables[cluster, driver]
                for driver in range(data_store.num_drivers)
            )
            objects_time_on_cluster = sum(
                (int(data_store.object_time_to_center[cluster][obj] * coefficient)
                 * backend.object_variables[cluster, obj])
                for obj in range(data_store.num_objects)
            )
            drivers_count = sum(
                map(lambda driver: backend.driver_variables[cluster, driver], range(data_store.num_drivers))
            )
            pickup_driving_time_on_cluster = 0
            for pickup in range(data_store.num_pickups):
                objects_with_current_pickup = filter(
                    lambda obj: data_store.pickups_objects_map[obj, pickup], range(data_store.num_objects)
                )
                objects_with_current_pickup_on_cluster = list(map(
                    lambda obj: backend.object_variables[cluster, obj], objects_with_current_pickup
                ))
                count_objects_with_pickup_on_cluster_variables = sum(objects_with_current_pickup_on_cluster)

                cluster_have_pickup = backend.model.NewBoolVar(f'[cluster {cluster} have pickup {pickup}]')
                drivers_more_than_objects_with_pickup = backend.model.NewBoolVar(
                    f'[cluster {cluster} pickup {pickup} drivers_more_than_objects]'
                )
                drivers_count_go_to_current_pickup = backend.model.NewIntVar(
                    0, data_store.num_drivers, f'[cluster {cluster} pickup {pickup} drivers_count_go_to_current_pickup]'
                )

                drivers_minus_objects_with_pickup = drivers_count - count_objects_with_pickup_on_cluster_variables
                # If count_objects_with_pickup_on_cluster_variables > 0 and drivers_minus_objects_with_pickup > 0:
                backend.model.Add(count_objects_with_pickup_on_cluster_variables > 0)\
                    .OnlyEnforceIf(cluster_have_pickup)
                backend.model.Add(drivers_minus_objects_with_pickup > 0)\
                    .OnlyEnforceIf(drivers_more_than_objects_with_pickup)
                # then drivers_count_go_to_current_pickup = count_objects_with_pickup_on_cluster_variables:
                backend.model.Add(drivers_count_go_to_current_pickup == count_objects_with_pickup_on_cluster_variables)\
                    .OnlyEnforceIf(cluster_have_pickup).OnlyEnforceIf(drivers_more_than_objects_with_pickup)
                # Else If count_objects_with_pickup_on_cluster_variables > 0 and drivers_minus_objects_with_pickup <= 0:
                backend.model.Add(drivers_minus_objects_with_pickup <= 0)\
                    .OnlyEnforceIf(drivers_more_than_objects_with_pickup.Not())
                # then drivers_count_go_to_current_pickup = drivers_count:
                backend.model.Add(drivers_count_go_to_current_pickup == drivers_count)\
                    .OnlyEnforceIf(cluster_have_pickup).OnlyEnforceIf(drivers_more_than_objects_with_pickup.Not())
                # Else If count_objects_with_pickup_on_cluster_variables <= 0:
                backend.model.Add(count_objects_with_pickup_on_cluster_variables <= 0)\
                    .OnlyEnforceIf(cluster_have_pickup.Not())
                # then drivers_count_go_to_current_pickup = 0:
                backend.model.Add(drivers_count_go_to_current_pickup == 0)\
                    .OnlyEnforceIf(cluster_have_pickup.Not())

                backend.pickup_variables[cluster, pickup] = drivers_count_go_to_current_pickup
                pickup_driving_time_on_cluster += \
                    int(data_store.pickup_time_to_center[cluster][pickup] * coefficient) \
                    * drivers_count_go_to_current_pickup

            cluster_time = objects_time_on_cluster + driving_time_to_cluster + pickup_driving_time_on_cluster
            backend.model.Add(drivers_time >= cluster_time)


class DriverClusterConstraints(BackendPlugin):
    @staticmethod
    def _setup(backend: MergeBackend, data_store: DataStore, coefficient=None, **kwargs):
        for cluster in range(data_store.num_clusters):
            # Each cluster should have at least one driver
            backend.model.Add(
                sum(backend.driver_variables[cluster, driver] for driver in range(data_store.num_drivers)) >= 1
            )
        # Each driver is assigned to exactly one cluster
        for driver in range(data_store.num_drivers):
            backend.model.Add(
                sum([backend.driver_variables[cluster, driver] for cluster in range(data_store.num_clusters)]) == 1
            )


class ClusterTimeObjective(BackendPlugin):
    @staticmethod
    def _setup(backend: MergeBackend, data_store: DataStore, cluster=None, **kwargs):
        result = []
        for obj in range(data_store.num_objects):
            value = data_store.object_time_to_center[cluster][obj] ** 2
            result.append(value * backend.object_variables[cluster, obj])
        return result


class DrivingTimeToPickupObjective(BackendPlugin):
    @staticmethod
    def _setup(backend: MergeBackend, data_store: DataStore, cluster=None, **kwargs):
        result = []
        for pickup in range(data_store.num_pickups):
            value = data_store.pickup_time_to_center[cluster][pickup] ** 2
            result.append(value * backend.pickup_variables[cluster, pickup])
        return result


class DriverTimeObjective(BackendPlugin):
    @staticmethod
    def _setup(backend: MergeBackend, data_store: DataStore, cluster=None, **kwargs):
        result = []
        for driver in range(data_store.num_drivers):
            value = data_store.driver_time_to_center[cluster][driver] ** 2
            result.append(value * backend.driver_variables[cluster, driver])
        return result


class ExceedCapacityPenalty(BackendPlugin):
    @staticmethod
    def _setup(backend: MergeBackend, data_store: DataStore, cluster=None, **kwargs):
        result = []
        if not data_store.big_clusters.params.use_vehicle_capacity:
            return result

        objects_capacities = [
            int(data_store.objects[obj].capacity) * backend.object_variables[cluster, obj]
            for obj in range(data_store.num_objects)
        ]
        drivers_capacities = [
            int(data_store.drivers[driver].capacity) * backend.driver_variables[cluster, driver]
            for driver in range(data_store.num_drivers)
        ]

        penalty_terms = []
        max_penalty = 0
        for center in range(data_store.num_clusters):
            for obj in range(data_store.num_objects):
                value = data_store.object_time_to_center[center][obj] ** 2
                value = int(value * data_store.capacity_penalty_scale)
                max_penalty += value
                penalty_terms.append(value * backend.object_variables[center, obj])
            for driver in range(data_store.num_drivers):
                value = data_store.driver_time_to_center[center][driver] ** 2
                value = int(value * data_store.capacity_penalty_scale)
                max_penalty += value
                penalty_terms.append(value * backend.driver_variables[center, driver])
        max_capacity = int(sum(obj.capacity for obj in data_store.objects))

        capacities_jobs_minus_drivers = cp_model.LinearExpr.Sum(objects_capacities) \
            - cp_model.LinearExpr.Sum(drivers_capacities)
        sum_penalty_terms = cp_model.LinearExpr.Sum(penalty_terms)

        cluster_capacities_bad = backend.model.NewBoolVar(f'[capacities bad at {cluster}]')
        penalty = backend.model.NewIntVar(0, max_penalty, f'[capacity_penalty {cluster}]')
        capacity_positive = backend.model.NewIntVar(0, max_capacity, f'[capacity_positive at {cluster}]')
        result_penalty = backend.model.NewIntVar(0, max_penalty * max_capacity, f'[result capacity penalty {cluster}]')

        # If capacities_jobs_minus_drivers > 0:
        backend.model.Add(capacities_jobs_minus_drivers > 0).OnlyEnforceIf(cluster_capacities_bad)
        # then:
        backend.model.Add(penalty == sum_penalty_terms).OnlyEnforceIf(cluster_capacities_bad)
        backend.model.Add(capacity_positive == capacities_jobs_minus_drivers) \
            .OnlyEnforceIf(cluster_capacities_bad)

        # If capacities_jobs_minus_drivers <= 0:
        backend.model.Add(capacities_jobs_minus_drivers <= 0).OnlyEnforceIf(cluster_capacities_bad.Not())
        # then:
        backend.model.Add(penalty == 0).OnlyEnforceIf(cluster_capacities_bad.Not())
        backend.model.Add(capacity_positive == 0).OnlyEnforceIf(cluster_capacities_bad.Not())

        backend.model.AddMultiplicationEquality(result_penalty, [penalty, capacity_positive])
        result.append(result_penalty)
        return result


class MergeBackendForClusters(MergeBackend):
    """
    Merge MiniClusters into BigClusters.
    """

    setup_plugins = [
        ClustersSize,
        GroupsConstraints,
        MiniClusterOnlyOneOnBig,
        DriverTimeOnClusterConstraints,
        DriverClusterConstraints,
    ]
    objectives = [
        ClusterTimeObjective,
        DrivingTimeToPickupObjective,
        DriverTimeObjective,
        ExceedCapacityPenalty,
    ]
    data_store = ClustersDataStore
    min_computation_seconds = 1.5


class MergeBackendForJobObjects(MergeBackend):
    """
    Merge MiniClusters and JobObjects into BigClusters.
    Some of MiniClusters are splitting into children JobObjects on initialisation.
    These JobObjects are using same way as MiniClusters.
    """

    setup_plugins = [
        ClustersSize,
        GroupsConstraints,
        MiniClusterOnlyOneOnBig,
        DriverTimeOnClusterConstraints,
        DriverClusterConstraints,
    ]
    objectives = [
        ClusterTimeObjective,
        DrivingTimeToPickupObjective,
        DriverTimeObjective,
        ExceedCapacityPenalty,
    ]
    data_store = MixClustersAndJobObjectsDataStore
    # Current MergeBackend usually have more objects to merge, so it needs more calculation time
    min_computation_seconds = 4


class MergeMiniClusters:
    def __init__(self, big_clusters_manager: BigClustersManager, constraints: List[MergeConstraint]):
        """
        :param constraints: Merging algorithm should take into account these constraints of drivers and clusters
        """
        self.manager = big_clusters_manager
        self.constraints = constraints

        self.history: List[Tuple[str, BackendResult]] = []
        self.used_centers_indexes = set()
        self.best: Optional[BackendResult] = None
        self.prev_scores, self.last_coefficient = [], None
        self.big_clusters_centers: List[MiniCluster] = []

    def merge_mini_clusters(self, steps) -> Optional[List[BigCluster]]:
        """
        Merge mini clusters of jobs into big clusters of jobs and drivers.
        :param steps: Count of iterations.
        """

        indexes = list(range(len(self.manager.mini_clusters)))
        random.shuffle(indexes)
        self.used_centers_indexes = set()
        clusters_centers_indexes = indexes[:self.manager.clusters_count]
        self.used_centers_indexes.add(tuple(set(clusters_centers_indexes)))
        self.big_clusters_centers: List[MiniCluster] = [self.manager.mini_clusters[i] for i in clusters_centers_indexes]
        for step in range(1, (steps or 0) + 1):
            event_handler.dev_msg(f'[merge_mini_clusters] Step {step}')
            self.merge_step(step)

        if self.best is not None:
            event_handler.dev_msg(f'[merge_mini_clusters] best score {self.best.score}')

        if self.manager.params.use_vehicle_capacity and self.best is not None \
                and self.should_improve_complex_capacity(self.best):
            self.merge_with_improve_capacity_clustering()

        if self.best is not None:
            return self.best.clusters

    def merge_step(self, step):
        backend = MergeBackendForClusters(
            self.manager, self.big_clusters_centers, self.manager.mini_clusters,
            self.manager.matter_drivers, self.constraints
        )
        merge_result = backend.merge(self.last_coefficient)
        self.history.append((str(step), merge_result))
        self.last_coefficient = merge_result.time_coefficient

        if self.best is None or self.best.score > merge_result.score:
            self.best = merge_result

        randomize_center = None
        if merge_result.score in self.prev_scores[-3:]:
            randomize_center = random.randint(0, len(merge_result.clusters) - 1)
        self.big_clusters_centers = self.calculate_big_clusters_centers(merge_result, randomize_center)
        self.prev_scores.append(merge_result.score)

    def merge_with_improve_capacity_clustering(self):
        event_handler.dev_msg('Improve capacity clustering')
        self.big_clusters_centers = self.best.initial_big_clusters_centers
        backend = MergeBackendForJobObjects(
            self.manager, self.big_clusters_centers, self.manager.mini_clusters,
            self.manager.matter_drivers, self.constraints, related_results=self.best
        )
        merge_result = backend.merge(self.last_coefficient, final_improving=True)
        self.history.append(('Improved capacity clustering', merge_result))
        self.best = merge_result

    def calculate_big_clusters_centers(self, merge_result, randomize_center: Optional[int] = None):
        """
        Calculate centers for big clusters from 'merge_result'.
        :param merge_result: Result of current merge.
        :param randomize_center: Take random mini cluster as center for specified big cluster.
        :return:
        """
        big_clusters_centers = []
        clusters_centers_indexes = []
        for _ in range(5):
            big_clusters_centers = []
            clusters_centers_indexes = []
            for i, big_cl in enumerate(merge_result.clusters):
                if i == randomize_center:
                    center_of_big = big_cl.objects[random.randint(0, len(big_cl.objects) - 1)]
                else:
                    center_of_big = self.find_new_center_of_big_cluster(big_cl)[0]
                big_clusters_centers.append(center_of_big)
                clusters_centers_indexes.append(center_of_big.index)

            if tuple(set(clusters_centers_indexes)) in self.used_centers_indexes:
                randomize_center = random.randint(0, len(merge_result.clusters)-1)
                continue
            break
        self.used_centers_indexes.add(tuple(set(clusters_centers_indexes)))
        return big_clusters_centers

    @staticmethod
    def should_improve_complex_capacity(merge_result):
        """
        Decide whether we should start improving current case or not.
        Depends on capacity of jobs and drivers on every cluster from 'merge_result'.
        :return: True if we should improve.
        """
        capacity_diff = 0
        used_capacity_diff = 0
        for cluster in merge_result.clusters:
            jobs_capacities = sum(job_obj.capacity for job_obj in cluster.job_objects)
            drivers_capacities = sum(driver.capacity for driver in cluster.drivers)
            diff = jobs_capacities - drivers_capacities
            capacity_diff += diff
            used_capacity_diff += max(diff, 0)
        return used_capacity_diff > capacity_diff and used_capacity_diff > 0

    def find_new_center_of_big_cluster(self, big_cluster: BigCluster, limit=1) -> List[MiniCluster]:
        distances_matrix = []
        for i, cluster in enumerate(big_cluster.objects):
            distances_matrix.append([])
            for j, cl in enumerate(big_cluster.objects):
                if j < i:
                    distances_matrix[-1].append(distances_matrix[j][i])
                    continue
                distances_matrix[-1].append((int(self.manager.distance_between_clusters(cluster, cl)), cl.size))
        score_index = [
            (
                int(math.sqrt(
                    sum(map(lambda x: x[1]*(x[0]**2), distances_to_other))/sum(map(lambda x: x[1], distances_to_other))
                )),
                cluster_index
            )
            for cluster_index, distances_to_other in enumerate(distances_matrix)
        ]
        sorted_average_clusters_indexes = list(map(itemgetter(1), sorted(score_index, key=itemgetter(0))))
        return [big_cluster.objects[i] for i in sorted_average_clusters_indexes[:limit]]
