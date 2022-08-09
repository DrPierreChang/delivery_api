import operator
from collections import defaultdict
from functools import reduce
from typing import List

from django.utils.translation import ugettext_lazy as _

from dateutil.parser import parse

from route_optimisation.engine.base_classes.parameters import Driver, EngineParameters, JobKind
from route_optimisation.engine.errors import ROError
from route_optimisation.engine.events import event_handler
from route_optimisation.engine.ortools.distance_matrix import DistanceMatrixBuilder
from route_optimisation.engine.ortools.helper_classes import (
    ConcreteLocation,
    Delivery,
    Depot,
    FakeDepot,
    Pickup,
    SiteBase,
    Vehicle,
)
from route_optimisation.engine.utils import time_to_seconds, to_dict_point
from route_optimisation.logging import EventType
from route_optimisation.logging.logs.progress import ProgressConst
from routing.utils import latlng_dict_from_str


class ContextInitializer:
    require = None

    def assert_required_fields(self, ctx):
        if not self.require:
            return
        for field in self.require:
            assert hasattr(ctx, field), 'Field {} was not initialized in context yet'.format(field)

    def __call__(self, ctx, params, *args, **kwargs):
        raise NotImplementedError()


class VehicleInit(ContextInitializer):
    def __call__(self, ctx, params, *args, **kwargs):
        ctx.vehicles, ctx.sites = [], []
        for driver in params.drivers:
            ctx.vehicles.append(self._perform_vehicle_creation(ctx, driver))
        ctx.num_vehicles = len(ctx.vehicles)

    @staticmethod
    def _perform_vehicle_creation(ctx, vehicle: Driver):
        breaks = [
            {'start_time': time_to_seconds(driver_break.start_time),
             'end_time': time_to_seconds(driver_break.end_time),
             'diff_allowed': driver_break.diff_allowed}
            for driver_break in vehicle.breaks
        ]
        params = dict(vehicle_id=vehicle.member_id, start_time=time_to_seconds(vehicle.start_time),
                      end_time=time_to_seconds(vehicle.end_time), skill_set=vehicle.skill_set,
                      capacity=vehicle.capacity, breaks=breaks,)
        options = [
            ('start_location', 'start_location', VehicleInit._create_concrete_location),
            ('end_location', 'end_location', VehicleInit._create_concrete_location),
            ('start_hub', 'start_depot', VehicleInit._create_depot),
            ('end_hub', 'end_depot', VehicleInit._create_depot),
        ]
        for option, param_name, init_func in options:
            option_value = getattr(vehicle, option)
            if option_value is not None:
                params[param_name] = init_func(ctx, option_value)
        vehicle = Vehicle(**params)
        if vehicle.get_start_site() is None:
            vehicle.start_site = VehicleInit._create_fake_depot(ctx)
        if vehicle.get_end_site() is None:
            vehicle.end_site = VehicleInit._create_fake_depot(ctx)
        return vehicle

    @staticmethod
    def _create_concrete_location(ctx, location_data):
        loc = ConcreteLocation(
            len(ctx.sites), to_dict_point(location_data.location, x_y=False),
            location_data.address, location_data.id
        )
        event_handler.dev(EventType.CONTEXT_BUILDING, 'Create Location obj: %s' % location_data.location)
        ctx.sites.append(loc)
        return loc

    @staticmethod
    def _create_depot(ctx, depot_data):
        for site in ctx.sites:
            if isinstance(site, Depot) and site.original_id == depot_data.id:
                return site
        dep = Depot(depot_data.id, to_dict_point(depot_data.location, x_y=False))
        event_handler.dev(EventType.CONTEXT_BUILDING, 'Create Depot: %s, %s' % (depot_data.id, depot_data.location))
        ctx.sites.append(dep)
        return dep

    @staticmethod
    def _create_fake_depot(ctx):
        if ctx.fake_depot is None:
            ctx.fake_depot = FakeDepot()
        return ctx.fake_depot


