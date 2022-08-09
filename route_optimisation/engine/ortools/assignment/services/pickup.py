import copy
import itertools
from operator import itemgetter
from typing import Dict, Iterable, List, Optional

from ortools.constraint_solver import pywrapcp

from ...context import BaseAssignmentContext
from ...helper_classes import Pickup
from .base import BaseImproveRouteProcess
from .routes import Route, RoutesManager
from .types import RoutePointIndex


class PickupRationalPosition(BaseImproveRouteProcess):
    def __init__(self, routes: RoutesManager, context: BaseAssignmentContext,
                 routing_manager: pywrapcp.RoutingIndexManager):
        super().__init__(context, routing_manager)
        self._routes = routes

    def process(self):
        if not self.context.has_pickup:
            return
        self._place_same_pickups_near()
        self._rational_position_reorder_pickups()

    def _rational_position_reorder_pickups(self):
        """
        Reorder pickups on route to minimize used time.
        """
        updated_routes = []
        for route in self._routes.list_routes():
            route_copy = self._rational_position_reorder_pickups_on_route(route)
            if route_copy:
                updated_routes.append(route_copy)
        self._routes.rewrite_routes(*updated_routes)

    def _rational_position_reorder_pickups_on_route(self, route):
        pickups_for_reorder: Dict[str, List[RoutePointIndex]] = {}
        job_points: List[RoutePointIndex] = []
        previous_point_index: Optional[RoutePointIndex] = None
        for point_index in route.job_points:
            point = self.context.points[self.routing_manager.IndexToNode(point_index)]
            if isinstance(point, Pickup):
                if point.latlng_location not in pickups_for_reorder:
                    pickups_for_reorder[point.latlng_location] = []
                pickups_for_reorder[point.latlng_location].append(point_index)
            else:
                if pickups_for_reorder:
                    ordered_pickup_indexes = self._get_pickups_ordered(
                        route, list(map(itemgetter(0), pickups_for_reorder.values())),
                        previous_point_index=previous_point_index,
                        next_point_index=point_index
                    )
                    for pickup_index in ordered_pickup_indexes:
                        pickup_point = self.context.points[self.routing_manager.IndexToNode(pickup_index)]
                        job_points.extend(pickups_for_reorder[pickup_point.latlng_location])
                    pickups_for_reorder = {}
                job_points.append(point_index)
                previous_point_index = point_index
        if job_points == route.job_points:
            return
        route_copy = copy.copy(route)
        route_copy.job_points = job_points
        if route_copy.is_fully_valid():
            return route_copy

    def _get_pickups_ordered(self, route: Route, pickups_indexes: List[RoutePointIndex],
                             previous_point_index: Optional[RoutePointIndex],
                             next_point_index: RoutePointIndex) -> Iterable[RoutePointIndex]:
        previous_point_node = self.routing_manager.IndexToNode(previous_point_index) \
            if previous_point_index is not None \
            else self.context.start_locations[route.vehicle_idx]
        last_point_node = self.routing_manager.IndexToNode(next_point_index)

        i = 0
        result = []
        while i < len(pickups_indexes):
            indexes_for_permute = pickups_indexes[i:i+4]
            values = []
            to_node = last_point_node if i+4 >= len(pickups_indexes) \
                else self.routing_manager.IndexToNode(pickups_indexes[i+4])
            from_node = self.routing_manager.IndexToNode(result[-1]) if len(result) > 0 else previous_point_node
            for indexes in itertools.permutations(indexes_for_permute):
                nodes = [from_node] + list(map(self.routing_manager.IndexToNode, indexes)) + [to_node]
                sum_time = sum(self.context.TotalTime(route.vehicle_idx, node_from, node_to)
                               for node_from, node_to in zip(nodes[:-1], nodes[1:]))
                values.append((sum_time, indexes))
            result.extend(sorted(values, key=itemgetter(0))[0][1])
            i += 4
        return result

    def _place_same_pickups_near(self):
        """
        In case pickups from same location are placed in sequence not one by one.
        Example:
        Hub -> PickupA(location1) -> PickupB(location2) -> PickupC(location1) -> ... other points.
        Should be like:
        Hub -> PickupA(location1) -> PickupC(location1) -> PickupB(location2) -> ... other points.
        """
        updated_routes = []
        for route in self._routes.list_routes():
            route_copy = self._place_same_pickups_near_on_route(route)
            if route_copy:
                updated_routes.append(route_copy)
        self._routes.rewrite_routes(*updated_routes)

    def _place_same_pickups_near_on_route(self, route):
        pickups = {}
        job_points = []
        for point_index in route.job_points:
            point = self.context.points[self.routing_manager.IndexToNode(point_index)]
            if not isinstance(point, Pickup):
                job_points.append(point_index)
                continue
            if point.latlng_location not in pickups:
                pickups[point.latlng_location] = point_index
                job_points.append(point_index)
            else:
                job_points.insert(job_points.index(pickups[point.latlng_location]), point_index)
        if job_points == route.job_points:
            return
        route_copy = copy.copy(route)
        route_copy.job_points = job_points
        if route_copy.is_fully_valid():
            return route_copy
