from ... import constants
from ...context import current_context
from ..base import UseAllDriversAssignmentMixin
from .base import BalancedAssignmentIteratingBase
from .iterating_logic import BalancedIteratingImplementation


class BalancedAssignment(UseAllDriversAssignmentMixin, BalancedAssignmentIteratingBase):
    runner_implementation_class = BalancedIteratingImplementation

    def get_iterations_count(self):
        return len(current_context.vehicles) + 3

    def _drivers_time_windows(self, time_dimension):
        for i, veh in enumerate(current_context.vehicles):
            start_index, end_index = self.routing_model.Start(i), self.routing_model.End(i)
            time_dimension.CumulVar(start_index).SetMin(veh.start_time)
            self.routing_model.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(start_index))
            time_dimension.SetCumulVarSoftUpperBound(end_index, self.temp_vehicle_end_times[i] or veh.end_time,
                                                     constants.PENALTY_DRIVER_OVERTIME)