class DepotInit(ContextInitializer):
    require = ('sites', )

    def __call__(self, ctx, params, *args, **kwargs):
        if ctx.fake_depot is not None:
            ctx.sites = [ctx.fake_depot] + ctx.sites
            ctx.fake_depot_node_id = 0
        ctx.sites_node_id_map = {site.unique_id: i for i, site in enumerate(ctx.sites)}
        ctx.sites_node_ids = ctx.sites_node_id_map.values()


class OrdersInit(ContextInitializer):
    def __call__(self, ctx, params, *args, **kwargs):
        ctx.orders = []
        ctx.pickup_delivery = []
        for job in params.jobs:
            delivery = Delivery(
                order_id=job.id, location=to_dict_point(job.deliver_address, x_y=False),
                deliver_after=parse(job.deliver_after) if job.deliver_after else None,
                deliver_before=parse(job.deliver_before),
                driver_member_id=job.driver_member_id, skill_set=job.skill_set, capacity=job.capacity,
                service_time=job.service_time, allow_skip=job.allow_skip,
            )
            for i, pickup in enumerate(job.pickups):
                pickup_obj = Pickup(
                    parent_order_id=job.id, order_id=pickup.pickup_id,
                    location=to_dict_point(pickup.pickup_address, x_y=False),
                    deliver_after=parse(pickup.pickup_after) if pickup.pickup_after else None,
                    deliver_before=parse(pickup.pickup_before) if pickup.pickup_before else None,
                    driver_member_id=job.driver_member_id, skill_set=job.skill_set, capacity=pickup.capacity,
                    service_time=pickup.service_time,
                )
                ctx.orders.append(pickup_obj)
                ctx.pickup_delivery.append((pickup_obj, delivery))
            ctx.orders.append(delivery)


class OrdersRelatedVariables(ContextInitializer):
    require = ('orders', 'sites', 'zero_time', )

    def __call__(self, ctx, params, *args, **kwargs):
        ctx.points = ctx.sites + ctx.orders
        ctx.orders_times = list(map(ctx.get_order_period, ctx.orders))
        ctx.points_node_id_map = {site.unique_id: i for i, site in enumerate(ctx.points)}
        ctx.num_locations = len(ctx.points)


class VehiclesRelatedVariables(ContextInitializer):
    require = ('vehicles', )

    def __call__(self, ctx, params, *args, **kwargs):
        ctx.use_vehicle_capacity = params.use_vehicle_capacity
        ctx.vehicle_capacities = [(veh.capacity if ctx.use_vehicle_capacity else Vehicle.UNLIMITED_CAPACITY)
                                  for veh in ctx.vehicles]
        ctx.have_driver_breaks = any(len(vehicle.breaks) > 0 for vehicle in ctx.vehicles)


class PointsInit(ContextInitializer):
    require = ('vehicles', 'sites_node_id_map', )

    def __call__(self, ctx, params, *args, **kwargs):
        ctx.start_locations, ctx.end_locations = [], []
        for veh in ctx.vehicles:
            _start_node_id, _end_node_id = PointsInit._vehicle_start_end_node_id(ctx, veh)
            start, end = ctx.sites[_start_node_id], ctx.sites[_end_node_id]
            event_handler.dev(
                EventType.CONTEXT_BUILDING,
                'Vehicle id %s. Start: %s - %s. End: %s - %s.' % (
                    veh.vehicle_id,
                    type(start), start.unique_id,
                    type(end), end.unique_id,
                )
            )
            ctx.start_locations.append(_start_node_id)
            ctx.end_locations.append(_end_node_id)

    @staticmethod
    def _vehicle_start_end_node_id(ctx, vehicle):
        start_site = vehicle.get_start_site()
        start = ctx.sites_node_id_map[start_site.unique_id]
        end_site = vehicle.get_end_site()
        end = ctx.sites_node_id_map[end_site.unique_id]
        return start, end


