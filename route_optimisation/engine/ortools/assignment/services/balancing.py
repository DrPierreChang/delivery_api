import copy
from operator import attrgetter, itemgetter
from typing import Iterable, Optional, Tuple

from ortools.constraint_solver import pywrapcp

from ...context import BaseAssignmentContext
from .base import BaseImproveRouteProcess
from .routes import PointToReassign, Route, RoutesManager
from .types import RoutePointIndex


def need_rebalance(balancing_percent, routes: RoutesManager):
    """
    Determines if `routes` are balanced within the specified allowed `balancing_percent`.

    :param balancing_percent: Allowed difference between routes.
    :param routes:
    :return: True in case routes should be balanced.
    """
    routes_times = routes.routes_times
    avg = sum(routes_times)/len(routes_times)
    for routes_time in routes_times:
        route_diff = (abs(routes_time-avg)/avg) * 100
        if route_diff > balancing_percent:
            return True
    return False


class RouteBalancingHelper(BaseImproveRouteProcess):
    """
    Service that make routes more balanced by route time.
    Move point from longer route to shorter route.
    """

    def __init__(self, balancing_percent, routes: RoutesManager, context: BaseAssignmentContext,
                 routing_manager: pywrapcp.RoutingIndexManager):
        super().__init__(context, routing_manager)
        self._balancing_percent = balancing_percent
        self._routes: RoutesManager = routes
        self.need_rebalance = False

    def prepare(self):
        self.need_rebalance = need_rebalance(self._balancing_percent, self._routes)

    def process(self):
        count, max_count = 0, len(self.context.vehicles) * 2
        while self.need_rebalance and count < max_count:
            count += 1
            rebalanced = self._rebalance_routes()
            if not rebalanced:
                return
            self.prepare()

    def _rebalance_routes(self):
        rebalance_happened = 0
        result_routes = self._move_point_from_longest_route(self._routes.longest_route)
        if result_routes:
            self._routes.rewrite_routes(*result_routes)
            rebalance_happened += 1

        result_routes = self._move_point_to_shortest_route(self._routes.fastest_route)
        if result_routes:
            self._routes.rewrite_routes(*result_routes)
            rebalance_happened += 1

        return rebalance_happened > 0

    def _move_point_from_longest_route(self, route_from: Route):
        result_routes, closest_time = None, self._max_time_on_route(route_from, default_value=1000000)
        other_routes = list(self._routes.list_routes(exclude=(route_from,)))
        for route_to in sorted(other_routes, key=attrgetter('get_time_left'), reverse=True):
            move_point_result = self._move_point(route_from, route_to, closest_time)
            if move_point_result is not None:
                result_routes, closest_time = move_point_result
        return result_routes

    def _move_point_to_shortest_route(self, route_to: Route):
        result_routes, closest_time = None, self._max_time_on_route(route_to, default_value=1000000)
        other_routes = list(self._routes.list_routes(exclude=(route_to,)))
        for route_from in sorted(other_routes, key=attrgetter('get_time_left')):
            move_point_result = self._move_point(route_from, route_to, closest_time)
            if move_point_result is not None:
                result_routes, closest_time = move_point_result
        return result_routes

    def _move_point(self, route_from: Route, route_to: Route, closest_time: int) \
            -> Optional[Tuple[Iterable[Route], int]]:
        """
        Finds point from `route_from` that can be moved to `route_to`

        :param closest_time: Current minimal time between points.
        :return: If possible then return copies of updated routes and time between points.
        None in case can't move any point.
        """

        if not route_to.can_extend_used_capacity(from_route=route_from):
            return
        if not route_to.can_extend_used_time(from_route=route_from):
            return

        times_between_points = []
        time_left_on_route = route_to.get_time_left
        prev_point_route_to = None
        for point_route_to in route_to.delivery_job_points:
            for point_route_from in route_from.delivery_job_points:
                time_between = self._time_between_points(point_route_from, point_route_to, route_to)
                if time_between >= closest_time:
                    continue
                if prev_point_route_to is not None:
                    diff = self._time_between_points(prev_point_route_to, point_route_from, route_to) \
                           + time_between - self._time_between_points(prev_point_route_to, point_route_to, route_to)
                    if diff > time_left_on_route:
                        continue
                times_between_points.append((time_between, point_route_from, point_route_to))
            prev_point_route_to = point_route_to

        times_between_points = sorted(times_between_points, key=itemgetter(0))
        for i, (time_between, point_a, point_b) in enumerate(times_between_points):
            pre_result_routes = self._try_move_point(point_a, point_b, route_from, route_to)
            if pre_result_routes is not None:
                return pre_result_routes, time_between

    @staticmethod
    def _try_move_point(moved_point: RoutePointIndex, near_point: RoutePointIndex, route_from: Route, route_to: Route) \
            -> Optional[Iterable[Route]]:
        """
        Move `moved_point` from `route_from` to `route_to`. Try to place it near `near_point`.

        :return: If possible then returns copies of updated `route_from` and `route_to` routes.
        None in case not possible to move point.
        """

        if not route_to.can_add_delivery(PointToReassign([], moved_point)):
            return
        route_from_copy = copy.copy(route_from)
        point_for_reassign = route_from_copy.take_point_for_reassign(moved_point)
        if not point_for_reassign:
            return
        if not route_from_copy.is_valid():
            return

        routes_to_select = []
        route_to_copy_after = copy.copy(route_to)
        route_to_copy_after.add_point(point_for_reassign, near_point, after=True)
        if route_to_copy_after.is_valid():
            if route_from.get_route_duration >= route_to_copy_after.get_route_duration:
                routes_to_select.append(route_to_copy_after)
        route_to_copy_pre = copy.copy(route_to)
        route_to_copy_pre.add_point(point_for_reassign, near_point, after=False)
        if route_to_copy_pre.is_valid():
            if route_from.get_route_duration >= route_to_copy_pre.get_route_duration:
                routes_to_select.append(route_to_copy_pre)

        if not routes_to_select:
            return
        return route_from_copy, sorted(routes_to_select, key=attrgetter('get_route_duration'))[0]

    def _max_time_on_route(self, route: Route, default_value):
        times = [self._time_between_points(route.job_points[0], point, route) for point in route.job_points[1:]]
        return max(times) if times else default_value

    def _time_between_points(self, point_a, point_b, route: Route):
        return self.context.TotalTime(
            route.vehicle_idx,
            self.routing_manager.IndexToNode(point_a),
            self.routing_manager.IndexToNode(point_b),
        )
