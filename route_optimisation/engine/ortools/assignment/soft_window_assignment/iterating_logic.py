from ortools.constraint_solver import pywrapcp

from route_optimisation.engine.events import event_handler
from route_optimisation.logging import EventType

from ...context import BaseAssignmentContext, current_context
from ..iterating_assignment import IteratingAssignment, IteratingAssignmentImplementation, IteratingServices
from .utils import RoutePointsReassignHelper


class SoftWindowServices(IteratingServices):
    def __init__(self, context: BaseAssignmentContext, routing_manager: pywrapcp.RoutingIndexManager):
        self.reassign_helper = RoutePointsReassignHelper(context, routing_manager)


class SoftWindowIteratingImplementation(IteratingAssignmentImplementation):
    def __init__(self, assignment_instance: IteratingAssignment):
        super().__init__(assignment_instance)
        self.assignment_instance = assignment_instance

    def init_iteration_services(self) -> SoftWindowServices:
        return SoftWindowServices(current_context, self.assignment_instance.routing_manager)

    def init_finish_services(self) -> SoftWindowServices:
        return SoftWindowServices(current_context, self.assignment_instance.routing_manager)

    def on_iteration_start(self, services: SoftWindowServices):
        services.reassign_helper.clean_routes(self.assignment_instance.to_routes())

    def check_break_after_iteration_start(self, services: SoftWindowServices):
        return not services.reassign_helper.reassign_points.has_points

    def do_iteration_logic(self, services: SoftWindowServices):
        services.reassign_helper.fill_routes()

    def after_iteration(self, services: SoftWindowServices):
        msg = 'Before rerun #{}:\nReassign helper log:{}\nAssignment:\n{}'.format(
            self.assignment_instance.current_iteration, '\n'.join(services.reassign_helper.log),
            str(self.assignment_instance)
        )
        event_handler.dev(EventType.OPTIMISATION_PROCESS, msg)

    def setup_assignment_after_iteration(self, services: SoftWindowServices):
        routes = services.reassign_helper.routes
        self.assignment_instance.setup()
        initial_assignment = self.assignment_instance.routing_model.ReadAssignmentFromRoutes(routes, False)
        self.assignment_instance.assignment = self.assignment_instance.routing_model.SolveFromAssignmentWithParameters(
            initial_assignment,
            self.assignment_instance.search_parameters.parameters
        )

    def clean_routes_before_finish(self, services: SoftWindowServices):
        services.reassign_helper.clean_routes(self.assignment_instance.to_routes())

    def setup_assignment_on_finish(self, services: SoftWindowServices):
        routes = services.reassign_helper.routes
        self.assignment_instance.setup()
        self.assignment_instance.assignment = self.assignment_instance.routing_model.ReadAssignmentFromRoutes(
            routes, False
        )
