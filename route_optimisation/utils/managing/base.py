from datetime import datetime, timedelta
from operator import attrgetter
from typing import List, Optional

from route_optimisation.const import RoutePointKind
from route_optimisation.engine.base_classes.parameters import DriverBreak
from route_optimisation.engine.dima import dima_cache
from route_optimisation.models import DriverRoute, DummyOptimisation, RouteOptimisation, RoutePoint
from route_optimisation.utils.breaks import ManualBreak, ManualBreakInDriverRoute, Part
from routing.google import GoogleClient
from routing.utils import latlng_dict


class MoveOrdersType:
    NEW_SOLO = 'new_solo'
    NEW_ADVANCED = 'new_advanced'
    EXISTING_ADVANCED = 'existing_advanced'


class MovingPreliminaryResult:
    def __init__(self, source_route: DriverRoute, result_source_points: List[RoutePoint],
                 target_route: DriverRoute, result_target_points: List[RoutePoint],
                 dummy_optimisation: Optional[DummyOptimisation] = None,
                 target_optimisation: Optional[RouteOptimisation] = None):
        self.source_route = source_route
        self.result_source_points = result_source_points
        self.target_route = target_route
        self.result_target_points = result_target_points
        self.dummy_optimisation = dummy_optimisation
        self.target_optimisation = target_optimisation


def update_route_from_updated_points(route: DriverRoute, updated_points: List[RoutePoint]):
    route.start_time = updated_points[0].start_time
    route.end_time = updated_points[-1].end_time
    route.total_time = int((route.end_time - route.start_time).total_seconds())
    route.driving_time = sum(map(attrgetter('driving_time'), updated_points))
    route.driving_distance = sum(map(attrgetter('distance'), updated_points))


def update_points(route: DriverRoute, points_sequence: List[RoutePoint]):
    locations = list(filter(None, map(latlng_location, points_sequence)))
    dima_cache.ensure_chain_cashed(locations, track_merchant=True)
    result = UpdatePointsHelper(route, points_sequence).get_updated_points_sequence()
    points_sequence.clear()
    points_sequence.extend(result)


class UpdatePointsHelper:
    def __init__(self, route: DriverRoute, points_sequence: List[RoutePoint]):
        self.route = route
        self.use_capacity = route.optimisation.optimisation_options.get('use_vehicle_capacity', False)
        engine_params = route.optimisation.backend.get_params_for_engine()
        existing_params = list(filter(lambda driver: driver.id == route.driver_id, engine_params.drivers))
        self.breaks = None
        if existing_params:
            self.breaks = existing_params[0].breaks
        else:
            from route_optimisation.utils.validation.options_serializers import DriverSerializer
            breaks = DriverSerializer(instance=route.driver, context={'optimisation': route.optimisation})\
                .get_breaks(route.driver)
            self.breaks = [DriverBreak(**driver_break) for driver_break in breaks] if breaks else None
        self.breaks_handler = None
        if self.breaks:
            self.breaks_handler = ManagingManualBreakInDriverRoute(route, points_sequence, self.breaks)
        self.points_sequence = points_sequence

    def get_updated_points_sequence(self) -> List[RoutePoint]:
        if self.breaks_handler is None:
            return self._from_route_points(self.points_sequence)
        return self._from_parts(self.breaks_handler.get_parts_with_breaks())

    def _from_parts(self, parts: List[Part]) -> List[RoutePoint]:
        result = []
        for part in parts:
            if part.kind == Part.SERVICE:
                part.point.start_time = self.breaks_handler.seconds_relative_to_datetime(part.start)
                part.point.end_time = self.breaks_handler.seconds_relative_to_datetime(part.end)
                result.append(part.point)
            elif part.kind == Part.TRANSIT:
                for driver_break in part.breaks:
                    point = RoutePoint(
                        number=None, route=self.route, point_kind=RoutePointKind.BREAK,
                        service_time=driver_break.end_time - driver_break.start_time,
                        driving_time=0, distance=0, path_polyline=None, utilized_capacity=None,
                        start_time=self.breaks_handler.seconds_relative_to_datetime(driver_break.start_time),
                        end_time=self.breaks_handler.seconds_relative_to_datetime(driver_break.end_time),
                    )
                    result.append(point)

        return self._from_route_points(result, update_times=False)

    def _from_route_points(self, points_sequence: List[RoutePoint], update_times=True) -> List[RoutePoint]:
        points_sequence[0].utilized_capacity = start_capacity(points_sequence) if self.use_capacity else 0
        previous_point, previous_point_with_location = None, None
        for idx, point in enumerate(points_sequence):
            point.number = idx + 1

            if previous_point_with_location is not None and point.point_kind != RoutePointKind.BREAK:
                cached = dima_cache.get_element(latlng_location(previous_point_with_location), latlng_location(point))
                point.driving_time = cached['duration']['value']
                point.distance = cached['distance']['value']
                point.path_polyline = GoogleClient.glue_polylines(cached.get('steps', []))

            if previous_point is not None:
                point.utilized_capacity = (previous_point.utilized_capacity + point_capacity(point)) \
                    if self.use_capacity else 0
                if update_times:
                    point.start_time = previous_point.end_time + timedelta(seconds=point.driving_time)
                    point.end_time = point.start_time + timedelta(seconds=point.service_time)

            previous_point = point
            if point.point_kind != RoutePointKind.BREAK:
                previous_point_with_location = point

        return list(points_sequence)


