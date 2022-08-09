from typing import List

from route_optimisation.const import RoutePointKind
from route_optimisation.engine.base_classes.result import AssignmentResult
from route_optimisation.models.driver_route import DriverRoute, DriverRouteColorPicker

from ...exceptions import MoveOrdersError
from ...models import RoutePoint
from .base import OptimisationResult, ResultKeeper


class MoveOrdersResultKeeper(ResultKeeper):
    def prepare(self, result: AssignmentResult, **params) -> OptimisationResult:
        prepared_optimisation_result = super().prepare(result)
        prepared_route_info = prepared_optimisation_result.routes[0]
        route, points = prepared_route_info.route, prepared_route_info.points
        prepared_route_info.route, prepared_route_info.points = self.update_routes_points_info(route, points, **params)
        return prepared_optimisation_result

    def update_routes_points_info(self, route, points, moved_points=None, **params):
        raise NotImplementedError()


def point_unique(point):
    compared_fields = ('point_kind', 'point_object_id', 'point_content_type_id')
    return tuple(map(lambda _field: getattr(point, _field), compared_fields))


def is_same_points(point_one, point_two):
    compared_fields = ('point_kind', 'start_time', 'end_time') \
        if point_one.point_kind == RoutePointKind.BREAK \
        else ('point_kind', 'point_object_id', 'point_content_type_id')
    return all(map(lambda x: getattr(point_one, x) == getattr(point_two, x), compared_fields))


def is_same_locations(point_one, point_two):
    if point_one.point_kind != RoutePointKind.LOCATION:
        return False
    compared_fields = ('point_kind', 'point_content_type_id')
    same_locations = all(map(lambda x: getattr(point_one, x) == getattr(point_two, x), compared_fields)) \
        and point_one.point_object.location == point_two.point_object.location
    return same_locations


def update_points(points: List[RoutePoint], existing_moved_points: List[RoutePoint]):
    """
    Update `existing_moved_points` information with information from similar `points`.

    :param points: list of route points. It is preliminary results from engine. They are not presented in DB.
    :param existing_moved_points: list of route points. They are presented in DB. Should be updated with new information from `points`.
    :return: list with mix of `points` and `existing_moved_points` with updated information.
    """
    new_points = []
    fields_for_update = ('number', 'route', 'route_id', 'service_time', 'driving_time', 'distance',
                         'start_time', 'end_time', 'utilized_capacity', 'path_polyline')
    existing_points_dict = {point_unique(point): point for point in existing_moved_points}
    for point in points:
        if point.point_kind in (RoutePointKind.HUB, RoutePointKind.LOCATION, RoutePointKind.BREAK):
            new_points.append(point)
            continue
        existing_point = existing_points_dict.get(point_unique(point))
        if not existing_point:
            continue
        for field in fields_for_update:
            setattr(existing_point, field, getattr(point, field))
        new_points.append(existing_point)
        del existing_points_dict[point_unique(point)]
    if existing_points_dict:
        raise MoveOrdersError('Unhandled error occurred. One of points can not be moved to new route.')
    return new_points


class NewRouteOptimiseResultKeeper(MoveOrdersResultKeeper):
    def update_routes_points_info(self, route, points, moved_points=None, **params):
        assert moved_points
        return route, update_points(points, moved_points)


class NewAdvancedRouteOptimiseResultKeeper(MoveOrdersResultKeeper):
    def update_routes_points_info(self, route, points, moved_points=None, **params):
        assert moved_points
        color_picker = DriverRouteColorPicker()
        used_colors = (set(self.optimisation.source_optimisation.routes.all().values_list('color', flat=True))
                       | set(DriverRoute.objects.get_used_colors_for_date(route.driver, self.optimisation.day)))
        route.color = color_picker(used_colors)
        return route, update_points(points, moved_points)


class ExistingRouteOptimiseResultKeeper(MoveOrdersResultKeeper):
    fields_for_update = ('number', 'service_time', 'driving_time', 'distance',
                         'start_time', 'end_time', 'utilized_capacity', 'path_polyline')

    def update_routes_points_info(self, route, points, moved_points=None, target_route=None, **params):
        assert moved_points
        assert target_route
        new_points = []
        existing_moved_points_dict = {point_unique(point): point for point in moved_points}
        existing_route_points = list(target_route.points.all().order_by('number'))
        used_existing = set()
        for point in points:
            if point.point_kind == RoutePointKind.BREAK:
                new_points.append(point)
                continue
            used = False
            for existing in existing_route_points:
                if existing.id in used_existing:
                    continue
                if is_same_points(point, existing):
                    for field in self.fields_for_update:
                        setattr(existing, field, getattr(point, field))
                    new_points.append(existing)
                    used_existing.add(existing.id)
                    used = True
                    break
            if used:
                continue

            existing_moved_point = existing_moved_points_dict.get(point_unique(point))
            if not existing_moved_point:
                continue
            for field in self.fields_for_update:
                setattr(existing_moved_point, field, getattr(point, field))
            existing_moved_point.route = target_route
            new_points.append(existing_moved_point)
            del existing_moved_points_dict[point_unique(point)]

        if existing_moved_points_dict:
            raise MoveOrdersError('Unhandled error occurred. One of points can not be moved to existing route.')
        target_route.driving_distance = route.driving_distance
        target_route.driving_time = route.driving_time
        target_route.total_time = route.total_time
        target_route.start_time = route.start_time
        target_route.end_time = route.end_time
        return target_route, new_points
