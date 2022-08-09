from functools import partial
from operator import attrgetter
from typing import Iterable

from ortools.constraint_solver import pywrapcp

from route_optimisation.engine.ortools import constants
from route_optimisation.engine.ortools.context import current_context

from ..helper_classes import Vehicle
from ..search_parameters import SearchParameters
from .result_parser import DefaultPrinter, OrToolsAssignmentResult


class AssignmentBase(object):
    @property
    def result(self):
        return self._make_assignment_result()

    def _make_assignment_result(self):
        raise NotImplementedError()

    def make_assignment(self):
        raise NotImplementedError()

    def default_printer(self):
        raise NotImplementedError()

    def clean(self):
        pass

    def __str__(self):
        result = '{class_name}. {assignment_parameters}; {main_info}\n'.format(
            class_name=self.__class__.__name__,
            assignment_parameters=self.str_assignment_parameters(),
            main_info=self.str_main_info()
        )
        result += str(self.result)
        return result.strip()

    def str_assignment_parameters(self):
        raise NotImplementedError()

    def str_main_info(self):
        raise NotImplementedError()


class ORToolsAssignmentBase(AssignmentBase):
    TIME_DIMENSION = 'Time'
    TIME_DIMENSION_SERVICE_FIRST = 'TimeSF'
    CAPACITY_DIMENSION = 'Capacity'
    COUNT_DIMENSION = 'Count'

    def __init__(self, search_parameters, *args, **kwargs):
        self.search_parameters: SearchParameters = search_parameters
        assert current_context.matrix, 'Google matrix must be calculated'
        self.routing_model = None
        self.routing_manager = None
        self.assignment = None

    @property
    def is_successful(self):
        return len(self.result.drivers_tours) > 0

    def _make_assignment_result(self):
        return OrToolsAssignmentResult(self).parse()

    def default_printer(self):
        return DefaultPrinter(self).parse()

    def clean(self):
        self.routing_model = None
        self.routing_manager = None
        self.assignment = None

    def str_assignment_parameters(self):
        return 'Strategy: {obj.search_parameters.first_solution_strategy}. ' \
               'Local search: {obj.search_parameters.local_search_metaheuristic}'.format(obj=self)

    def str_main_info(self):
        return 'Skipped Orders: {skipped_len}; Skipped Drivers: {skipped_drivers_len}; ' \
               'TIME: {obj.result.driving_time}; ' \
               'DISTANCE: {obj.result.driving_distance}'.format(obj=self, skipped_len=len(self.result.skipped_orders),
                                                                skipped_drivers_len=len(self.result.skipped_drivers),)

    def __eq__(self, other):
        if isinstance(other, ORToolsAssignmentBase):
            return self.result == other.result
        else:
            return False

    def __hash__(self):
        return hash(str(self.result))

    def compare_by_estimated_time(self, other):
        if len(other.result.skipped_orders) > len(self.result.skipped_orders):
            return -1
        if len(other.result.skipped_orders) == len(self.result.skipped_orders) \
                and other.result.driving_time > self.result.driving_time:
            return -1
        return 1

    @property
    def tour_periods_ratio(self):
        tour_periods = map(attrgetter('full_time'), list(self.result.drivers_tours.values()))
        tour_periods = sorted(tour_periods)
        return float(tour_periods[-1]) / tour_periods[0] if tour_periods[0] > 0 else float('inf')

    @property
    def tour_time_diff_to_avg(self):
        return max(map(abs, map(attrgetter('ratio_to_avg'), self.result.drivers_tours.values())))

    def to_routes(self):
        routes = []
        for i, veh in enumerate(current_context.vehicles):
            vehicle_route = []
            first_index = self.routing_model.Start(i)
            first_var = self.routing_model.NextVar(first_index)
            current_index = self.assignment.Value(first_var)
            while not self.routing_model.IsEnd(current_index):
                vehicle_route.append(current_index)
                next_var = self.routing_model.NextVar(current_index)
                current_index = self.assignment.Value(next_var)
            routes.append(vehicle_route)
        return routes

    def setup(self):
        # The number of nodes of the VRP is num_locations. Nodes are indexed from 0 to num_locations - 1.
        # The number of vehicles of the VRP is num_vehicles. Vehicles also are indexed from 0 to num_vehicles - 1
        self.routing_manager = pywrapcp.RoutingIndexManager(
            current_context.num_locations, current_context.num_vehicles,
            current_context.start_locations, current_context.end_locations
        )
        self.routing_model = pywrapcp.RoutingModel(self.routing_manager)

        # TODO: Refactoring
        self.allow_skipping_orders(self.routing_model, self.routing_manager)
        self.set_cost_function_for_all_vehicles(self.routing_model, self.routing_manager)
        self.add_time_dimension(self.routing_model, self.routing_manager)
        self.add_capacity_dimension(self.routing_model, self.routing_manager)
        self.set_allowed_vehicles(self.routing_model, self.routing_manager)
        self.add_pickup_delivery_requirements(self.routing_model, self.routing_manager)
        self.set_required_sequence(self.routing_model, self.routing_manager)
        self.add_driver_breaks(self.routing_model, self.routing_manager)
        self.customize_routing_model()

    def make_assignment(self, *args, **kwargs):
        self.setup()
        self.assignment = self.routing_model.SolveWithParameters(self.search_parameters.parameters)
        return self.assignment is not None

    def set_allowed_vehicles(self, routing, manager):
        for order in current_context.orders:
            allowed_vehicles = set()
            for i, vehicle in enumerate(current_context.vehicles):
                if order.check_vehicle_skills_set(vehicle):
                    allowed_vehicles.add(i)
                if order.check_assigned_vehicle(vehicle):
                    allowed_vehicles.intersection_update({i})
                    break
            order_index = manager.NodeToIndex(current_context.points_node_id_map[order.unique_id])
            routing.VehicleVar(order_index).SetValues([-1] + list(allowed_vehicles))

    def set_required_sequence(self, routing, manager):
        for i, vehicle in enumerate(current_context.vehicles):
            if vehicle.required_start_sequence is None:
                continue
            for site_from, site_to in zip(vehicle.required_start_sequence[:-1], vehicle.required_start_sequence[1:]):
                from_index = manager.NodeToIndex(current_context.points_node_id_map[site_from.unique_id])
                to_index = manager.NodeToIndex(current_context.points_node_id_map[site_to.unique_id])
                routing.solver().Add(routing.NextVar(from_index) == to_index)
                routing.VehicleVar(from_index).SetValues([-1, i])

    def allow_skipping_orders(self, routing, manager):
        for i, order_node in enumerate(range(len(current_context.sites), current_context.num_locations)):
            if current_context.orders[i].allow_skip:
                routing.AddDisjunction([manager.NodeToIndex(order_node)], constants.PENALTY_FOR_SKIP)

    def set_cost_function_for_all_vehicles(self, routing, manager):
        cost_evaluator_callbacks = [partial(current_context.time_callback, i)
                                    for i in range(current_context.num_vehicles)]
        cost_evaluator_callbacks = [partial(self.index_to_node_decorator, manager, cb)
                                    for cb in cost_evaluator_callbacks]
        for i, cb in zip(range(current_context.num_vehicles), cost_evaluator_callbacks):
            distance_callback_index = routing.RegisterTransitCallback(cb)
            routing.SetArcCostEvaluatorOfVehicle(distance_callback_index, i)

    def add_time_dimension(self, routing, manager):
        time_callbacks = [partial(current_context.time_callback, i) for i in range(current_context.num_vehicles)]
        time_callbacks = [partial(self.index_to_node_decorator, manager, cb) for cb in time_callbacks]
        time_callback_indices = [routing.RegisterTransitCallback(cb) for cb in time_callbacks]
        routing.AddDimensionWithVehicleTransits(time_callback_indices, constants.TWO_DAYS, constants.TWO_DAYS, False,
                                                self.TIME_DIMENSION)
        if current_context.have_driver_breaks:
            time_callbacks_sf = [partial(current_context.time_callback_service_first, i)
                                 for i in range(current_context.num_vehicles)]
            time_callbacks_sf = [partial(self.index_to_node_decorator, manager, cb) for cb in time_callbacks_sf]
            time_callbacks_sf_indices = [routing.RegisterTransitCallback(cb) for cb in time_callbacks_sf]
            routing.AddDimensionWithVehicleTransits(
                time_callbacks_sf_indices, constants.TWO_DAYS, constants.TWO_DAYS,
                False, self.TIME_DIMENSION_SERVICE_FIRST
            )

    def add_driver_breaks(self, routing, manager):
        if not current_context.have_driver_breaks:
            return

        node_visit_transit = [0] * routing.Size()
        for index in range(routing.Size()):
            node_index = manager.IndexToNode(index)
            node_visit_transit[index] = current_context.ServiceTimeFrom(None, node_index, node_index)

        time_dimension = self.routing_model.GetMutableDimension(self.TIME_DIMENSION)
        time_dimension_sf = self.routing_model.GetMutableDimension(self.TIME_DIMENSION_SERVICE_FIRST)
        solver = routing.solver()
        vehicles: Iterable[Vehicle] = current_context.vehicles
        for vehicle_idx, vehicle in enumerate(vehicles):
            breaks = [
                solver.FixedDurationIntervalVar(
                    max(driver_break.start_time - driver_break.diff_allowed, vehicle.start_time),  # break start min
                    min(driver_break.start_time + driver_break.diff_allowed, vehicle.end_time),  # break start max
                    driver_break.duration,  # break duration
                    False,  # optional: no
                    'Break'
                ) for driver_break in vehicle.breaks
            ]
            if breaks:
                time_dimension_sf.SetBreakIntervalsOfVehicle(breaks, vehicle_idx, node_visit_transit)
        for index in range(routing.Size()):
            if routing.IsEnd(index):   # no slack in end node
                continue
            slack_var, slack_var_sf = time_dimension.SlackVar(index), time_dimension_sf.SlackVar(index)
            routing.AddToAssignment(slack_var)
            routing.AddToAssignment(slack_var_sf)
            solver.Add(slack_var == slack_var_sf)

    def add_capacity_dimension(self, routing, manager):
        capacity_callback = partial(self.index_to_node_decorator, manager, current_context.capacity_callback)
        capacity_callback_index = routing.RegisterTransitCallback(capacity_callback)
        routing.AddDimensionWithVehicleCapacity(
            capacity_callback_index, 0, current_context.vehicle_capacities, False, self.CAPACITY_DIMENSION
        )

    def add_pickup_delivery_requirements(self, routing, manager):
        for pickup, delivery in current_context.pickup_delivery:
            pickup_index = manager.NodeToIndex(current_context.points_node_id_map[pickup.unique_id])
            delivery_index = manager.NodeToIndex(current_context.points_node_id_map[delivery.unique_id])
            routing.AddPickupAndDelivery(pickup_index, delivery_index)
            routing.solver().Add(routing.VehicleVar(pickup_index) == routing.VehicleVar(delivery_index))

    def index_to_node_decorator(self, manager, callback, from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return callback(from_node, to_node)

    def customize_routing_model(self):
        pass


class TimeBalancedAssignmentMixin(object):
    def __init__(self, search_parameters, time_balancing_coefficient, *args, **kwargs):
        super().__init__(search_parameters, *args, **kwargs)
        self.time_balancing_coefficient = time_balancing_coefficient
        self.driver_start_upper_bound_coefficient = self.time_balancing_coefficient + 1

    def str_assignment_parameters(self):
        return 'Time Balancing coefficient: {obj.time_balancing_coefficient}; {base}'.format(
            obj=self, base=super().str_assignment_parameters()
        )

    def customize_routing_model(self):
        super().customize_routing_model()
        time_dimension = self.routing_model.GetMutableDimension(self.TIME_DIMENSION)
        self._set_balancing(time_dimension)

    def _set_balancing(self, time_dimension):
        time_dimension.SetGlobalSpanCostCoefficient(self.time_balancing_coefficient)


class UseAllDriversAssignmentMixin(object):
    def str_assignment_parameters(self):
        return 'Use All Drivers; {base}'.format(base=super().str_assignment_parameters())

    def customize_routing_model(self):
        super().customize_routing_model()
        self._add_count_dimension()
        self._use_costs_for_empty_route()

    def _add_count_dimension(self):
        self.routing_model.AddConstantDimension(
            1,  # increment by one every time
            len(current_context.points) + 2,
            True,  # set count to zero
            self.COUNT_DIMENSION
        )

    def _use_costs_for_empty_route(self):
        count_dimension = self.routing_model.GetDimensionOrDie(self.COUNT_DIMENSION)
        for i, veh in enumerate(current_context.vehicles):
            self.routing_model.SetVehicleUsedWhenEmpty(True, i)
            end_index = self.routing_model.End(i)
            count_dimension.SetCumulVarSoftLowerBound(end_index, 2, constants.PENALTY_FOR_EMPTY_ROUTE)


class ORToolsSimpleAssignment(ORToolsAssignmentBase):
    def __init__(self, search_parameters, *args, **kwargs):
        super().__init__(search_parameters, *args, **kwargs)
        self.driver_start_upper_bound_coefficient = 1

    def make_assignment(self, assignment_progress_watcher):
        return super(ORToolsSimpleAssignment, self).make_assignment()

    def customize_routing_model(self):
        super().customize_routing_model()
        time_dimension = self.routing_model.GetDimensionOrDie(self.TIME_DIMENSION)
        self._setup_drivers_time_windows()
        self._job_time_limits(time_dimension)
        self._setup_dictate_driver_to_begin_at_start_time()

    def _setup_drivers_time_windows(self):
        time_dimension = self.routing_model.GetDimensionOrDie(self.TIME_DIMENSION)
        self._drivers_time_windows(time_dimension)

        if current_context.have_driver_breaks:
            time_dimension_service_first = self.routing_model.GetDimensionOrDie(self.TIME_DIMENSION_SERVICE_FIRST)
            solver = self.routing_model.solver()
            self._drivers_time_windows(time_dimension_service_first)
            for i, veh in enumerate(current_context.vehicles):
                start_index = self.routing_model.Start(i)
                solver.Add(time_dimension.CumulVar(start_index) == time_dimension_service_first.CumulVar(start_index))

    def _setup_dictate_driver_to_begin_at_start_time(self):
        time_dimension = self.routing_model.GetDimensionOrDie(self.TIME_DIMENSION)
        self._dictate_driver_to_begin_at_start_time(time_dimension)

        if current_context.have_driver_breaks:
            time_dimension_service_first = self.routing_model.GetDimensionOrDie(self.TIME_DIMENSION_SERVICE_FIRST)
            self._dictate_driver_to_begin_at_start_time(time_dimension_service_first)

    def _drivers_time_windows(self, time_dimension):
        for i, veh in enumerate(current_context.vehicles):
            start_index, end_index = self.routing_model.Start(i), self.routing_model.End(i)
            time_dimension.CumulVar(start_index).SetMin(veh.start_time)
            time_dimension.CumulVar(end_index).SetMax(veh.end_time)
            self.routing_model.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(start_index))

    def _job_time_limits(self, time_dimension):
        # Add limit on size of the time windows.
        for i, order_node in enumerate(range(len(current_context.sites), current_context.num_locations)):
            index = self.routing_manager.NodeToIndex(order_node)
            time_dimension.CumulVar(index).SetRange(*current_context.orders_times[i])

    def _dictate_driver_to_begin_at_start_time(self, time_dimension):
        for i, veh in enumerate(current_context.vehicles):
            start_index = self.routing_model.Start(i)
            time_dimension.SetCumulVarSoftUpperBound(start_index, veh.start_time,
                                                     self.driver_start_upper_bound_coefficient)

    def lock_drivers_orders(self, routing, routes):
        for vehicle_idx, route in enumerate(routes):
            for order_index in route:
                routing.VehicleVar(order_index).SetValues([-1, vehicle_idx])
        time_dimension = routing.GetMutableDimension(self.TIME_DIMENSION)
        for i, veh in enumerate(current_context.vehicles):
            start_index, end_index = routing.Start(i), routing.End(i)
            time_dimension.CumulVar(end_index).SetMax(veh.end_time)

    def planned_inner_steps_count(self):
        return 0


class ExtendedTimeWindowAssignment(ORToolsSimpleAssignment):

    def _drivers_time_windows(self, time_dimension):
        for i, veh in enumerate(current_context.vehicles):
            start_index, end_index = self.routing_model.Start(i), self.routing_model.End(i)
            time_dimension.CumulVar(start_index).SetMin(veh.start_time)
            end_time = min(veh.end_time + 3600, 24 * 3600)
            time_dimension.CumulVar(end_index).SetMax(end_time)
            self.routing_model.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(start_index))

    def _job_time_limits(self, time_dimension):
        # Add limit on size of the time windows.
        for i, order_node in enumerate(range(len(current_context.sites), current_context.num_locations)):
            index = self.routing_manager.NodeToIndex(order_node)
            start_time, end_time = current_context.orders_times[i]
            n_start_time = max(start_time - 3600, 0)
            time_dimension.CumulVar(index).SetMin(n_start_time)
            n_end_time = min(end_time + 3600, (24 * 3600) - 1)
            time_dimension.CumulVar(index).SetMax(n_end_time)
