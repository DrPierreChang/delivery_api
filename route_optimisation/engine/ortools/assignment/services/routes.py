import copy
import math
from abc import ABC
from operator import attrgetter
from typing import Dict, Iterable, List, Optional, Tuple

from ortools.constraint_solver import pywrapcp

from route_optimisation.utils.breaks import ManualBreak, ManualBreakInDriverRoute, Part

from ... import constants
from ...context import BaseAssignmentContext
from ...helper_classes import Delivery, JobSite, Pickup, Vehicle
from .base import BaseImproveRouteService
from .types import ClosenessScore, RoutePointIndex


class PointToReassign:
    def __init__(self, pickups_indices: List[RoutePointIndex], delivery_index: RoutePointIndex):
        self.pickups_indices: List[RoutePointIndex] = pickups_indices
        self.delivery_index: RoutePointIndex = delivery_index

    def minimal_job_capacity(self, context, routing_manager):
        return abs(sum(
            context.Capacity(None, routing_manager.IndexToNode(point_index))
            for point_index in self.pickups_indices + [self.delivery_index]
        ))

    def minimal_service_time(self, vehicle_idx, context, routing_manager):
        return sum(
            context.ServiceTime(vehicle_idx, None, routing_manager.IndexToNode(point_index))
            for point_index in self.pickups_indices + [self.delivery_index]
        )

    def __str__(self):
        return f'PointToReassign({self.pickups_indices},{self.delivery_index})'


class RouteBase:
    def __init__(self, vehicle_idx: int, job_points: List[RoutePointIndex],
                 context: BaseAssignmentContext, routing_manager: pywrapcp.RoutingIndexManager, routes_manager):
        self.vehicle_idx: int = vehicle_idx
        self.vehicle: Vehicle = context.vehicles[vehicle_idx]
        self.job_points: List[RoutePointIndex] = job_points
        self.context = context
        self.routing_manager = routing_manager
        self.routes_manager = routes_manager
        self.fixed_end_time = None

    def __copy__(self):
        return self.__class__(
            self.vehicle_idx, list(self.job_points), self.context, self.routing_manager, self.routes_manager
        )

    @property
    def working_end_time(self):
        return self.fixed_end_time or self.vehicle.end_time

    @property
    def working_time(self):
        return self.working_end_time - self.vehicle.start_time

    def _is_delivery_point_index(self, point_index: RoutePointIndex) -> bool:
        point_node = self.routing_manager.IndexToNode(point_index)
        point_object = self.context.points[point_node]
        return isinstance(point_object, Delivery)

    def _is_pickup_point_index(self, point_index: RoutePointIndex) -> bool:
        point_node = self.routing_manager.IndexToNode(point_index)
        point_object = self.context.points[point_node]
        return isinstance(point_object, Pickup)

    @property
    def delivery_job_points(self) -> Iterable[RoutePointIndex]:
        return (p for p in self.job_points if self._is_delivery_point_index(p))

    @property
    def pickup_job_points(self) -> Iterable[RoutePointIndex]:
        return (p for p in self.job_points if self._is_pickup_point_index(p))

    def get_start_capacity(self):
        start_depot_node = self.context.start_locations[self.vehicle_idx]
        end_depot_node = self.context.end_locations[self.vehicle_idx]
        start_capacity = 0
        prev_point_node = start_depot_node
        for point_index in self.job_points:
            point_node = self.routing_manager.IndexToNode(point_index)
            start_capacity += self.context.Capacity(prev_point_node, point_node)
            prev_point_node = point_node
        start_capacity += self.context.Capacity(prev_point_node, end_depot_node)
        return abs(start_capacity)

    @property
    def route_hash(self):
        return hash((self.vehicle_idx, tuple(self.job_points), self.fixed_end_time))


class RouteService:
    def __init__(self, route: RouteBase, context: BaseAssignmentContext, routing_manager: pywrapcp.RoutingIndexManager):
        self.route = route
        self.context = context
        self.routing_manager = routing_manager

    @property
    def value(self):
        return self._get_value()

    def _get_value(self):
        raise NotImplementedError()

    def handle(self, *args, **kwargs):
        raise NotImplementedError()


class CachedValueRouteService(RouteService, ABC):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cached = None

    @property
    def value(self):
        if self._cached is not None:
            prev_points_hash, result = self._cached
            if prev_points_hash == hash(tuple(self.route.job_points)):
                return result
        result = super().value
        self._cached = (hash(tuple(self.route.job_points)), result)
        return result

    def handle(self, *args, **kwargs):
        pass


