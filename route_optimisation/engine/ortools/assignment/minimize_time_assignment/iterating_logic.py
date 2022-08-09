import json

from ortools.constraint_solver import pywrapcp

from route_optimisation.engine.events import event_handler
from route_optimisation.logging import EventType

from ...context import BaseAssignmentContext, current_context
from ..iterating_assignment import IteratingAssignment, IteratingAssignmentImplementation, IteratingServices
from ..services import (
    MinSkippedAssignmentStore,
    MoveAndSwapPointsHelper,
    NearbyAssignByCloseness,
    NearbyReassignByClosenessDiff,
    NearbyReassignPrepareHelper,
    PickupRationalPosition,
    PreviousRunStore,
    ReassignPointsManager,
    RoutePointsReassignHelper,
    RoutesManager,
    SimpleTimer,
    SoftAssignmentRoutesCleaner,
    SwapFullRouteHelper,
    UnassignNonNearby,
)


class MinimizeTimeAssignmentServices(IteratingServices):
    def __init__(self, routes, context: BaseAssignmentContext,
                 routing_manager: pywrapcp.RoutingIndexManager, route_find_best_place_cache: dict):
        params = {'context': context, 'routing_manager': routing_manager}
        self.routes_manager = RoutesManager(routes, context, routing_manager,
                                            route_find_best_place_cache, route_can_be_skipped=True)
        self.reassign_points = ReassignPointsManager(**params)
        self.swap_helper = SwapFullRouteHelper(self.routes_manager, **params)
        self.pickup_reassign_helper = PickupRationalPosition(self.routes_manager, **params)
        self.reassign_helper = RoutePointsReassignHelper(self.routes_manager, self.reassign_points, **params)
        self.routes_cleaner = SoftAssignmentRoutesCleaner(self.routes_manager, self.reassign_points)
        self.nearby_by_closeness = NearbyAssignByCloseness(self.routes_manager, self.reassign_points, **params)
        self.nearby_reassign_by_diff = NearbyReassignByClosenessDiff(
            self.routes_manager, self.reassign_points, **params)
        self.nearby_reassign_helper = NearbyReassignPrepareHelper(self.routes_manager, self.reassign_points, **params)
        self.unassign_nearby = UnassignNonNearby(self.routes_manager, self.reassign_points, **params)
        self.point_swap = MoveAndSwapPointsHelper(self.routes_manager, **params)


