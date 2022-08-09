from abc import ABC

from ...context import current_context
from ..iterating_assignment import IteratingAssignment


class BalancedAssignmentIteratingBase(IteratingAssignment, ABC):
    def __init__(self, search_parameters, route_balancing_allowed_diff, *args, **kwargs):
        super().__init__(search_parameters, *args, **kwargs)
        self.route_balancing_allowed_diff = route_balancing_allowed_diff
        self.temp_vehicle_end_times = [None] * len(current_context.vehicles)
