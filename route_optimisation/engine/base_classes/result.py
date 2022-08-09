import copy
import importlib
from operator import attrgetter
from typing import Dict, List

from django.utils import dateparse


class Point:
    __slots__ = (
        'point_prototype', 'model_class', 'point_kind', 'location', 'previous',
        'service_time', 'driving_time', 'distance',
        'start_time', 'end_time', 'utilized_capacity',
        'polyline',
    )

    def __init__(
            self, point_prototype, model_class, point_kind, location, previous,
            service_time, driving_time, distance,
            start_time, end_time, utilized_capacity,
            polyline,
    ):
        self.point_prototype = point_prototype
        self.model_class = model_class
        self.point_kind = point_kind
        self.location = location
        self.previous = previous
        self.service_time = service_time
        self.driving_time = driving_time
        self.distance = distance
        self.start_time = start_time
        self.end_time = end_time
        self.utilized_capacity = utilized_capacity
        self.polyline = polyline

    def __str__(self):
        return f'Point {self.point_kind}'

    def to_dict(self):
        return {
            'point_prototype': self.point_prototype,
            'model_class': self.model_class.__name__ if self.model_class else None,
            'point_kind': self.point_kind,
            'location': self.location,
            'previous': None,
            'service_time': self.service_time,
            'driving_time': self.driving_time,
            'distance': self.distance,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'utilized_capacity': self.utilized_capacity,
            'polyline': self.polyline,
        }

    @classmethod
    def from_dict(cls, value):
        from merchant.models import Hub
        from route_optimisation.models import DriverRouteLocation
        from tasks.models import Order
        model_classes = {
            'Order': Order,
            'Hub': Hub,
            'DriverRouteLocation': DriverRouteLocation,
        }
        value['model_class'] = model_classes[value['model_class']] if value['model_class'] else None
        value['start_time'] = dateparse.parse_datetime(value['start_time'])
        value['end_time'] = dateparse.parse_datetime(value['end_time'])
        return cls(**value)


class DriverTour:
    __slots__ = ('points', 'driving_time', 'full_time', 'driving_distance', 'ratio_to_min', 'ratio_to_avg',)

    def __init__(self, points: List[Point], driving_time, full_time, driving_distance):
        self.points: List[Point] = points
        self.driving_time = driving_time
        self.full_time = full_time
        self.driving_distance = driving_distance
        self.ratio_to_min = 0
        self.ratio_to_avg = 0

    @property
    def start_time(self):
        if self.points:
            return min(map(attrgetter('start_time'), self.points)).timestamp()

    def to_dict(self):
        return {
            'points': [p.to_dict() for p in self.points],
            'driving_time': self.driving_time,
            'full_time': self.full_time,
            'driving_distance': self.driving_distance,
        }

    @classmethod
    def from_dict(cls, value):
        value['points'] = [Point.from_dict(p) for p in value['points']]
        return cls(**value)


class AssignmentResult:
    __slots__ = ('good', 'drivers_tours', 'skipped_orders', 'skipped_drivers', 'driving_time', 'driving_distance',
                 'exception_dict', )

    def __init__(self, drivers_tours, skipped_orders, driving_time, driving_distance, skipped_drivers,
                 good=True, exception_dict=None):
        self.good = good
        self.drivers_tours: Dict[int, DriverTour] = drivers_tours
        self.skipped_orders = skipped_orders
        self.skipped_drivers: set = skipped_drivers
        self.driving_time = driving_time
        self.driving_distance = driving_distance
        self.exception_dict = exception_dict

        if self.drivers_tours and len(self.drivers_tours) > 0:
            min_full_time = min(map(attrgetter('full_time'), self.drivers_tours.values()))
            avg_full_time = sum(map(attrgetter('full_time'), self.drivers_tours.values())) \
                / len(self.drivers_tours)
            for tour in self.drivers_tours.values():
                tour.ratio_to_min = tour.full_time/min_full_time
                tour.ratio_to_avg = (tour.full_time / avg_full_time) - 1

    @property
    def avg_start_time(self):
        values = list(filter(None, map(attrgetter('start_time'), self.drivers_tours.values())))
        return sum(values) / len(values)

    @classmethod
    def failed_assignment(cls, exc):
        exception_dict = {
            'exc_type': str(type(exc)),
            'exc_class': exc.__class__,
            'exc_str': str(exc),
        }
        return cls(None, None, None, None, None, good=False, exception_dict=exception_dict)

    def __str__(self):
        result = ''
        if len(self.drivers_tours) == 0:
            return result
        for driver, tour in self.drivers_tours.items():
            result += 'Driver_id: {:>10}; Tour points: {:>2}; Driving time: {:>6}({:^6})[{:^6}][{:^6}]; ' \
                      'Driving distance: {:>10}\n'\
                .format(driver, len(tour.points), tour.driving_time, tour.full_time,
                        round(tour.ratio_to_min, 2), round(tour.ratio_to_avg, 2),
                        tour.driving_distance)
        return result.strip()

    def to_dict(self):
        drivers_tours = {k: v.to_dict() for k, v in self.drivers_tours.items()}\
            if self.drivers_tours is not None else None
        exception_dict = None
        if self.exception_dict is not None:
            exception_dict = copy.copy(self.exception_dict)
            exception_dict['exc_class_module'] = exception_dict['exc_class'].__module__
            exception_dict['exc_class_name'] = exception_dict['exc_class'].__name__
            del exception_dict['exc_class']
        return {
            'good': self.good,
            'drivers_tours': drivers_tours,
            'skipped_orders': self.skipped_orders,
            'skipped_drivers': list(self.skipped_drivers) if self.skipped_drivers is not None else None,
            'driving_time': self.driving_time,
            'driving_distance': self.driving_distance,
            'exception_dict': exception_dict,
        }

    @classmethod
    def from_dict(cls, value):
        val = copy.deepcopy(value)
        val['drivers_tours'] = {k: DriverTour.from_dict(v) for k, v in val['drivers_tours'].items()} \
            if val['drivers_tours'] is not None else None
        val['skipped_drivers'] = set(val['skipped_drivers']) if val['skipped_drivers'] is not None else None
        if val['exception_dict']:
            exc_module = importlib.import_module(val['exception_dict'].pop('exc_class_module'))
            val['exception_dict']['exc_class'] = getattr(exc_module, val['exception_dict'].pop('exc_class_name'))
        return cls(**val)
