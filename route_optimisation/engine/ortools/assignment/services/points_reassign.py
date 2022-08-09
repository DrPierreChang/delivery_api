import copy
from operator import itemgetter
from typing import Iterable, List, Tuple

from ortools.constraint_solver import pywrapcp

from ...context import BaseAssignmentContext
from ...helper_classes import Delivery
from .base import BaseImproveRouteProcess, BaseImproveRouteService
from .routes import PointToReassign, Route, RoutesManager, get_related_pickups_indices
from .types import RoutePointIndex


class ReassignPointsManager(BaseImproveRouteService):
    def __init__(self, context: BaseAssignmentContext, routing_manager: pywrapcp.RoutingIndexManager):
        super().__init__(context, routing_manager)
        self.skipped_found = False
        self.points_to_reassign: List[PointToReassign] = []
        self.active_points_to_reassign = []

    @property
    def has_points(self):
        return bool(self.points_to_reassign)

    def activate_points_to_reassign(self, routes: RoutesManager):
        """
        Find 30 closest points to hubs. Activate them to future reassign actions.
        """
        sorted_points = self._sort_points_by_closeness_to_hubs(routes)
        self.active_points_to_reassign = list(sorted_points)[:30]

    def _sort_points_by_closeness_to_hubs(self, routes: RoutesManager) -> Iterable[PointToReassign]:
        points_list: List[Tuple[int, PointToReassign]] = []
        for point_to_reassign in self.points_to_reassign:
            min_value = None
            for route in routes.list_routes():
                if not route.can_add_delivery(point_to_reassign):
                    continue
                # Create route only with hubs and current point
                one_point_route = Route(
                    route.vehicle_idx,
                    point_to_reassign.pickups_indices + [point_to_reassign.delivery_index],
                    self.context, self.routing_manager, routes
                )
                if min_value is None or one_point_route.get_route_duration < min_value:
                    min_value = one_point_route.get_route_duration
            if min_value is not None:
                points_list.append((min_value, point_to_reassign))
        return map(itemgetter(1), sorted(points_list, key=itemgetter(0)))

    def find_skipped_points(self, assigned_routes: RoutesManager):
        assert not self.skipped_found
        skipped_deliveries_nodes = {i for i, point in enumerate(self.context.points) if isinstance(point, Delivery)}
        for route in assigned_routes.list_routes():
            skipped_deliveries_nodes.difference_update(set(map(self.routing_manager.IndexToNode, route.job_points)))
        skipped = []
        for delivery_node in skipped_deliveries_nodes:
            delivery_index = self.routing_manager.NodeToIndex(delivery_node)
            pickup_indices = list(get_related_pickups_indices(delivery_index, self.context, self.routing_manager))
            skipped.append(PointToReassign(pickup_indices, delivery_index))
        self.points_to_reassign.extend(skipped)
        self.skipped_found = True

    def take_point_for_reassign(self, route, point=None):
        point_for_reassign = route.take_point_for_reassign(point or route.job_points[-1])
        if point_for_reassign:
            self.points_to_reassign.append(point_for_reassign)

    def get(self, point: RoutePointIndex):
        found = list(filter(lambda x: x.delivery_index == point, self.active_points_to_reassign))
        if found:
            return found[0]


class SoftAssignmentRoutesCleaner:
    """
    Take points from route until route time is not exceed available time window.
    """
    def __init__(self, routes: RoutesManager, reassign_points: ReassignPointsManager):
        self._routes: RoutesManager = routes
        self.reassign_points: ReassignPointsManager = reassign_points
        self.cant_get_point = None

    def process(self):
        self.reassign_points.find_skipped_points(self._routes)
        for route in self._routes.list_routes():
            while not route.is_route_time_good():
                point_to_reassign, route_copy = self._find_best_point_to_take(route, validate_only_orders=True)
                if not point_to_reassign:
                    point_to_reassign, route_copy = self._find_best_point_to_take(route, validate_only_orders=False)
                    if not point_to_reassign:
                        raise Exception('cant get point')
                self.reassign_points.points_to_reassign.append(point_to_reassign)
                route.job_points = route_copy.job_points

    @staticmethod
    def _find_best_point_to_take(route: Route, validate_only_orders=False):
        start_duration = route.get_route_duration
        best_point_for_reassign, best_route, max_diff = None, None, -1
        for point_index in route.delivery_job_points:
            route_copy = copy.copy(route)
            point_for_reassign = route_copy.take_point_for_reassign(point_index)
            diff = start_duration - route_copy.get_route_duration
            if diff <= max_diff:
                continue
            if not route_copy.is_valid(only_orders=validate_only_orders):
                continue
            best_point_for_reassign, best_route, max_diff = point_for_reassign, route_copy, diff
        return best_point_for_reassign, best_route


class RoutePointsReassignHelper(BaseImproveRouteProcess):
    """
    Service assigns points on routes by minimal increasing of route duration.
    """

    def __init__(self, routes: RoutesManager, reassign_points: ReassignPointsManager,
                 context: BaseAssignmentContext, routing_manager: pywrapcp.RoutingIndexManager):
        super().__init__(context, routing_manager)
        self._routes: RoutesManager = routes
        self._reassign_points: ReassignPointsManager = reassign_points
        self._fill_reassign_cache = {}

    def process(self):
        self._fill_reassign_cache = {}
        should_continue = True
        while self._reassign_points.has_points and should_continue:
            should_continue = False
            result = self._find_best_place_by_duration()
            if not result:
                continue
            should_continue = True
            best_point_to_reassign_index, updated_route = result
            point_to_reassign = self._reassign_points.active_points_to_reassign.pop(best_point_to_reassign_index)
            self._reassign_points.points_to_reassign.pop(
                self._reassign_points.points_to_reassign.index(point_to_reassign))
            self._routes.rewrite_routes(updated_route)
            del self._fill_reassign_cache[updated_route.vehicle_idx]
        self._fill_reassign_cache = {}

    def _find_best_place_by_duration(self):
        best_index, best_diff_of_duration, best_route_to = None, 10000000, None
        for index, point_to_reassign in enumerate(self._reassign_points.active_points_to_reassign):
            for route_to in self._routes.list_routes():
                if route_to.vehicle_idx not in self._fill_reassign_cache:
                    self._fill_reassign_cache[route_to.vehicle_idx] = {}
                if point_to_reassign in self._fill_reassign_cache[route_to.vehicle_idx]:
                    route_to_copy = self._fill_reassign_cache[route_to.vehicle_idx][point_to_reassign]
                else:
                    route_to_copy = route_to.find_best_place(point_to_reassign, None)
                    self._fill_reassign_cache[route_to.vehicle_idx][point_to_reassign] = route_to_copy
                if not route_to_copy:
                    continue
                diff = route_to_copy.get_route_duration - route_to.get_route_duration
                if diff < best_diff_of_duration:
                    best_diff_of_duration = diff
                    best_index = index
                    best_route_to = route_to_copy
        if best_index is not None:
            return best_index, best_route_to
