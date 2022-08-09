from route_optimisation.engine.errors import NoSolutionFoundError
from route_optimisation.engine.ortools.assignment.base import AssignmentBase

from .parameters import EngineParameters
from .result import AssignmentResult


class AlgorithmBase:
    def assign(self, params: EngineParameters) -> AssignmentResult:
        assignment = self.optimise()
        if assignment is None:
            raise NoSolutionFoundError('No solution found')
        return assignment.result

    def optimise(self) -> AssignmentBase:
        raise NotImplementedError()

    def clean(self):
        pass
