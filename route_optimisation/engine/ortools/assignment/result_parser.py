from datetime import datetime, timedelta
from functools import reduce
from operator import attrgetter
from typing import Iterable, List

from merchant.models import Hub
from route_optimisation.const import RoutePointKind
from route_optimisation.engine.base_classes.result import AssignmentResult, DriverTour, Point
from route_optimisation.engine.dima import dima_cache
from route_optimisation.engine.ortools.context import current_context
from route_optimisation.engine.ortools.helper_classes import (
    ConcreteLocation,
    Delivery,
    Depot,
    JobSite,
    Pickup,
    SiteBase,
    Vehicle,
    VehicleBreak,
)
from route_optimisation.engine.ortools.utils import extract_capacity
from route_optimisation.models.location import DriverRouteLocation
from tasks.models import Order


class DriverBreak:
    __slots__ = ('start_time', 'end_time',)

    def __init__(self, start_time: datetime, end_time: datetime):
        self.start_time: datetime = start_time
        self.end_time: datetime = end_time


class AssignmentParser:
    def parse(self):
        raise NotImplementedError()


class ORToolsAssignmentParser(AssignmentParser):
    def __init__(self, base):
        self.base = base
        self.skipped_jobs = None
        self.skipped_vehicles = set()

    def parse(self):
        self._on_start()
        for vehicle_nbr in range(current_context.num_vehicles):
            self._process_vehicle(vehicle_nbr)
        self._on_end()
        return self.result

    def _on_start(self):
        self.skipped_jobs = set([i for i, point in enumerate(current_context.points) if isinstance(point, Delivery)])

    def _process_vehicle(self, vehicle_nbr):
        raise NotImplementedError

    def _on_end(self):
        pass

    @property
    def result(self):
        raise NotImplementedError


def seconds2human(seconds):
    return str(timedelta(seconds=seconds))


class DefaultPrinter(ORToolsAssignmentParser):
    point_type_map = {
        Pickup: 'pickup',
        Delivery: 'delivery',
        Depot: 'hub',
        ConcreteLocation: 'location',
    }

    def __init__(self, base):
        super().__init__(base)
        self.result_str = ''

    def _on_start(self):
        super()._on_start()
        self.result_str += "ObjectiveValue: %s\n" % str(self.base.assignment.ObjectiveValue())

    def _process_vehicle(self, vehicle_nbr):
        node_template = "\n\t{node_index:>3}({index:>3}) Time({tmin:>8}, {tmax:>8}; break({tslmin:>7}, {tslmax:>7}))" \
                        " Capacity({capmin:^3}, {capmax:^3})" \
                        " {unique_id:<27} {loc:<40} ({avail_tmin:>8},{avail_tmax:>8})"
        time_dimension = self.base.routing_model.GetDimensionOrDie(self.base.TIME_DIMENSION)
        capacity_dimension = self.base.routing_model.GetDimensionOrDie(self.base.CAPACITY_DIMENSION)

        index = self.base.routing_model.Start(vehicle_nbr)
        plan_output = 'Route {0}:'.format(vehicle_nbr)
        have_jobs = False

        while not self.base.routing_model.IsEnd(index):
            self.skipped_jobs.difference_update({int(index)})
            node_index = self.base.routing_manager.IndexToNode(index)
            if isinstance(current_context.points[node_index], JobSite):
                have_jobs = True
            time_var = time_dimension.CumulVar(index)
            time_slack_var = time_dimension.SlackVar(index) if current_context.have_driver_breaks else None
            capacity_var = capacity_dimension.CumulVar(index)
            if isinstance(current_context.points[node_index], JobSite):
                avail_tmin, avail_tmax = current_context.get_order_period(current_context.points[node_index])
            else:
                veh = current_context.vehicles[vehicle_nbr]
                avail_tmin, avail_tmax = veh.start_time, veh.end_time
            plan_output += \
                node_template.format(
                    node_index=node_index,
                    index=index,
                    tmin=seconds2human(self.base.assignment.Min(time_var)),
                    tmax=seconds2human(self.base.assignment.Max(time_var)),
                    tslmin=seconds2human(self.base.assignment.Min(time_slack_var)) if time_slack_var else '',
                    tslmax=seconds2human(self.base.assignment.Max(time_slack_var)) if time_slack_var else '',
                    capmin=str(self.base.assignment.Min(capacity_var)),
                    capmax=str(self.base.assignment.Max(capacity_var)),
                    unique_id=current_context.points[node_index].unique_id,
                    loc='{lat},{lng}'.format(**current_context.points[node_index].location),
                    avail_tmin=seconds2human(avail_tmin),
                    avail_tmax=seconds2human(avail_tmax),
                )
            index = self.base.assignment.Value(self.base.routing_model.NextVar(index))

        self.skipped_jobs.difference_update({int(index)})
        node_index = self.base.routing_manager.IndexToNode(index)
        if isinstance(current_context.points[node_index], JobSite):
            have_jobs = True
        time_var = time_dimension.CumulVar(index)
        capacity_var = capacity_dimension.CumulVar(index)
        veh = current_context.vehicles[vehicle_nbr]
        avail_tmin, avail_tmax = veh.start_time, veh.end_time
        plan_output += \
            node_template.format(
                node_index=node_index,
                index=index,
                tmin=seconds2human(self.base.assignment.Min(time_var)),
                tmax=seconds2human(self.base.assignment.Max(time_var)),
                tslmin='', tslmax='',
                capmin=str(self.base.assignment.Min(capacity_var)),
                capmax=str(self.base.assignment.Max(capacity_var)),
                unique_id=current_context.points[node_index].unique_id,
                loc='{lat},{lng}'.format(**current_context.points[node_index].location),
                avail_tmin=seconds2human(avail_tmin),
                avail_tmax=seconds2human(avail_tmax),
            )

        if not have_jobs:
            self.skipped_vehicles.add(current_context.vehicles[vehicle_nbr].vehicle_id)

        self.result_str += '%s\n' % plan_output

    def _on_end(self):
        super()._on_end()
        self.result_str += 'Skipped jobs: %s\n' % self.skipped_jobs
        self.result_str += 'Skipped drivers: %s\n' % self.skipped_vehicles

    @property
    def result(self):
        return self.result_str


