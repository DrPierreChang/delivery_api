from abc import ABC
from operator import attrgetter, itemgetter
from typing import Dict, List

from ortools.constraint_solver import pywrapcp

from ...context import BaseAssignmentContext
from .base import BaseImproveRouteProcess
from .points_reassign import ReassignPointsManager
from .routes import Route, RoutesManager
from .utils import PointsRouteCloseness, ToRouteCloseness


class RouteClosenessScoreMetadata:
    """
    Information about closeness of points to its route and other routes
    """

    def __init__(self, route: Route, routes: RoutesManager, nearby_coefficient: float):
        self._route = route
        self._routes = routes
        self._nearby_coefficient = nearby_coefficient
        self.points_metadata: List[PointsRouteCloseness] = []
        self._calc()

    def _calc(self):
        for delivery_point_index in self._route.delivery_job_points:
            point_metadata = self._calc_point_metadata(delivery_point_index)
            if point_metadata.have_another_routes:
                self.points_metadata.append(point_metadata)

    def _calc_point_metadata(self, delivery_point_index):
        # Find closeness of point to its route
        route_closeness_score = self._route.calculate_point_closeness_score(delivery_point_index)
        # Find closeness of point to another routes
        another_routes_scores: List[ToRouteCloseness] = []
        for another_route in self._routes.list_routes(exclude=(self._route,)):
            another_route_closeness_score = another_route.calculate_point_closeness_score(delivery_point_index)
            # Leave only very close routes (much closer then its route)
            if another_route_closeness_score < route_closeness_score / self._nearby_coefficient:
                another_routes_scores.append(
                    ToRouteCloseness(another_route.vehicle_idx, another_route_closeness_score)
                )
        another_routes_scores = sorted(another_routes_scores, key=attrgetter('closeness_score'))
        return PointsRouteCloseness(delivery_point_index, route_closeness_score, another_routes_scores)


class RoutesClosenessMetadata:
    def __init__(self):
        self.data: Dict[int, RouteClosenessScoreMetadata] = {}

    def prepare(self, routes: RoutesManager, nearby_coefficient):
        for route in routes.list_routes():
            self.data[route.vehicle_idx] = RouteClosenessScoreMetadata(route, routes, nearby_coefficient)


class NearbyReassignBase(BaseImproveRouteProcess, ABC):
    def __init__(self, routes: RoutesManager, reassign_points: ReassignPointsManager,
                 context: BaseAssignmentContext, routing_manager: pywrapcp.RoutingIndexManager):
        super().__init__(context, routing_manager)
        self._routes = routes
        self._reassign_points = reassign_points

    def get_nearby_metadata(self, nearby_coefficient=None) -> RoutesClosenessMetadata:
        nearby_coefficient = nearby_coefficient or 1.3
        nearby_metadata = RoutesClosenessMetadata()
        nearby_metadata.prepare(self._routes, nearby_coefficient)
        return nearby_metadata


class NearbyReassignPrepareHelper(NearbyReassignBase):
    def __init__(self, routes: RoutesManager, reassign_points: ReassignPointsManager,
                 context: BaseAssignmentContext, routing_manager: pywrapcp.RoutingIndexManager):
        super().__init__(routes, reassign_points, context, routing_manager)
        self.have_faraway_points = False

    def process(self, *args, **kwargs):
        nearby_metadata = self.get_nearby_metadata()
        for meta in nearby_metadata.data.values():
            for point_metadata in meta.points_metadata:
                if point_metadata.have_another_routes:
                    self.have_faraway_points = True
                    return


class UnassignNonNearby(NearbyReassignBase):
    """
    Removes points from route. Remove points that placed far from other points of the route.
    """

    def process(self, nearby_coefficient=1.25):
        for route in self._routes.list_routes():
            points_closeness_scores = [
                (route.calculate_point_closeness_score(point), point)
                for point in route.delivery_job_points
            ]
            if not points_closeness_scores:
                continue
            points_closeness_scores = sorted(points_closeness_scores, key=itemgetter(0))
            avg_score = sum(map(itemgetter(0), points_closeness_scores)) / len(points_closeness_scores)
            max_allowed_score = avg_score * nearby_coefficient
            far_points = filter(lambda x: x[0] > max_allowed_score, points_closeness_scores)
            for _, point in far_points:
                self._reassign_points.take_point_for_reassign(route, point)