class MinimizeTimeIteratingImplementation(IteratingAssignmentImplementation):
    def __init__(self, assignment_instance: IteratingAssignment):
        super().__init__(assignment_instance)
        self.assignment_instance = assignment_instance
        self.previous_runs = PreviousRunStore(assignment_instance)
        self.min_skipped_assignment = MinSkippedAssignmentStore()
        self.route_find_best_place_cache = {}

    def check_break_before_iteration(self):
        self.previous_runs.process_changes()
        if self.previous_runs.not_changing:
            event_handler.dev(EventType.OPTIMISATION_PROCESS, 'Time and distance has not changed since last cycle')
            return True

    def log_before_iteration(self):
        self._dump_current_routes()
        msg = 'Before change #{}:\nAssignment:\n{}'.format(
            self.assignment_instance.current_iteration, str(self.assignment_instance)
        )
        event_handler.dev(EventType.OPTIMISATION_PROCESS, msg)

    def init_iteration_services(self) -> MinimizeTimeAssignmentServices:
        return MinimizeTimeAssignmentServices(
            self.assignment_instance.to_routes(),
            current_context,
            self.assignment_instance.routing_manager,
            self.route_find_best_place_cache,
        )

    def init_finish_services(self) -> MinimizeTimeAssignmentServices:
        routes = self.min_skipped_assignment.routes
        if routes is None:
            routes = self.assignment_instance.to_routes()
        return MinimizeTimeAssignmentServices(
            routes,
            current_context,
            self.assignment_instance.routing_manager,
            self.route_find_best_place_cache,
        )

    def on_iteration_start(self, services: MinimizeTimeAssignmentServices):
        services.pickup_reassign_helper.process()
        services.swap_helper.process()
        services.routes_cleaner.process()
        services.nearby_reassign_helper.process()

    def check_break_after_iteration_start(self, services: MinimizeTimeAssignmentServices):
        if not (services.nearby_reassign_helper.have_faraway_points or services.reassign_points.has_points):
            event_handler.dev(
                EventType.OPTIMISATION_PROCESS,
                f'Break cycle. '
                f'nearby_reassign_helper.have_faraway_points: {services.nearby_reassign_helper.have_faraway_points}, '
                f'reassign_points.has_points: {services.reassign_points.has_points}'
            )
            return True

    def do_iteration_logic(self, services: MinimizeTimeAssignmentServices):
        event_messages = [f'[{self.__class__.__name__}]']

        def append_event_message(name, timing):
            event_messages.append('{name}: {timing}'.format(name=name, timing=round(timing, 3)))

        timer = SimpleTimer(on_exit=append_event_message)

        for nearby_coefficient in (1.25, 1.5, 1.75):
            event_messages.append(f'Points to reassign: {len(services.reassign_points.points_to_reassign)}')
            with timer.timeit('unassign_nearby'):
                services.unassign_nearby.process(nearby_coefficient)

            services.reassign_points.activate_points_to_reassign(services.routes_manager)
            event_messages.append(f'Points to reassign: {len(services.reassign_points.points_to_reassign)}')
            with timer.timeit('reassign_helper-1'):
                services.reassign_helper.process()

            event_messages.append(f'Points to reassign: {len(services.reassign_points.points_to_reassign)}')
            with timer.timeit('nearby_by_time'):
                services.nearby_reassign_by_diff.process(nearby_coefficient)

            services.reassign_points.activate_points_to_reassign(services.routes_manager)
            event_messages.append(f'Points to reassign: {len(services.reassign_points.points_to_reassign)}')
            with timer.timeit('nearby_by_score'):
                services.nearby_by_closeness.process()

            services.reassign_points.activate_points_to_reassign(services.routes_manager)
            event_messages.append(f'Points to reassign: {len(services.reassign_points.points_to_reassign)}')
            with timer.timeit('reassign_helper-2'):
                services.reassign_helper.process()

        event_messages.append(f'Points to reassign: {len(services.reassign_points.points_to_reassign)}')
        with timer.timeit('point_swap'):
            services.point_swap.process()
        services.pickup_reassign_helper.process()
        services.swap_helper.process()
        event_messages.append(f'Points to reassign: {len(services.reassign_points.points_to_reassign)}')
        event_handler.dev(EventType.OPTIMISATION_PROCESS, '\n'.join(event_messages))

    def after_iteration(self, services: MinimizeTimeAssignmentServices):
        self.min_skipped_assignment.process(services.reassign_points, services.routes_manager)

    def setup_assignment_after_iteration(self, services: MinimizeTimeAssignmentServices):
        routes = services.routes_manager.routes
        self.assignment_instance.setup()
        self.assignment_instance.assignment = self.assignment_instance.routing_model.ReadAssignmentFromRoutes(
            routes, False
        )
        assert self.assignment_instance.assignment is not None
        msg = 'Before rerun #{}:\nChanged Assignment:\n{}'.format(
            self.assignment_instance.current_iteration, str(self.assignment_instance)
        )
        event_handler.dev(EventType.OPTIMISATION_PROCESS, msg)
        self.assignment_instance.assignment = self.assignment_instance.routing_model.SolveFromAssignmentWithParameters(
            self.assignment_instance.assignment,
            self.assignment_instance.search_parameters.rerun_search_parameters
        )

    def clean_routes_before_finish(self, services: MinimizeTimeAssignmentServices):
        services.routes_cleaner.process()

    def setup_assignment_on_finish(self, services: MinimizeTimeAssignmentServices):
        routes = services.routes_manager.routes
        self.assignment_instance.setup()
        self.assignment_instance.lock_drivers_orders(self.assignment_instance.routing_model, routes)
        self.assignment_instance.assignment = self.assignment_instance.routing_model.ReadAssignmentFromRoutes(
            routes, False
        )
        self.assignment_instance.assignment = self.assignment_instance.routing_model.SolveFromAssignmentWithParameters(
            self.assignment_instance.assignment,
            self.assignment_instance.search_parameters.rerun_search_parameters
        )
        self._dump_current_routes('result')

    def _dump_current_routes(self, postfix=None):
        # return
        postfix = postfix or self.assignment_instance.current_iteration
        res = []
        for dr, tour in self.assignment_instance.result.drivers_tours.items():
            points = []
            for point in tour.points:
                points.append({'kind': point.point_kind, 'loc': point.location})
            res.append({'driver_id': dr, 'points': points})
        with open('result_replays/test_ro_minimize_time_{}.json'.format(postfix), 'w') as f:
            json.dump({'routes': res}, f)