class NodeInfo:
    def __init__(self, node, time_start, current_capacity, driver_break_interval):
        self.node = node
        self.time_start = time_start
        self.current_capacity = current_capacity
        self.driver_break_interval = driver_break_interval


class OrToolsAssignmentResult(ORToolsAssignmentParser):
    model_class_map = {
        Pickup: Order,
        Delivery: Order,
        Depot: Hub,
        ConcreteLocation: DriverRouteLocation,
    }
    point_kind_map = {
        Pickup: RoutePointKind.PICKUP,
        Delivery: RoutePointKind.DELIVERY,
        Depot: RoutePointKind.HUB,
        ConcreteLocation: RoutePointKind.LOCATION,
    }

    def __init__(self, base):
        super().__init__(base)
        self.driver_tour_points = {}
        self.full_driving_time = 0
        self.full_distance = 0
        self.time_dimension = self.base.routing_model.GetDimensionOrDie(self.base.TIME_DIMENSION)
        self.capacity_dimension = self.base.routing_model.GetDimensionOrDie(self.base.CAPACITY_DIMENSION)

    def _process_vehicle(self, vehicle_nbr):
        nodes_sequence: List[NodeInfo] = []
        index = self.base.routing_model.Start(vehicle_nbr)
        while not self.base.routing_model.IsEnd(index):
            nodes_sequence.append(self._get_node_info(index))
            index = self.base.assignment.Value(self.base.routing_model.NextVar(index))
        nodes_sequence.append(self._get_node_info(index, last=True))
        self.skipped_jobs.difference_update(set(map(attrgetter('node'), nodes_sequence)))

        if len(nodes_sequence) < 3:
            self.skipped_vehicles.add(current_context.vehicles[vehicle_nbr].vehicle_id)
            return
        if current_context.start_locations[vehicle_nbr] == current_context.fake_depot_node_id:
            nodes_sequence = nodes_sequence[1:]
        if current_context.end_locations[vehicle_nbr] == current_context.fake_depot_node_id:
            nodes_sequence = nodes_sequence[:-1]

        def count_dimension_of_tour(dimension_function):
            tour_edges = zip(nodes_sequence[:-1], nodes_sequence[1:])
            return reduce(
                lambda s, edges: s + dimension_function(vehicle_nbr, edges[0].node, edges[1].node),
                tour_edges,
                0
            )

        tour_points = self._get_tour_points(vehicle_nbr, nodes_sequence)
        tour_driving_time = count_dimension_of_tour(current_context.TotalTime)
        tour_full_time = count_dimension_of_tour(current_context.TotalTimeWithService)
        driving_distance = count_dimension_of_tour(current_context.Distance)

        driver_tour = DriverTour(points=tour_points, driving_time=tour_driving_time, driving_distance=driving_distance,
                                 full_time=tour_full_time)
        self.driver_tour_points[current_context.vehicles[vehicle_nbr].vehicle_id] = driver_tour

        self.full_driving_time += tour_driving_time
        self.full_distance += driving_distance

    def _get_node_info(self, index, last=False):
        time_var = self.time_dimension.CumulVar(index)
        time_start = self.base.assignment.Min(time_var)
        capacity_var = self.capacity_dimension.CumulVar(index)
        capacity = self.base.assignment.Min(capacity_var)
        driver_break_interval = 0
        if current_context.have_driver_breaks and not last:
            time_slack_var = self.time_dimension.SlackVar(index)
            driver_break_interval = self.base.assignment.Min(time_slack_var)
        return NodeInfo(self.base.routing_manager.IndexToNode(index), time_start, capacity, driver_break_interval)

    def _get_tour_points(self, vehicle_nbr, nodes_sequence: List[NodeInfo]) -> List[Point]:
        tour_points = []
        previous_point = None
        for node_from, node_to in zip([None] + nodes_sequence[:-1], nodes_sequence[:]):
            breaks: List[DriverBreak] = []
            node_point_to = current_context.points[node_to.node]
            service_time, driving_time, distance, polyline = 0, 0, 0, None
            if node_from is not None:
                service_time = current_context.ServiceTime(vehicle_nbr, node_from.node, node_to.node)
                driving_time = current_context.TotalTime(vehicle_nbr, node_from.node, node_to.node)
                distance = current_context.Distance(vehicle_nbr, node_from.node, node_to.node)
                cache_directions = dima_cache.get_element(previous_point.location, node_point_to.location)
                if cache_directions:
                    polyline = cache_directions.get('steps', [{}])[0].get('polyline', {}).get('points', None)
            end_time = node_to.time_start
            start_time = end_time - service_time
            start_time = current_context.zero_time + timedelta(seconds=start_time)
            end_time = current_context.zero_time + timedelta(seconds=end_time)

            if node_from is not None and node_from.driver_break_interval > 0:
                breaks.extend(DriverBreaksHelper.get_breaks_times_for_vehicle(
                    vehicle=current_context.vehicles[vehicle_nbr],
                    start_transit=int((previous_point.end_time - current_context.zero_time).total_seconds()),
                    end_transit=int((start_time - current_context.zero_time).total_seconds()),
                    break_duration=node_from.driver_break_interval
                ))

            for driver_break in breaks:
                point = self.point_from_driver_break(driver_break, node_to, previous_point)
                tour_points.append(point)
                previous_point = point

            point = Point(
                point_prototype=node_point_to.get_prototype(),
                model_class=self.model_class_map[type(node_point_to)],
                point_kind=self.point_kind_map[type(node_point_to)],
                location=node_point_to.location,
                previous=previous_point,
                service_time=service_time,
                driving_time=driving_time,
                distance=distance,
                start_time=start_time,
                end_time=end_time,
                utilized_capacity=extract_capacity(node_to.current_capacity),
                polyline=polyline,
            )
            tour_points.append(point)
            previous_point = point
        return tour_points

    @staticmethod
    def point_from_driver_break(driver_break: DriverBreak, node_to: NodeInfo, previous_point) -> Point:
        return Point(
            point_prototype=None,
            model_class=None,
            point_kind=RoutePointKind.BREAK,
            location=None,
            previous=previous_point,
            service_time=int((driver_break.end_time - driver_break.start_time).total_seconds()),
            driving_time=0,
            distance=0,
            start_time=driver_break.start_time,
            end_time=driver_break.end_time,
            utilized_capacity=extract_capacity(node_to.current_capacity),
            polyline=None,
        )

    @property
    def result(self):
        skipped_orders = list(map(SiteBase.original_id_getter, [current_context.points[i] for i in self.skipped_jobs]))
        return AssignmentResult(
            self.driver_tour_points,
            skipped_orders,
            self.full_driving_time,
            self.full_distance,
            self.skipped_vehicles,
        )


