import copy
from collections import defaultdict
from operator import itemgetter
from typing import Dict, Iterable, List, Optional, Tuple

from ortools.constraint_solver import pywrapcp

from ...context import BaseAssignmentContext
from .base import BaseImproveRouteProcess
from .routes import PointToReassign, Route, RoutesManager
from .types import ClosenessScore, RoutePointIndex
from .utils import ToRouteCloseness


class RoutesChangeCounter:
    """
    Keep track of route changes. Limit count of changes to no more than 3 consecutive changes.
    Do not allow to make too many changes (it slows down an algorithm)
    """

    CHANGE_COUNT_LIMIT = 3

    def __init__(self):
        self._counter = defaultdict(int)

    def count_changed_source_route(self, route: Route):
        # Increase counter for source route
        self._counter[route.vehicle_idx] += 1

    def count_changed_target_route(self, route: Route):
        # Decrease counter for target route if it already reached changes limit
        if self._counter[route.vehicle_idx] >= self.CHANGE_COUNT_LIMIT:
            self._counter[route.vehicle_idx] -= 1

    def count_skipped_changes_for_route(self, route: Route):
        # If route was skipped from changes then we assume that it reached changes limit
        self._counter[route.vehicle_idx] = self.CHANGE_COUNT_LIMIT

    def is_forbidden_to_change_route(self, route: Route) -> bool:
        return self._counter[route.vehicle_idx] >= self.CHANGE_COUNT_LIMIT

    def clear(self):
        self._counter = defaultdict(int)


class MoveAndSwapRestriction:
    def check(self, source_route: Route, source_route_changed: Route,
              target_route: Route, target_route_changed: Route) -> bool:
        """
        :return: True if move/swap allowed. False in case it is forbidden.
        """
        raise NotImplementedError()


class ChangedRoutesHistoryRestrict(MoveAndSwapRestriction):
    """
    Restrict move and swap points between routes with similar changing.
    Main reason of this restriction is to prevent infinite loop.
    """

    def __init__(self):
        self._history = []

    def register_routes(self, source_route: Route, source_route_changed: Route,
                        target_route: Route, target_route_changed: Route):
        """Register last changes"""
        change_hash = hash((
            source_route.vehicle_idx, tuple(source_route.job_points), tuple(source_route_changed.job_points),
            target_route.vehicle_idx, tuple(target_route.job_points), tuple(target_route_changed.job_points)
        ))
        self._history.append(change_hash)

    def check(self, source_route: Route, source_route_changed: Route,
              target_route: Route, target_route_changed: Route) -> bool:
        change_hash = hash((
            source_route.vehicle_idx, tuple(source_route.job_points), tuple(source_route_changed.job_points),
            target_route.vehicle_idx, tuple(target_route.job_points), tuple(target_route_changed.job_points)
        ))
        return change_hash not in self._history


class PotentialRoutesForPoint:
    __slots__ = ('source_route', 'point_index', 'routes', 'points_for_swap')

    def __init__(self, source_route: Route, point_index: RoutePointIndex, routes: Iterable[Route]):
        self.source_route = source_route
        self.point_index = point_index
        self.routes = routes
        self.points_for_swap: Dict[Route, Iterable[RoutePointIndex]] = {}


class PotentialRoutesForEachRoutePoint:
    """
    Find routes that potentially could fit better for each point of `source_route`.
    So we can try to move point to one of that potential routes.
    """

    FARTHEST_POINTS_COUNT_FOR_PROCESS = 3

    def __init__(self, source_route: Route, routes: RoutesManager):
        self._source_route = source_route
        self._routes = routes

    def find(self):
        result: List[PotentialRoutesForPoint] = []
        points_to_process = self._find_farthest_points()
        for point_index, source_route_closeness_score in points_to_process:
            routes_closer_than_source_route = self._get_routes_closer_than_source_route(
                point_index, source_route_closeness_score
            )
            if not routes_closer_than_source_route:
                continue
            routes = [
                self._routes[to_route_similarity.vehicle_idx]
                for to_route_similarity in routes_closer_than_source_route
            ]
            result.append(PotentialRoutesForPoint(self._source_route, point_index, routes))
        return result

    def _get_routes_closer_than_source_route(self, point_index: RoutePointIndex,
                                             source_route_closeness_score: ClosenessScore) -> List[ToRouteCloseness]:
        closeness_scores_to_another_routes = [
            ToRouteCloseness(
                route.vehicle_idx, route.calculate_point_closeness_score(point_index)
            ) for route in self._routes.list_routes(exclude=(self._source_route,))
        ]
        return list(filter(
            lambda x: x.closeness_score < source_route_closeness_score,
            closeness_scores_to_another_routes
        ))

    def _find_farthest_points(self) -> List[Tuple[RoutePointIndex, ClosenessScore]]:
        point_scores: List[Tuple[RoutePointIndex, ClosenessScore]] = [
            (delivery_point_index, self._source_route.calculate_point_closeness_score(delivery_point_index))
            for delivery_point_index in self._source_route.delivery_job_points
        ]
        point_scores = sorted(point_scores, key=itemgetter(1), reverse=True)
        return point_scores[:self.FARTHEST_POINTS_COUNT_FOR_PROCESS]


