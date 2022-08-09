from typing import Dict, List, Optional

from ortools.constraint_solver import pywrapcp

from route_optimisation.engine.ortools.context import BaseAssignmentContext
from route_optimisation.engine.ortools.helper_classes import Delivery

from ... import constants
from ..services.routes import OrToolsManualBreakInDriverRoute
from ..services.routes import Route as RouteNew
from ..services.types import RoutePointIndex


class PointToReassign:
    def __init__(self, pickups_indices, delivery_index):
        self.pickups_indices: List[int] = pickups_indices
        self.delivery_index: int = delivery_index


class Route:
    def __init__(self, vehicle_idx, job_points):
        self.vehicle_idx: int = vehicle_idx
        self.job_points: List[int] = job_points

    def get_route_finish_time(self, context, routing_manager):
        vehicle = context.vehicles[self.vehicle_idx]
        if not vehicle.breaks:
            return self._calc_finish_time_no_breaks(context, routing_manager)

        route_obj = RouteNew(
            self.vehicle_idx, list(map(RoutePointIndex, self.job_points)),
            context, routing_manager, None
        )
        route_time_with_breaks = OrToolsManualBreakInDriverRoute(route_obj, context, routing_manager)
        result = route_time_with_breaks.get_time_finish()
        if result is not None:
            return result
        return constants.TWO_DAYS

    def _calc_finish_time_no_breaks(self, context, routing_manager):
        start_depot_node = context.start_locations[self.vehicle_idx]
        end_depot_node = context.end_locations[self.vehicle_idx]
        prev_point_node = start_depot_node
        cumul_time = context.vehicles[self.vehicle_idx].start_time
        for point_index in self.job_points:
            point_node = routing_manager.IndexToNode(point_index)
            cumul_time += context.TotalTimeWithService(self.vehicle_idx, prev_point_node, point_node)
            prev_point_node = point_node
        cumul_time += context.TotalTimeWithService(self.vehicle_idx, prev_point_node, end_depot_node)
        return cumul_time

    def pop(self, index=-1):
        return self.job_points.pop(index)

    def remove_point(self, point):
        self.job_points.pop(self.job_points.index(point))

    def add_point(self, point: PointToReassign):
        """
        Simply add point to route: pickups on first place, delivery at the end of route.
        """
        self.job_points = point.pickups_indices + self.job_points
        self.job_points.append(point.delivery_index)

    def get_time_left(self, context, routing_manager):
        finish_time = self.get_route_finish_time(context, routing_manager)
        max_time = context.vehicles[self.vehicle_idx].end_time
        return max_time - finish_time

    def is_route_time_good(self, context, routing_manager):
        return self.get_time_left(context, routing_manager) >= 0

    def can_add_delivery(self, point: PointToReassign, context: BaseAssignmentContext,
                         routing_manager: pywrapcp.RoutingIndexManager):
        vehicle = context.vehicles[self.vehicle_idx]
        delivery_point_node = routing_manager.IndexToNode(point.delivery_index)
        delivery_point = context.points[delivery_point_node]
        return delivery_point.check_vehicle_skills_set(vehicle) and delivery_point.is_allowed_vehicle(vehicle)


class ReassignPointsManager:
    def __init__(self, assignment_context: BaseAssignmentContext, routing_manager: pywrapcp.RoutingIndexManager):
        self.context = assignment_context
        self.routing_manager = routing_manager
        self.skipped_found = False
        self.points_to_reassign = []

    @property
    def has_points(self):
        return bool(self.points_to_reassign)

    def find_skipped_points(self, assigned_routes):
        assert not self.skipped_found
        skipped_deliveries_nodes = {i for i, point in enumerate(self.context.points) if isinstance(point, Delivery)}
        for route in assigned_routes:
            skipped_deliveries_nodes.difference_update(set(map(self.routing_manager.IndexToNode, route)))
        skipped = []
        for delivery_node in skipped_deliveries_nodes:
            delivery_index = self.routing_manager.NodeToIndex(delivery_node)
            pickup_indices = list(self._get_related_pickups_indices(delivery_index))
            skipped.append(PointToReassign(pickup_indices, delivery_index))
        self.points_to_reassign.extend(skipped)
        self.skipped_found = True

    def take_point_for_reassign(self, route):
        """
        Take last delivery point and related pickups from route
        """
        delivery_point_index = route.pop()
        pickups_indices = list(self._get_related_pickups_indices(delivery_point_index))
        for deleted_pickup_point_index in pickups_indices:
            route.remove_point(deleted_pickup_point_index)
        self.points_to_reassign.append(PointToReassign(pickups_indices, delivery_point_index))

    def _get_related_pickups_indices(self, delivery_point_index):
        delivery_point_node = self.routing_manager.IndexToNode(delivery_point_index)
        delivery_point = self.context.points[delivery_point_node]
        for pickup, delivery in self.context.pickup_delivery:
            if delivery_point.unique_id == delivery.unique_id:
                yield self.routing_manager.NodeToIndex(self.context.points_node_id_map[pickup.unique_id])


class RoutePointsReassignHelper:
    def __init__(self, assignment_context: BaseAssignmentContext, routing_manager: pywrapcp.RoutingIndexManager):
        self.context = assignment_context
        self.routing_manager = routing_manager
        self.good_routes: Optional[Dict[int, Route]] = None
        self.reassign_points: Optional[ReassignPointsManager] = None
        self.log = []

    def clean_routes(self, routes):
        self.good_routes: Dict[int, Route] = {}
        self.reassign_points = ReassignPointsManager(self.context, self.routing_manager)
        self.reassign_points.find_skipped_points(routes)
        for vehicle_idx, route in enumerate(routes):
            route = Route(vehicle_idx, route)
            while not route.is_route_time_good(self.context, self.routing_manager):
                self.reassign_points.take_point_for_reassign(route)
            self.good_routes[vehicle_idx] = route

    def fill_routes(self):
        self.log.append('Points to reassign(before): {}'.format(len(self.reassign_points.points_to_reassign)))
        for vehicle_idx, route in self.good_routes.items():
            if self.reassign_points.has_points:
                self._try_add_points_to_route(route)
        self.log.append('Points to reassign(after): {}'.format(len(self.reassign_points.points_to_reassign)))

    def _try_add_points_to_route(self, route: Route):
        while self.reassign_points.has_points:
            best_index_to_add_to_route = self._find_best_point_to_insert(route)
            if best_index_to_add_to_route is None:
                return
            point_to_reassign = self.reassign_points.points_to_reassign.pop(best_index_to_add_to_route)
            route.add_point(point_to_reassign)
        return

    def _find_best_point_to_insert(self, route: Route):
        # TODO: check for capacity
        best_index, max_time_left = None, -1
        for i in range(len(self.reassign_points.points_to_reassign)):
            point_to_reassign = self.reassign_points.points_to_reassign[i]
            route_copy = Route(route.vehicle_idx, list(route.job_points))
            if not route_copy.can_add_delivery(point_to_reassign, self.context, self.routing_manager):
                continue
            route_copy.add_point(point_to_reassign)
            time_left_on_route = route_copy.get_time_left(self.context, self.routing_manager)
            if time_left_on_route < 0:
                continue
            if time_left_on_route > max_time_left:
                best_index, max_time_left = i, time_left_on_route
        return best_index

    @property
    def routes(self):
        return [self.good_routes[i].job_points for i in range(len(self.context.vehicles))]