class HelpVariables(ContextInitializer):
    def __call__(self, ctx, params, *args, **kwargs):
        ctx.service_time = params.default_job_service_time * 60
        ctx.pickup_service_time = params.default_pickup_service_time * 60
        ctx.focus = params.focus


class RequiredStartSequenceInit(ContextInitializer):
    def __call__(self, ctx, params: EngineParameters, *args, **kwargs):
        if params.required_start_sequence is None:
            return
        for sequence_setting in params.required_start_sequence:
            for vehicle in ctx.vehicles:
                if vehicle.vehicle_id != sequence_setting.driver_member_id:
                    continue
                self._setup_vehicle(vehicle, sequence_setting.sequence, ctx)

    def _setup_vehicle(self, vehicle, sequence, ctx):
        sites = []
        point_type_map = {
            JobKind.HUB: Depot,
            JobKind.DELIVERY: Delivery,
            JobKind.PICKUP: Pickup,
        }
        for item in sequence:
            point_type = point_type_map[item.point_kind]
            for point in ctx.points:
                if isinstance(point, point_type) and item.point_id == point.original_id:
                    sites.append(point)
                    break
        vehicle.required_start_sequence = sites


class DistanceMatrixInit(ContextInitializer):
    require = ('sites', 'points', )

    def __init__(self):
        self._clear_variables()

    def _clear_variables(self):
        self.location_point_map = None
        self.locations = None
        self.builder = None

    def __call__(self, ctx, params, *args, **kwargs):
        self._clear_variables()
        event_handler.progress(stage=ProgressConst.START_DISTANCE_MATRIX)
        self._handle_locations(ctx)
        self._build(ctx)
        self._clean_points(ctx)
        event_handler.progress(stage=ProgressConst.DISTANCE_MATRIX)

    def _handle_locations(self, ctx):
        real_points = list(filter(lambda x: not isinstance(x, FakeDepot), ctx.points))
        self.location_point_map = LocationPointMap()
        for point in real_points:
            self.location_point_map[point.location].append(point)
        self.locations = list(map(latlng_dict_from_str, self.location_point_map.keys()))

    def _build(self, ctx):
        self.builder = DistanceMatrixBuilder(self.locations)
        self.builder.build_via_directions_api()
        ctx.matrix = self.builder.matrix

    def _clean_points(self, ctx):
        components = self.builder.components
        if ctx.is_without_start_end and len(components) > 1:
            raise ROError(_('We could not create the optimisation. There are orders on different continents.'))

        locations_by_components = list(map(lambda comp: comp.get_used_locations(), components))
        points_by_components = []
        for locations in locations_by_components:
            points_getter = map(lambda loc: self.location_point_map[loc], locations)
            points_by_components.append(reduce(operator.add, points_getter, []))
        hubs_by_components = map(lambda _points: [point for point in _points if point in ctx.sites],
                                 points_by_components)
        components_with_hubs = len(list(filter(None, hubs_by_components)))
        if components_with_hubs > 1:
            raise ROError(_('We could not create the optimisation. There are hubs on different continents.'))
        elif components_with_hubs == 0:
            return

        not_accessible_orders = []
        for points in points_by_components:
            hubs_points = tuple(1 for point in points if point in ctx.sites)
            if len(hubs_points):
                continue
            for p in points:
                not_accessible_orders.append(p)
        ctx.handle_not_accessible_orders(not_accessible_orders)


class LocationPointMap(defaultdict):
    def __init__(self):
        super().__init__()
        self.default_factory = list

    @staticmethod
    def _transform_key(key) -> str:
        if isinstance(key, dict):
            return '{lat},{lng}'.format(**key)
        return key

    def __setitem__(self, key, value: List[SiteBase]):
        return super().__setitem__(self._transform_key(key), value)

    def __getitem__(self, item) -> List[SiteBase]:
        return super().__getitem__(self._transform_key(item))
