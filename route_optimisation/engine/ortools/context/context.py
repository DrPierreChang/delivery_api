from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from route_optimisation.engine.base_classes.parameters import EngineParameters
from route_optimisation.engine.events import event_handler
from route_optimisation.engine.ortools import constants
from route_optimisation.engine.ortools.context.init import (
    DepotInit,
    DistanceMatrixInit,
    HelpVariables,
    OrdersInit,
    OrdersRelatedVariables,
    PointsInit,
    RequiredStartSequenceInit,
    VehicleInit,
    VehiclesRelatedVariables,
)
from route_optimisation.engine.ortools.helper_classes import Delivery, FakeDepot, JobSite, Pickup, SiteBase, Vehicle
from route_optimisation.logging import EventType


class BaseAssignmentContext:
    initials = None

    def __init__(self, parameters):
        self._log_params(parameters)
        self._define_variables()

        zero_time = datetime.combine(parameters.day, datetime.min.time())
        self.zero_time = parameters.timezone.localize(zero_time)

        for init in self.initials:
            init.assert_required_fields(self)
            init(self, parameters)

        # Put callbacks to the distance function and travel time functions here.
        self.distance_callback = self.Distance
        self.time_callback = self.TotalTimeWithService
        self.time_callback_service_first = self.TotalTimeWithServiceFirst
        self.capacity_callback = self.Capacity

    def Distance(self, vehicle_index, from_node, to_node):
        check_sites = self.check_sites(vehicle_index, from_node, to_node)
        if check_sites is not None:
            return check_sites
        if not self.is_node_available(vehicle_index, to_node):
            return constants.PENALTY_FOR_ANOTHER_DRIVER_ORDER
        return self.get_matrix_value(from_node, to_node, 'distance')

    def TotalTime(self, vehicle_index, from_node, to_node):
        check_sites = self.check_sites(vehicle_index, from_node, to_node)
        if check_sites is not None:
            return check_sites
        return self.get_matrix_value(from_node, to_node, 'duration')

    def TotalTimeWithService(self, vehicle_index, from_node, to_node):
        service = self.ServiceTime(vehicle_index, from_node, to_node)
        return self.TotalTime(vehicle_index, from_node, to_node) + service

    def TotalTimeWithServiceFirst(self, vehicle_index, from_node, to_node):
        service = self.ServiceTimeFrom(vehicle_index, from_node, to_node)
        return self.TotalTime(vehicle_index, from_node, to_node) + service

    def ServiceTime(self, vehicle_index, from_node, to_node):
        if to_node in self.sites_node_ids:
            return 0
        order = self.orders[to_node - len(self.sites)]
        if order.service_time is not None:
            return order.service_time
        return self.pickup_service_time if isinstance(order, Pickup) else self.service_time

    def ServiceTimeFrom(self, vehicle_index, from_node, to_node):
        if from_node in self.sites_node_ids:
            return 0
        order = self.orders[from_node - len(self.sites)]
        if order.service_time is not None:
            return order.service_time
        return self.pickup_service_time if isinstance(order, Pickup) else self.service_time

    def Capacity(self, from_node, to_node):
        if not self.use_vehicle_capacity:
            return 0
        if to_node >= len(self.sites):
            order = self.orders[to_node - len(self.sites)]
            if isinstance(order, Pickup):
                return order.capacity
            return -1*order.capacity
        else:
            return 0

    def get_order_period(self, order):
        order_deliver_after_time_delta = (order.window_start - self.zero_time) \
            if order.window_start else timedelta()
        order_deliver_before_time_delta = (order.window_end - self.zero_time) \
            if order.window_end else timedelta(hours=24)
        return int(order_deliver_after_time_delta.total_seconds()), \
            int(order_deliver_before_time_delta.total_seconds())

    def get_matrix_value(self, from_node, to_node, field):
        return self.matrix[(self.points[from_node].location, self.points[to_node].location)][field]

    def check_sites(self, vehicle_index, from_node, to_node):
        val = None
        if from_node == self.fake_depot_node_id:
            val = 0 if from_node == self.start_locations[vehicle_index] else constants.PENALTY_FOR_WRONG_DEPOT
        if to_node == self.fake_depot_node_id:
            val = 0 if to_node == self.end_locations[vehicle_index] else constants.PENALTY_FOR_WRONG_DEPOT
        return val

    def is_node_available(self, vehicle_index, node):
        if node >= len(self.sites):
            order = self.orders[node - len(self.sites)]
            vehicle = self.vehicles[vehicle_index]
            if not self._available_by_assigning(order, vehicle):
                return False
            if not self._available_by_skills(order, vehicle):
                return False
        return True

    def _available_by_assigning(self, order, vehicle):
        return order.driver_member_id is None or vehicle.vehicle_id == order.driver_member_id

    def _available_by_skills(self, order, vehicle):
        return not set(order.skill_set).difference(set(vehicle.skill_set))

    @property
    def is_without_start_end(self):
        return self.fake_depot and len(self.sites) == 1

    @property
    def has_pickup(self):
        return len(self.pickup_delivery) > 0

    def handle_not_accessible_orders(self, orders):
        bad_points = []
        for order in orders:
            if order in self.orders:
                self.orders.remove(order)
                bad_points.append(order)
        if len(bad_points) > 0:
            skipped_orders = list(map(SiteBase.original_id_getter, bad_points))
            event_kwargs = {'objects': skipped_orders, 'code': 'not_accessible_orders'}
            event_handler.info(EventType.SKIPPED_OBJECTS, msg=None, optimisation_propagate=True, **event_kwargs)
        OrdersRelatedVariables()(self, None)

    def _define_variables(self):
        self.vehicles: List[Vehicle] = []
        self.sites: List[SiteBase] = []
        self.num_vehicles: int = 0
        self.have_driver_breaks: bool = False
        # Used to emulate free start/end (i.e. without start/end hub or location)
        self.fake_depot: Optional[FakeDepot] = None
        self.fake_depot_node_id: Optional[int] = None
        self.sites_node_id_map: dict = {}
        self.sites_node_ids: List[int] = []
        self.orders: List[JobSite] = []
        self.pickup_delivery: List[Tuple[Pickup, Delivery]] = []
        self.points: List[SiteBase] = []
        self.orders_times: List = []
        self.points_node_id_map: dict = {}
        self.num_locations: int = 0
        self.vehicle_capacities: List = []
        self.use_vehicle_capacity = False
        self.start_locations: List = []
        self.end_locations: List = []
        self.service_time: int = 0
        self.pickup_service_time: int = 0
        self.matrix: dict = {}

    def _log_params(self, parameters: EngineParameters):
        event_handler.dev(
            EventType.CONTEXT_BUILDING,
            'EngineParameters. Timezone: %s, Day: %s, Service Time: %s, Pickup Service Time: %s' % (
                parameters.timezone, parameters.day, parameters.default_job_service_time,
                parameters.default_pickup_service_time,
            ),
        )
        event_handler.dev(
            EventType.CONTEXT_BUILDING,
            'EngineParameters. Jobs: %s, List: %s' % (len(parameters.jobs), list(map(str, parameters.jobs))),
        )
        event_handler.dev(
            EventType.CONTEXT_BUILDING,
            'EngineParameters. Drivers: %s, List: %s' % (len(parameters.drivers), list(map(str, parameters.drivers))),
        )
        if parameters.required_start_sequence is not None:
            event_handler.dev(EventType.CONTEXT_BUILDING, 'EngineParameters. %s' % parameters.required_start_sequence)


class GroupAssignmentContext(BaseAssignmentContext):
    initials = (
        VehicleInit(),
        DepotInit(),
        OrdersInit(),
        OrdersRelatedVariables(),
        VehiclesRelatedVariables(),
        HelpVariables(),
        PointsInit(),
        RequiredStartSequenceInit(),
        DistanceMatrixInit(),
    )
