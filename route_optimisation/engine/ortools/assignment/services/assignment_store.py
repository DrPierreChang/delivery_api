import copy

from .points_reassign import ReassignPointsManager
from .routes import RoutesManager


class MinSkippedAssignmentStore:
    """
    Service to keep latest assigned routes with minimal count of skipped orders and minimal count of skipped drivers.
    Using this service in iteration assignment.
    """

    def __init__(self):
        self.routes = None
        self.points_to_reassign = []
        self.min_skipped_orders = None
        self.max_used_drivers = None

    def process(self, reassign_points: ReassignPointsManager, routes_manager: RoutesManager):
        if self.min_skipped_orders is not None and len(reassign_points.points_to_reassign) > self.min_skipped_orders:
            return
        if self.max_used_drivers is not None and routes_manager.not_empty_routes_count < self.max_used_drivers:
            return
        self.routes = copy.deepcopy(routes_manager.routes)
        self.points_to_reassign = copy.deepcopy(reassign_points.points_to_reassign)
        self.min_skipped_orders = len(reassign_points.points_to_reassign)
        self.max_used_drivers = routes_manager.not_empty_routes_count