class HandleRouteService(RouteService, ABC):
    def _get_value(self):
        pass


class ManualBreaksValidator:
    def __init__(self, route: RouteBase, context: BaseAssignmentContext, routing_manager: pywrapcp.RoutingIndexManager,
                 only_orders):
        self.context = context
        self.only_orders = only_orders
        self.route = route
        self.routing_manager = routing_manager

    def __call__(self, parts: List[Part], *args, **kwargs):
        for part in parts:
            if part.kind == Part.SERVICE and not self._is_time_good(part):
                return False
        if self.only_orders:
            return True
        return parts[-1].end < self.route.working_end_time

    def _is_time_good(self, part: Part):
        order_node = self.routing_manager.IndexToNode(part.point)
        time_from, time_to = self.context.orders_times[order_node - len(self.context.sites)]
        return time_from <= part.end <= time_to


class OrToolsManualBreakInDriverRoute(ManualBreakInDriverRoute):
    def __init__(self, route: RouteBase, context: BaseAssignmentContext, routing_manager: pywrapcp.RoutingIndexManager,
                 only_orders=False):
        parts = self._get_route_parts(route, context, routing_manager)
        breaks = [ManualBreak(b.start_time, b.end_time, diff_allowed_seconds=b.diff_allowed)
                  for b in route.vehicle.breaks]
        super().__init__(parts, breaks)
        self.validators.append(ManualBreaksValidator(route, context, routing_manager, only_orders))

    def _get_route_parts(self, route: RouteBase, context: BaseAssignmentContext,
                         routing_manager: pywrapcp.RoutingIndexManager) -> List[Part]:
        parts: List[Part] = []
        prev_point_node = context.start_locations[route.vehicle_idx]
        cumul_time = route.vehicle.start_time
        for point_index in route.job_points:
            point_node = routing_manager.IndexToNode(point_index)
            _start = cumul_time
            cumul_time += context.TotalTime(route.vehicle_idx, prev_point_node, point_node)
            parts.append(Part(_start, cumul_time, Part.TRANSIT, point_index))
            _start = cumul_time
            cumul_time += context.ServiceTime(route.vehicle_idx, prev_point_node, point_node)
            parts.append(Part(_start, cumul_time, Part.SERVICE, point_index))
            prev_point_node = point_node
        _start = cumul_time
        cumul_time += context.TotalTime(route.vehicle_idx, prev_point_node, context.end_locations[route.vehicle_idx])
        parts.append(Part(_start, cumul_time, Part.TRANSIT, None))
        return parts

    def get_time_finish(self) -> Optional[int]:
        parts = self.get_parts_with_breaks()
        if parts:
            return parts[-1].end


class RouteFinishTime(CachedValueRouteService):
    def _get_value(self):
        if not self.route.vehicle.breaks:
            return self._calc_finish_time_no_breaks()
        route_time_with_breaks = OrToolsManualBreakInDriverRoute(self.route, self.context, self.routing_manager)
        result = route_time_with_breaks.get_time_finish()
        if result is not None:
            return result
        return constants.TWO_DAYS

    def _calc_finish_time_no_breaks(self):
        start_depot_node = self.context.start_locations[self.route.vehicle_idx]
        end_depot_node = self.context.end_locations[self.route.vehicle_idx]
        prev_point_node = start_depot_node
        cumul_time = self.route.vehicle.start_time
        for point_index in self.route.job_points:
            point_node = self.routing_manager.IndexToNode(point_index)
            cumul_time += self.context.TotalTimeWithService(self.route.vehicle_idx, prev_point_node, point_node)
            prev_point_node = point_node
        cumul_time += self.context.TotalTimeWithService(self.route.vehicle_idx, prev_point_node, end_depot_node)
        return cumul_time


class RouteDuration(RouteFinishTime):
    def _get_value(self):
        route_finish_time = super()._get_value()
        return route_finish_time - self.route.vehicle.start_time


class MinimalJobCapacityOnRoute(CachedValueRouteService):
    def _get_value(self):
        value = None
        for delivery_point_index in self.route.delivery_job_points:
            pickups_indices = list(
                get_related_pickups_indices(delivery_point_index, self.context, self.routing_manager)
            )
            delivery_capacity_diff = abs(sum(
                self.context.Capacity(None, self.routing_manager.IndexToNode(point_index))
                for point_index in pickups_indices + [delivery_point_index]
            ))
            if value is None:
                value = delivery_capacity_diff
                continue
            value = min(value, delivery_capacity_diff)
        return value