class ManagingManualBreakInDriverRoute(ManualBreakInDriverRoute):
    def __init__(self, route: DriverRoute, points_sequence: List[RoutePoint], breaks: List[DriverBreak]):
        timezone = route.optimisation.merchant.timezone
        day = route.optimisation.day
        self.day_zero = timezone.localize(datetime.combine(day, datetime.min.time()))
        parts = self._get_route_parts(points_sequence, timezone)
        manual_breaks: List[ManualBreak] = [
            ManualBreak(
                self.str_time_to_seconds(b.start_time),
                self.str_time_to_seconds(b.end_time),
                b.diff_allowed * 60
            ) for b in breaks
        ]
        super().__init__(parts, manual_breaks)

    def _get_route_parts(self, points_sequence: List[RoutePoint], timezone) -> List[Part]:
        parts: List[Part] = []
        previous_point = points_sequence[0]
        cumul_time = self.datetime_to_seconds_relative(previous_point.end_time, timezone)
        parts.append(Part(cumul_time, cumul_time, Part.SERVICE, previous_point))
        for point in points_sequence[1:]:
            _start = cumul_time
            from_location, to_location = latlng_location(previous_point), latlng_location(point)
            cached = dima_cache.get_element(from_location, to_location)
            driving_time = cached['duration']['value']
            cumul_time += driving_time
            parts.append(Part(_start, cumul_time, Part.TRANSIT, point))
            _start = cumul_time
            cumul_time += point.service_time
            parts.append(Part(_start, cumul_time, Part.SERVICE, point))
            previous_point = point
        return parts

    def datetime_to_seconds_relative(self, t, timezone):
        return int((t.astimezone(timezone) - self.day_zero).total_seconds())

    def seconds_relative_to_datetime(self, t):
        return self.day_zero + timedelta(seconds=t)

    @staticmethod
    def str_time_to_seconds(t):
        hour, minutes, seconds = list(map(int, t.split(':')))
        return hour*3600 + minutes*60 + seconds


def start_capacity(points_sequence):
    return abs(sum(map(point_capacity, points_sequence)))


def point_capacity(point):
    if point.point_kind == RoutePointKind.PICKUP:
        return 1 if point.point_object.capacity is None else point.point_object.capacity
    elif point.point_kind == RoutePointKind.DELIVERY:
        order = point.point_object
        if order.is_concatenated_order:
            capacity = sum(
                (1 if pickup_capacity is None else pickup_capacity)
                for pickup_capacity
                in order.orders.all().exclude(pickup_address_id__isnull=True).values_list('capacity', flat=True)
            )
        else:
            capacity = 1 if order.capacity is None else order.capacity
        return -1 * capacity
    return 0


def latlng_location(point: RoutePoint):
    return point.point_location and latlng_dict(point.point_location.coordinates)