class PotentialSwapPointsForEachRoutePoint:
    """
    Find points on potential routes that could be moved to `source_route`.
    So we can try to swap points between routes.
    """

    CLOSEST_TARGET_ROUTE_POINTS_COUNT = 5

    def find(self, potential_routes: List[PotentialRoutesForPoint]):
        for potential_routes_data in potential_routes:
            for route in potential_routes_data.routes:
                closeness_score_limit = route.calculate_point_closeness_score(potential_routes_data.point_index)
                route_points_for_potential_swap = self._get_closest_points_from_target_route(
                    potential_routes_data.source_route, route, closeness_score_limit
                )
                potential_routes_data.points_for_swap[route] = route_points_for_potential_swap
        return potential_routes

    def _get_closest_points_from_target_route(self, source_route: Route, target_route: Route,
                                              closeness_score_limit: ClosenessScore) -> List[RoutePointIndex]:
        point_scores: List[Tuple[RoutePointIndex, ClosenessScore]] = [
            (route_point_index, source_route.calculate_point_closeness_score(route_point_index))
            for route_point_index in target_route.delivery_job_points
        ]
        point_scores = sorted(
            filter(lambda x: x[1] < closeness_score_limit, point_scores),
            key=itemgetter(1)
        )
        return list(map(itemgetter(0), point_scores[:self.CLOSEST_TARGET_ROUTE_POINTS_COUNT]))


class MoveAndSwapPointsResult:
    def __init__(self, source_route: Route, target_route: Route,
                 changed_source_route: Route, changed_target_route: Route):
        self.source_route = source_route
        self.target_route = target_route
        self.changed_source_route = changed_source_route
        self.changed_target_route = changed_target_route
        self.diff = changed_source_route.get_route_duration + changed_target_route.get_route_duration \
            - source_route.get_route_duration - target_route.get_route_duration


class MoveAndSwapPointsOnRoutes:
    """
    This service moves and swaps points between routes.
    Routes and points chosen so it could be potentially decrease routes time.
    Service choose best possible improvement.
    """

    def __init__(self, restrictions: Iterable[MoveAndSwapRestriction]):
        self._restrictions = restrictions

    def process(self, potential_routes: List[PotentialRoutesForPoint]) -> Optional[Tuple[Route]]:
        # Start value equals to 0 because we should not allow changes without improving.
        # Trying not to stuck into infinite loop.
        best_value, best_routes = 0, None
        for potential_routes_data in potential_routes:
            for potential_route in potential_routes_data.routes:
                if not potential_route.can_add_delivery(PointToReassign([], potential_routes_data.point_index)):
                    continue
                move_result = self._try_move_point(
                    potential_routes_data.source_route, potential_routes_data.point_index,
                    potential_route
                )
                if move_result and move_result.diff < best_value:
                    best_value = move_result.diff
                    best_routes = (move_result.changed_source_route, move_result.changed_target_route)

                for potential_swap_point in potential_routes_data.points_for_swap[potential_route]:
                    swap_point_reassign = PointToReassign([], potential_swap_point)
                    if not potential_routes_data.source_route.can_add_delivery(swap_point_reassign):
                        continue
                    swap_result = self._try_swap_points(
                        potential_routes_data.source_route, potential_routes_data.point_index,
                        potential_route, potential_swap_point
                    )
                    if swap_result and swap_result.diff < best_value:
                        best_value = swap_result.diff
                        best_routes = (swap_result.changed_source_route, swap_result.changed_target_route)

        return best_routes

    def _try_move_point(self, source_route: Route, moved_point: RoutePointIndex, target_route: Route) \
            -> Optional[MoveAndSwapPointsResult]:
        source_route_copy = copy.copy(source_route)
        moved_point_for_reassign = source_route_copy.take_point_for_reassign(moved_point)
        if not moved_point_for_reassign or not source_route_copy.is_valid():
            return
        best_target_route = target_route.find_best_place(moved_point_for_reassign, None)
        if best_target_route \
                and self._check_restrictions(source_route, source_route_copy, target_route, best_target_route):
            return MoveAndSwapPointsResult(source_route, target_route, source_route_copy, best_target_route)

    def _try_swap_points(self, source_route: Route, moved_point: RoutePointIndex,
                         target_route: Route, point_for_swap: RoutePointIndex) -> Optional[MoveAndSwapPointsResult]:
        source_route_copy = copy.copy(source_route)
        moved_point_for_reassign = source_route_copy.take_point_for_reassign(moved_point)
        if not moved_point_for_reassign or not source_route_copy.is_valid():
            return
        target_route_copy = copy.copy(target_route)
        swap_point_for_reassign = target_route_copy.take_point_for_reassign(point_for_swap)
        if not swap_point_for_reassign or not target_route_copy.is_valid():
            return
        best_source_route = source_route_copy.find_best_place(swap_point_for_reassign, None)
        if not best_source_route:
            return
        best_target_route = target_route_copy.find_best_place(moved_point_for_reassign, None)
        if best_target_route \
                and self._check_restrictions(source_route, best_source_route, target_route, best_target_route):
            return MoveAndSwapPointsResult(source_route, target_route, best_source_route, best_target_route)

    def _check_restrictions(self, source_route: Route, source_route_changed: Route,
                            target_route: Route, target_route_changed: Route):
        for restriction in self._restrictions:
            if not restriction.check(source_route, source_route_changed, target_route, target_route_changed):
                return False
        return True


