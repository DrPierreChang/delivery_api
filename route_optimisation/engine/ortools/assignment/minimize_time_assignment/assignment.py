from ... import constants
from ...context import current_context
from ..iterating_assignment import IteratingAssignment
from .iterating_logic import MinimizeTimeIteratingImplementation


class MinimizeTimeAssignment(IteratingAssignment):
    runner_implementation_class = MinimizeTimeIteratingImplementation

    def get_iterations_count(self):
        return len(current_context.vehicles) + 3

    def _drivers_time_windows(self, time_dimension):
        for i, veh in enumerate(current_context.vehicles):
            start_index, end_index = self.routing_model.Start(i), self.routing_model.End(i)
            time_dimension.CumulVar(start_index).SetMin(veh.start_time)
            self.routing_model.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(start_index))
            time_dimension.SetCumulVarSoftUpperBound(end_index, veh.end_time, constants.PENALTY_DRIVER_OVERTIME)