class MinimalServiceTimeOnRoute(CachedValueRouteService):
    def _get_value(self):
        value = None
        for delivery_point_index in self.route.delivery_job_points:
            pickups_indices = list(
                get_related_pickups_indices(delivery_point_index, self.context, self.routing_manager)
            )
            service_time_diff = sum(
                self.context.ServiceTime(self.route.vehicle_idx, None, self.routing_manager.IndexToNode(point_index))
                for point_index in pickups_indices + [delivery_point_index]
            )
            if value is None:
                value = service_time_diff
                continue
            value = min(value, service_time_diff)
        return value


class MaxUsedCapacityOnRoute(CachedValueRouteService):
    def _get_value(self):
        start_depot_node = self.context.start_locations[self.route.vehicle_idx]
        end_depot_node = self.context.end_locations[self.route.vehicle_idx]
        start_capacity = self.route.get_start_capacity()
        capacities = []
        prev_point_node = start_depot_node
        cumul_capacity = start_capacity
        capacities.append(cumul_capacity)
        for point_index in self.route.job_points:
            point_node = self.routing_manager.IndexToNode(point_index)
            cumul_capacity += self.context.Capacity(prev_point_node, point_node)
            capacities.append(cumul_capacity)
            prev_point_node = point_node
        cumul_capacity += self.context.Capacity(prev_point_node, end_depot_node)
        capacities.append(cumul_capacity)
        return max(capacities)