class MoveAndSwapPointsHelper(BaseImproveRouteProcess):
    """
    Service moves/swaps points between routes.
    Takes in consideration closeness score of point to other points of route.
    """

    def __init__(self, routes: RoutesManager, context: BaseAssignmentContext,
                 routing_manager: pywrapcp.RoutingIndexManager):
        super().__init__(context, routing_manager)
        self._routes = routes
        self._routes_change_counter = RoutesChangeCounter()
        self._change_history_restriction = ChangedRoutesHistoryRestrict()

    def process(self):
        should_continue = True
        self._routes_change_counter.clear()
        while should_continue:
            should_continue = False
            updated_routes = self._find_routes_for_update()
            if updated_routes is not None:
                should_continue = True
                self._routes.rewrite_routes(*updated_routes)

    def _find_routes_for_update(self) -> Optional[Tuple[Route]]:
        for source_route in self._routes.list_routes():
            if self._routes_change_counter.is_forbidden_to_change_route(source_route):
                continue
            routes_result = self._try_move_points_from_route(source_route)
            if routes_result is not None:
                self._routes_change_counter.count_changed_source_route(routes_result[0])
                self._routes_change_counter.count_changed_target_route(routes_result[1])
                self._change_history_restriction.register_routes(
                    self._routes[routes_result[0].vehicle_idx], routes_result[0],
                    self._routes[routes_result[1].vehicle_idx], routes_result[1]
                )
                return routes_result
            self._routes_change_counter.count_skipped_changes_for_route(source_route)

    def _try_move_points_from_route(self, source_route: Route) -> Optional[Tuple[Route]]:
        potential_routes = PotentialRoutesForEachRoutePoint(source_route, self._routes).find()
        potential_routes = PotentialSwapPointsForEachRoutePoint().find(potential_routes)
        return MoveAndSwapPointsOnRoutes((self._change_history_restriction,)).process(potential_routes)


class SwapFullRouteHelper(BaseImproveRouteProcess):
    """
    Service swaps full route (pickups and deliveries) between drivers to minimize time.
    It could be helpful when drivers starts/ends from different hubs.
    Some jobs could be closer to Hub A, but some to Hub B.
    """

    def __init__(self, routes: RoutesManager, context: BaseAssignmentContext,
                 routing_manager: pywrapcp.RoutingIndexManager):
        super().__init__(context, routing_manager)
        self._routes = routes

    def process(self):
        should_continue = True
        while should_continue:
            should_continue = False
            result_routes = self._find_routes_for_update()
            if result_routes is not None:
                should_continue = True
                self._routes.rewrite_routes(*result_routes)

    def _find_routes_for_update(self) -> Optional[Iterable[Route]]:
        for route_a in self._routes.list_routes():
            for route_b in self._routes.list_routes(exclude=(route_a,)):
                result_routes = self._try_swap(route_a, route_b)
                if result_routes is not None:
                    return result_routes

    @staticmethod
    def _try_swap(route_a, route_b) -> Optional[Iterable[Route]]:
        route_a_copy = copy.copy(route_a)
        route_a_copy.job_points = route_b.job_points
        if not route_a_copy.is_fully_valid():
            return
        route_b_copy = copy.copy(route_b)
        route_b_copy.job_points = route_a.job_points
        if not route_b_copy.is_fully_valid():
            return
        if route_a.get_route_duration + route_b.get_route_duration \
                > route_a_copy.get_route_duration + route_b_copy.get_route_duration:
            return route_a_copy, route_b_copy