class Break:
    def __init__(self, start_time: int, end_time: int):
        self.start_time: int = start_time
        self.end_time: int = end_time

    @property
    def duration(self) -> int:
        return self.end_time - self.start_time

    def intersects(self, another) -> bool:
        max_start = max(self.start_time, another.start_time)
        min_end = min(self.end_time, another.end_time)
        return max_start <= min_end


class DriverBreaksHelper:
    @staticmethod
    def get_breaks_times_for_vehicle(vehicle: Vehicle, start_transit: int, end_transit: int, break_duration: int) \
            -> List[DriverBreak]:
        break_settings = sorted(vehicle.breaks, key=lambda x: (x.start_time * 100000 + x.end_time))
        driver_breaks = []
        for break_setting in break_settings:
            break_time = None
            if DriverBreaksHelper.break_inside_transit(break_setting, start_transit, end_transit):
                break_time = (break_setting.start_time, break_setting.end_time)
            elif DriverBreaksHelper.break_on_transit_start(break_setting, start_transit):
                break_time = (start_transit, start_transit + break_setting.duration)
            elif DriverBreaksHelper.break_on_transit_end(break_setting, end_transit):
                break_time = (end_transit - break_setting.duration, end_transit)
            if break_time is not None:
                driver_breaks.append(Break(*break_time))
        driver_breaks = DriverBreaksHelper.clean_breaks(driver_breaks, start_transit, end_transit, break_duration)
        return [
            DriverBreak(
                current_context.zero_time + timedelta(seconds=item.start_time),
                current_context.zero_time + timedelta(seconds=item.end_time),
            ) for item in driver_breaks
        ]

    @staticmethod
    def clean_breaks(driver_breaks: Iterable[Break], start_transit: int, end_transit: int, break_duration: int) \
            -> List[Break]:
        driver_breaks = DriverBreaksHelper.merge_intersected(driver_breaks)
        breaks_sum = sum(map(attrgetter('duration'), driver_breaks))
        while breaks_sum > break_duration:
            driver_breaks.pop()
            breaks_sum = sum(map(attrgetter('duration'), driver_breaks))
        time_left = break_duration - breaks_sum
        for _ in range(5):
            if time_left == 0:
                break
            driver_breaks = DriverBreaksHelper.additional_break_time(
                driver_breaks, start_transit, end_transit, time_left
            )
            driver_breaks = DriverBreaksHelper.merge_intersected(driver_breaks)
            breaks_sum = sum(map(attrgetter('duration'), driver_breaks))
            time_left = break_duration - breaks_sum
        return driver_breaks

    @staticmethod
    def break_inside_transit(break_setting: VehicleBreak, start_transit: int, end_transit: int):
        return break_setting.start_time >= start_transit and break_setting.end_time <= end_transit

    @staticmethod
    def break_on_transit_start(break_setting: VehicleBreak, start_transit: int):
        return break_setting.start_time < start_transit <= (break_setting.start_time + break_setting.diff_allowed)

    @staticmethod
    def break_on_transit_end(break_setting: VehicleBreak, end_transit: int):
        return break_setting.end_time > end_transit >= (break_setting.end_time - break_setting.diff_allowed)

    @staticmethod
    def merge_intersected(breaks: Iterable[Break]) -> List[Break]:
        """
        If some driver break intervals intersect, then we need to merge them.

        [Break(0, 100), Break(90, 110), Break(130, 150), Break(120, 160)] -> [Break(0, 110), Break(120, 160)]
        """
        result_breaks: List[Break] = list(breaks)
        for _ in range(10):
            changed = False
            current_breaks = list(result_breaks)
            result_breaks = []
            for driver_break in current_breaks:
                append_break = driver_break
                for result_break in result_breaks:
                    if driver_break.intersects(result_break):
                        append_break = None
                        changed = True
                        result_break.start_time = min(driver_break.start_time, result_break.start_time)
                        result_break.end_time = max(driver_break.end_time, result_break.end_time)
                if append_break is not None:
                    result_breaks.append(append_break)
            if not changed:
                break
        return result_breaks

    @staticmethod
    def additional_break_time(breaks: Iterable[Break], start_transit: int, end_transit: int, break_time_left: int) \
            -> List[Break]:
        """
        Finds how to extend driver break intervals with break_time_left.
        Can't be earlier than start_transit and later than end_transit.

        :param break_time_left: Time in seconds that should be added to intervals.
        """
        result_breaks = []
        for driver_break in breaks:
            if break_time_left == 0:
                result_breaks.append(driver_break)
                continue
            if driver_break.start_time > start_transit:
                if driver_break.start_time - break_time_left > start_transit:
                    driver_break.start_time -= break_time_left
                    break_time_left = 0
                else:
                    break_time_left -= driver_break.start_time - start_transit
                    driver_break.start_time = start_transit
            if break_time_left == 0:
                result_breaks.append(driver_break)
                continue
            if driver_break.end_time < end_transit:
                if driver_break.end_time + break_time_left < end_transit:
                    driver_break.end_time += break_time_left
                    break_time_left = 0
                else:
                    break_time_left -= end_transit - driver_break.end_time
                    driver_break.end_time = end_transit
            result_breaks.append(driver_break)
        return result_breaks