class NearbyReassignByClosenessDiff(NearbyReassignBase):
    """
    This service reassign points from one route to another by closeness score.
    Firstly, service unassign all faraway points.
    Secondly, service assigns these points to new routes.
    """

    def process(self, nearby_coefficient, *args, **kwargs):
        nearby_metadata = self.get_nearby_metadata(nearby_coefficient=nearby_coefficient)
        self._take_faraway_points(nearby_metadata)
        self._add_points_to_new_routes(nearby_metadata)

    def _take_faraway_points(self, nearby_metadata: RoutesClosenessMetadata):
        for vehicle_idx, meta in nearby_metadata.data.items():
            for point_metadata in meta.points_metadata:
                self._reassign_points.take_point_for_reassign(
                    self._routes[vehicle_idx], point_metadata.delivery_point_index
                )

    def _add_points_to_new_routes(self, nearby_metadata: RoutesClosenessMetadata):
        should_continue = True
        while should_continue:
            should_continue = False
            for route_idx, route_closeness_metadata in nearby_metadata.data.items():
                if not route_closeness_metadata.points_metadata:
                    continue
                if len(list(self._routes[route_idx].delivery_job_points)) < 2:
                    continue
                result = self._add_point_to_best_available_route(
                    route_idx, route_closeness_metadata.points_metadata
                )
                if result:
                    should_continue = True
                    updated_route, added_delivery_point_index = result
                    self._save_results(updated_route, added_delivery_point_index)

    def _add_point_to_best_available_route(self, route_idx_from, points_metadata: List[PointsRouteCloseness]):
        best_route_to, best_score_diff, best_metadata_index, delivery_point_index = None, -1, None, None
        for meta_index, point_metadata in enumerate(points_metadata):
            for another_route_score in point_metadata.another_routes_scores:
                diff = point_metadata.closeness_score - another_route_score.closeness_score
                if diff <= best_score_diff:
                    continue
                route_to = self._find_best_place(
                    point_metadata.delivery_point_index, route_idx_from, another_route_score.vehicle_idx)
                if route_to is None:
                    continue
                best_route_to = route_to
                best_score_diff = diff
                best_metadata_index = meta_index
                delivery_point_index = point_metadata.delivery_point_index
        if best_route_to:
            points_metadata.pop(best_metadata_index)
            return best_route_to, delivery_point_index

    def _find_best_place(self, point_index, route_idx_from, route_idx_to):
        route_to = self._routes[route_idx_to]
        route_from = self._routes[route_idx_from]
        point_for_reassign = self._reassign_points.get(point_index)
        if not point_for_reassign:
            return
        return route_to.find_best_place(point_for_reassign, route_from.get_route_duration)

    def _save_results(self, updated_route, added_delivery_point_index):
        # Remove point from points_to_reassign
        reassign_point_index_to_pop = -1
        for i, reassign in enumerate(self._reassign_points.points_to_reassign):
            if reassign.delivery_index == added_delivery_point_index:
                reassign_point_index_to_pop = i
                break
        self._reassign_points.points_to_reassign.pop(reassign_point_index_to_pop)
        # Remove point from active points_to_reassign
        active_reassign_point_index_to_pop = -1
        for i, reassign in enumerate(self._reassign_points.active_points_to_reassign):
            if reassign.delivery_index == added_delivery_point_index:
                active_reassign_point_index_to_pop = i
                break
        self._reassign_points.active_points_to_reassign.pop(active_reassign_point_index_to_pop)
        # Update routes
        self._routes.rewrite_routes(updated_route)


class NearbyAssignByCloseness(NearbyReassignBase):
    """
    This service appends points(from list to reassign) to route by closeness
    """

    def process(self):
        should_continue = True
        while self._reassign_points.has_points and should_continue:
            should_continue = False
            result = self._find_point_and_route_to_insert()
            if not result:
                continue
            should_continue = True
            best_point_to_reassign_index, updated_route = result
            self._save_result(best_point_to_reassign_index, updated_route)

    def _find_point_and_route_to_insert(self):
        best_index, best_closeness_score, best_route_to = None, 10000000, None
        for index, point_to_reassign in enumerate(self._reassign_points.active_points_to_reassign):
            closeness_to_routes = [
                (route.calculate_point_closeness_score(point_to_reassign.delivery_index), route)
                for route in self._routes.list_routes()
                if route.can_add_delivery(point_to_reassign)
            ]
            closeness_to_routes = sorted(
                filter(lambda x: x[0] < best_closeness_score, closeness_to_routes),
                key=itemgetter(0)
            )
            for closeness_score, route_to in closeness_to_routes:
                updated_route_to = route_to.find_best_place(point_to_reassign, None)
                if updated_route_to:
                    best_closeness_score = closeness_score
                    best_index = index
                    best_route_to = updated_route_to
                    break
        if best_index is not None:
            return best_index, best_route_to

    def _save_result(self, best_point_to_reassign_index, updated_route):
        point_to_reassign = self._reassign_points.active_points_to_reassign.pop(best_point_to_reassign_index)
        self._reassign_points.points_to_reassign.pop(
            self._reassign_points.points_to_reassign.index(point_to_reassign))
        self._routes.rewrite_routes(updated_route)