class CanAddDelivery(HandleRouteService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cached = {}

    def handle(self, point_to_reassign: PointToReassign, *args, **kwargs) -> bool:
        if point_to_reassign.delivery_index in self._cached:
            return self._cached[point_to_reassign.delivery_index]
        vehicle = self.route.vehicle
        delivery_point_node = self.routing_manager.IndexToNode(point_to_reassign.delivery_index)
        delivery_point = self.context.points[delivery_point_node]
        result = delivery_point.check_vehicle_skills_set(vehicle) and delivery_point.is_allowed_vehicle(vehicle)
        self._cached[point_to_reassign.delivery_index] = result
        return result


class AllTimeValidator(HandleRouteService):
    def handle(self, only_orders=False, *args, **kwargs) -> bool:
        if not self.route.vehicle.breaks:
            return self._calc_no_breaks(only_orders=only_orders)
        route_time_with_breaks = OrToolsManualBreakInDriverRoute(self.route, self.context, self.routing_manager,
                                                                 only_orders=only_orders)
        result = route_time_with_breaks.get_time_finish()
        return result is not None

    def _calc_no_breaks(self, only_orders=False):
        start_depot_node = self.context.start_locations[self.route.vehicle_idx]
        end_depot_node = self.context.end_locations[self.route.vehicle_idx]
        prev_point_node = start_depot_node
        cumul_time = self.route.vehicle.start_time
        for point_index in self.route.job_points:
            point_node = self.routing_manager.IndexToNode(point_index)
            cumul_time += self.context.TotalTimeWithService(self.route.vehicle_idx, prev_point_node, point_node)
            point: JobSite = self.context.points[point_node]
            point_start_time, point_end_time = self.context.get_order_period(point)
            if cumul_time < point_start_time or cumul_time > point_end_time:
                return False
            prev_point_node = point_node
        if only_orders:
            return True
        cumul_time += self.context.TotalTimeWithService(self.route.vehicle_idx, prev_point_node, end_depot_node)
        return cumul_time < self.route.working_end_time


class CapacityValidator(HandleRouteService):
    def handle(self, *args, **kwargs) -> bool:
        if not self.context.use_vehicle_capacity:
            return True
        start_depot_node = self.context.start_locations[self.route.vehicle_idx]
        end_depot_node = self.context.end_locations[self.route.vehicle_idx]
        start_capacity = self.route.get_start_capacity()
        max_capacity = self.route.vehicle.capacity
        if start_capacity > max_capacity:
            return False

        prev_point_node = start_depot_node
        cumul_capacity = start_capacity
        for point_index in self.route.job_points:
            point_node = self.routing_manager.IndexToNode(point_index)
            cumul_capacity += self.context.Capacity(prev_point_node, point_node)
            if cumul_capacity > max_capacity:
                return False
            prev_point_node = point_node
        cumul_capacity += self.context.Capacity(prev_point_node, end_depot_node)
        return cumul_capacity <= max_capacity


class RequiredSequenceValidator(HandleRouteService):
    def handle(self, *args, **kwargs) -> bool:
        vehicle = self.route.vehicle
        if vehicle.required_start_sequence is None:
            return True
        self_points = [self.context.start_locations[self.route.vehicle_idx]] \
            + list(map(self.routing_manager.IndexToNode, self.route.job_points)) \
            + [self.context.end_locations[self.route.vehicle_idx]]
        if len(self_points) < len(vehicle.required_start_sequence):
            return False
        for required_site, real_node in zip(vehicle.required_start_sequence, self_points):
            required_site_node = self.context.points_node_id_map[required_site.unique_id]
            if required_site_node != real_node:
                return False
        return True


class ClosenessScoreService(HandleRouteService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cached: Dict[RoutePointIndex: Tuple[int, ClosenessScore]] = {}

    def handle(self, point_index: RoutePointIndex, *args, **kwargs) -> ClosenessScore:
        _cached = self._cached.get(point_index)
        if _cached is not None:
            prev_points_hash, point_closeness_score = _cached
            if prev_points_hash == hash(tuple(self.route.job_points)):
                return point_closeness_score

        values = []
        start_depot_node = self.context.start_locations[self.route.vehicle_idx]
        end_depot_node = self.context.end_locations[self.route.vehicle_idx]
        for self_point_index in self.route.job_points:
            if point_index == self_point_index:
                continue
            values.append(self.context.TotalTime(
                self.route.vehicle_idx,
                self.routing_manager.IndexToNode(point_index),
                self.routing_manager.IndexToNode(self_point_index),
            ))
        for depot_node in [start_depot_node, end_depot_node]:
            values.append(self.context.TotalTime(
                self.route.vehicle_idx,
                self.routing_manager.IndexToNode(point_index),
                depot_node,
            ))
        point_closeness_score = ClosenessScore(round(self.point_closeness_score_func(values), 2))
        self._cached[point_index] = (hash(tuple(self.route.job_points)), point_closeness_score)
        return point_closeness_score

    @staticmethod
    def point_closeness_score_func(values: List[int]) -> float:
        percent_first_closest = 0.8
        values = sorted(values)[:math.ceil(len(values)*percent_first_closest)]
        return sum(values)/len(values)


class Route(RouteBase):
    def __init__(self, vehicle_idx, job_points, context: BaseAssignmentContext,
                 routing_manager: pywrapcp.RoutingIndexManager, routes_manager):
        super().__init__(vehicle_idx, job_points, context, routing_manager, routes_manager)
        self._route_duration = RouteDuration(self, context, routing_manager)
        self._route_finish_time = RouteFinishTime(self, context, routing_manager)
        self._minimal_job_capacity_on_route = MinimalJobCapacityOnRoute(self, context, routing_manager)
        self._minimal_service_time_on_route = MinimalServiceTimeOnRoute(self, context, routing_manager)
        self._max_used_capacity = MaxUsedCapacityOnRoute(self, context, routing_manager)
        self._can_add_delivery = CanAddDelivery(self, context, routing_manager)
        self._all_time_validator = AllTimeValidator(self, context, routing_manager)
        self._capacity_validator = CapacityValidator(self, context, routing_manager)
        self._required_sequence_validator = RequiredSequenceValidator(self, context, routing_manager)
        self._closeness_score_service = ClosenessScoreService(self, context, routing_manager)

    @property
    def can_be_empty(self):
        return self.routes_manager.route_can_be_skipped

    @property
    def minimal_job_capacity_on_route(self):
        return self._minimal_job_capacity_on_route.value

    @property
    def minimal_service_time_on_route(self):
        return self._minimal_service_time_on_route.value

    def get_route_finish_time(self) -> int:
        return self._route_finish_time.value

    @property
    def get_route_duration(self) -> int:
        return self._route_duration.value

    @property
    def get_max_used_capacity(self) -> int:
        if not self.context.use_vehicle_capacity:
            return 0
        return self._max_used_capacity.value

    def pop(self, index=-1) -> int:
        return self.job_points.pop(index)

    def remove_point(self, point: RoutePointIndex):
        self.job_points.pop(self.job_points.index(point))

    def add_point(self, point_to_reassign: PointToReassign, after_point=None, after=True):
        """
        Simply add point to route: pickups on first place, delivery at the end of route.
        """
        self.job_points = point_to_reassign.pickups_indices + self.job_points
        if after_point is not None:
            self.job_points.insert(self.job_points.index(after_point) + int(after), point_to_reassign.delivery_index)
        else:
            self.job_points.append(point_to_reassign.delivery_index)

    def take_point_for_reassign(self, delivery_point_index: RoutePointIndex) -> Optional[PointToReassign]:
        if not self.can_be_empty and len(list(self.delivery_job_points)) < 2:
            return
        delivery_point_node = self.routing_manager.IndexToNode(delivery_point_index)
        delivery_point = self.context.points[delivery_point_node]
        if not delivery_point.allow_skip:
            return
        self.remove_point(delivery_point_index)
        pickups_indices = list(get_related_pickups_indices(delivery_point_index, self.context, self.routing_manager))
        for deleted_pickup_point_index in pickups_indices:
            self.remove_point(deleted_pickup_point_index)
        return PointToReassign(pickups_indices, delivery_point_index)

    @property
    def get_time_left(self) -> int:
        finish_time = self.get_route_finish_time()
        max_time = self.working_end_time
        return max_time - finish_time

    def is_route_time_good(self) -> bool:
        return self.get_time_left >= 0

    def can_add_delivery(self, point: PointToReassign) -> bool:
        return self._can_add_delivery.handle(point)

    def can_extend_used_capacity(self, from_route=None, point_for_reassign: PointToReassign = None):
        if self.context.use_vehicle_capacity:
            minimal_possible_new_capacity = None
            if from_route is not None:
                minimal_possible_new_capacity = from_route.minimal_job_capacity_on_route
            elif point_for_reassign is not None:
                minimal_possible_new_capacity = point_for_reassign.minimal_job_capacity(
                    self.context, self.routing_manager
                )
            if minimal_possible_new_capacity is not None and minimal_possible_new_capacity > 0:
                max_used_capacity = self.get_max_used_capacity
                if self.vehicle.capacity < max_used_capacity + minimal_possible_new_capacity:
                    return False
        return True

    def can_extend_used_time(self, from_route=None, point_for_reassign: PointToReassign = None):
        minimal_possible_new_service_time = None
        if from_route is not None:
            minimal_possible_new_service_time = from_route.minimal_service_time_on_route
        elif point_for_reassign is not None:
            minimal_possible_new_service_time = point_for_reassign.minimal_service_time(
                self.vehicle_idx, self.context, self.routing_manager
            )
        if minimal_possible_new_service_time is not None and minimal_possible_new_service_time > self.get_time_left:
            return False
        return True

    def is_all_time_valid(self, only_orders=False) -> bool:
        return self._all_time_validator.handle(only_orders)

    def is_capacities_valid(self) -> bool:
        return self._capacity_validator.handle()

    def is_required_sequence_valid(self):
        return self._required_sequence_validator.handle()

    def is_valid(self, only_orders=False) -> bool:
        return self.is_all_time_valid(only_orders) and self.is_capacities_valid() and self.is_required_sequence_valid()

    def is_fully_valid(self):
        return self.is_valid() \
               and all(self.can_add_delivery(PointToReassign([], point)) for point in self.delivery_job_points)

    def calculate_point_closeness_score(self, point_index: RoutePointIndex) -> ClosenessScore:
        return self._closeness_score_service.handle(point_index)

    def find_best_place(self, point_for_reassign: PointToReassign, max_duration=None):
        case_hash = hash((self.route_hash, point_for_reassign.delivery_index))
        if case_hash in self.routes_manager.route_find_best_place_cache:
            result = self.routes_manager.route_find_best_place_cache[case_hash]
            if result is None:
                return
            route_to_return = copy.copy(self)
            route_to_return.job_points = list(result)
            return route_to_return
        result = self._find_best_place(point_for_reassign, max_duration)
        if len(self.routes_manager.route_find_best_place_cache) < 100000:
            self.routes_manager.route_find_best_place_cache[case_hash] = \
                list(result.job_points) if result is not None else result
        return result

    def _find_best_place(self, point_for_reassign: PointToReassign, max_duration=None):
        if not self.can_add_delivery(point_for_reassign):
            return
        if not self.can_extend_used_capacity(point_for_reassign=point_for_reassign):
            return
        if not self.can_extend_used_time(point_for_reassign=point_for_reassign):
            return

        best_route_to, best_value = None, max_duration * 2 if max_duration is not None else 1000000
        for before_point_index in self.job_points:
            route_to_copy = copy.copy(self)
            route_to_copy.add_point(point_for_reassign, before_point_index, after=False)
            check_result = self._compare_durations(route_to_copy, best_value)
            if check_result is not None:
                best_value = check_result
                best_route_to = route_to_copy
        route_to_copy = copy.copy(self)
        route_to_copy.add_point(point_for_reassign)
        check_result = self._compare_durations(route_to_copy, best_value)
        if check_result is not None:
            best_route_to = route_to_copy
        return best_route_to

    @staticmethod
    def _compare_durations(route, best_value):
        if not route.is_valid():
            return
        duration_value = route.get_route_duration
        if duration_value >= best_value:
            return
        return duration_value


def get_related_pickups_indices(delivery_point_index: RoutePointIndex, assignment_context: BaseAssignmentContext,
                                routing_manager: pywrapcp.RoutingIndexManager):
    delivery_point_node = routing_manager.IndexToNode(delivery_point_index)
    delivery_point = assignment_context.points[delivery_point_node]
    for pickup, delivery in assignment_context.pickup_delivery:
        if delivery_point.unique_id == delivery.unique_id:
            yield routing_manager.NodeToIndex(assignment_context.points_node_id_map[pickup.unique_id])


class RoutesManager(BaseImproveRouteService):
    def __init__(self, routes, context: BaseAssignmentContext, routing_manager: pywrapcp.RoutingIndexManager,
                 route_find_best_place_cache: dict, route_can_be_skipped=False):
        super().__init__(context, routing_manager)
        self.route_find_best_place_cache = route_find_best_place_cache
        self.route_can_be_skipped = route_can_be_skipped
        self._routes: Dict[int, Route] = {}
        for vehicle_idx, route in enumerate(routes):
            self._routes[vehicle_idx] = Route(vehicle_idx, route, self.context, self.routing_manager, self)

    @property
    def routes_times(self):
        return list(map(attrgetter('get_route_duration'), self._routes.values()))

    @property
    def working_times(self):
        return list(map(attrgetter('working_time'), self._routes.values()))

    def fix_end_times(self):
        top_count = math.ceil((len(self._routes)-1)/3)
        ordered_routes = sorted(self._routes.values(), key=attrgetter('get_route_duration'), reverse=True)
        top = ordered_routes[:top_count]
        coefficient = 1.1
        for route in top:
            route.fixed_end_time = min(route.vehicle.start_time + int(route.get_route_duration * coefficient),
                                       route.vehicle.end_time)
        for route in ordered_routes[top_count:]:
            route.fixed_end_time = min(route.vehicle.start_time + int(top[-1].get_route_duration * coefficient),
                                       route.vehicle.end_time)

    def unfix_end_times(self):
        for route in self._routes.values():
            route.fixed_end_time = None

    @property
    def longest_route(self):
        return max(self._routes.values(), key=attrgetter('get_route_duration'))

    @property
    def fastest_route(self):
        return min(self._routes.values(), key=attrgetter('get_route_duration'))

    def rewrite_routes(self, *routes: Route):
        if len(routes) == 0:
            return
        for route in routes:
            route.fixed_end_time = self._routes[route.vehicle_idx].fixed_end_time
            self._routes[route.vehicle_idx] = route
        exists = set()
        for route in self._routes.values():
            for point in route.delivery_job_points:
                if point in exists:
                    raise Exception('should not exist')
                exists.add(point)

    def list_routes(self, exclude: Optional[Iterable[Route]] = None):
        exclude = exclude or []
        exclude_indexes = [exclude_route.vehicle_idx for exclude_route in exclude]
        for route in self._routes.values():
            if route.vehicle_idx in exclude_indexes:
                continue
            yield route

    @property
    def routes(self):
        return [self._routes[i].job_points for i in range(len(self.context.vehicles))]

    @property
    def not_empty_routes_count(self):
        return len([1 for route in self._routes.values() if route.job_points])

    def set_routes(self, routes):
        self._routes: Dict[int, Route] = {}
        for vehicle_idx, route in enumerate(routes):
            self._routes[vehicle_idx] = Route(vehicle_idx, route, self.context, self.routing_manager, self)

    def routes_time_end(self, exceed=1):
        result = []
        for vehicle_idx, veh in enumerate(self.context.vehicles):
            duration = self._routes[vehicle_idx].get_route_duration
            result.append(min((int(veh.start_time + duration*exceed), veh.end_time)))
        return result

    def __getitem__(self, item):
        return self._routes[item]
