import json
import math

from ortools.constraint_solver import pywrapcp

from route_optimisation.engine.events import event_handler
from route_optimisation.logging import EventType

from ...context import BaseAssignmentContext, current_context
from ..iterating_assignment import IteratingAssignmentImplementation, IteratingServices
from ..services import (
    MinSkippedAssignmentStore,
    MoveAndSwapPointsHelper,
    NearbyAssignByCloseness,
    NearbyReassignByClosenessDiff,
    NearbyReassignPrepareHelper,
    PickupRationalPosition,
    PreviousRunStore,
    ReassignPointsManager,
    RouteBalancingHelper,
    RoutePointsReassignHelper,
    RoutesManager,
    SimpleTimer,
    SoftAssignmentRoutesCleaner,
    SwapFullRouteHelper,
    UnassignNonNearby,
)
from .base import BalancedAssignmentIteratingBase


class BalancedAssignmentServices(IteratingServices):
    def __init__(self, routes, route_balancing_allowed_diff,
                 context: BaseAssignmentContext,
                 routing_manager: pywrapcp.RoutingIndexManager,
                 route_find_best_place_cache: dict):
        params = {'context': context, 'routing_manager': routing_manager}
        self.routes_manager = RoutesManager(
            routes, context, routing_manager, route_find_best_place_cache, route_can_be_skipped=False
        )
        self.reassign_points = ReassignPointsManager(**params)
        self.swap_helper = SwapFullRouteHelper(self.routes_manager, **params)
        self.pickup_reassign_helper = PickupRationalPosition(self.routes_manager, **params)
        self.reassign_helper = RoutePointsReassignHelper(self.routes_manager, self.reassign_points, **params)
        self.routes_cleaner = SoftAssignmentRoutesCleaner(self.routes_manager, self.reassign_points)
        self.balancing = RouteBalancingHelper(route_balancing_allowed_diff, self.routes_manager, **params)
        self.nearby_by_closeness = NearbyAssignByCloseness(self.routes_manager, self.reassign_points, **params)
        self.nearby_reassign_by_diff = NearbyReassignByClosenessDiff(
            self.routes_manager, self.reassign_points, **params)
        self.nearby_reassign_helper = NearbyReassignPrepareHelper(self.routes_manager, self.reassign_points, **params)
        self.unassign_nearby = UnassignNonNearby(self.routes_manager, self.reassign_points, **params)
        self.point_swap = MoveAndSwapPointsHelper(self.routes_manager, **params)
        self.rebalance_allowed = False


class BalancedIteratingImplementation(IteratingAssignmentImplementation):
    def __init__(self, assignment_instance: BalancedAssignmentIteratingBase):
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

    def init_iteration_services(self) -> BalancedAssignmentServices:
        return BalancedAssignmentServices(
            self.assignment_instance.to_routes(),
            self.assignment_instance.route_balancing_allowed_diff,
            current_context,
            self.assignment_instance.routing_manager,
            self.route_find_best_place_cache,
        )

    def init_finish_services(self) -> BalancedAssignmentServices:
        routes = self.min_skipped_assignment.routes
        if routes is None:
            routes = self.assignment_instance.to_routes()
        return BalancedAssignmentServices(
            routes,
            self.assignment_instance.route_balancing_allowed_diff,
            current_context,
            self.assignment_instance.routing_manager,
            self.route_find_best_place_cache,
        )

    def on_iteration_start(self, services: BalancedAssignmentServices):
        services.pickup_reassign_helper.process()
        services.swap_helper.process()
        services.routes_cleaner.process()
        services.nearby_reassign_helper.process()
        self.previous_runs.process_skipped(services.reassign_points)
        services.rebalance_allowed = self._is_rebalance_allowed(services)
        if services.rebalance_allowed:
            services.balancing.prepare()

    def _is_rebalance_allowed(self, services: BalancedAssignmentServices):
        half_iterations_passed = \
            self.assignment_instance.current_iteration \
            >= math.floor(self.assignment_instance.get_iterations_count()/2)
        return half_iterations_passed or not services.reassign_points.has_points \
            or self.previous_runs.not_changing_orders_count

    def check_break_after_iteration_start(self, services: BalancedAssignmentServices):
        if not (services.balancing.need_rebalance or services.nearby_reassign_helper.have_faraway_points
                or services.reassign_points.has_points):
            event_handler.dev(
                EventType.OPTIMISATION_PROCESS,
                f'Break cycle. balancing.need_rebalance: {services.balancing.need_rebalance}, '
                f'nearby_reassign_helper.have_faraway_points: {services.nearby_reassign_helper.have_faraway_points}, '
                f'reassign_points.has_points: {services.reassign_points.has_points}'
            )
            return True

    def do_iteration_logic(self, services: BalancedAssignmentServices):
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

            if services.rebalance_allowed:
                event_messages.append(f'Points to reassign: {len(services.reassign_points.points_to_reassign)}')
                with timer.timeit('balancing'):
                    services.balancing.process()
                services.routes_manager.fix_end_times()

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

        services.routes_manager.unfix_end_times()
        event_messages.append(f'Points to reassign: {len(services.reassign_points.points_to_reassign)}')
        with timer.timeit('point_swap'):
            services.point_swap.process()
        services.pickup_reassign_helper.process()
        services.swap_helper.process()
        event_messages.append(f'Points to reassign: {len(services.reassign_points.points_to_reassign)}')
        event_handler.dev(EventType.OPTIMISATION_PROCESS, '\n'.join(event_messages))

    def after_iteration(self, services: BalancedAssignmentServices):
        self.assignment_instance.temp_vehicle_end_times = services.routes_manager.routes_time_end()
        self.min_skipped_assignment.process(services.reassign_points, services.routes_manager)

    def setup_assignment_after_iteration(self, services: BalancedAssignmentServices):
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

    def clean_routes_before_finish(self, services: BalancedAssignmentServices):
        services.routes_cleaner.process()

    def setup_assignment_on_finish(self, services: BalancedAssignmentServices):
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
        with open('result_replays/test_ro_balancing_{}.json'.format(postfix), 'w') as f:
            json.dump({'routes': res}, f)
