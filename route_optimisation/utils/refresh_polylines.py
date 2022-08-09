import logging

from route_optimisation.const import GOOGLE_API_REQUESTS_LIMIT
from route_optimisation.engine.dima import dima_cache, set_dima_cache
from route_optimisation.engine.events import set_event_handler
from route_optimisation.engine.ortools.context.init import LocationPointMap
from route_optimisation.engine.ortools.distance_matrix import DistanceMatrixBuilder
from route_optimisation.logging import EventType
from route_optimisation.models import DummyOptimisation, RoutePoint
from route_optimisation.optimisation_events import RadaroEventsHandler
from routing.context_managers import GoogleApiRequestsTracker
from routing.google import GoogleClient
from routing.utils import latlng_dict_from_str

logger = logging.getLogger('optimisation')


class LocationMap(dict):
    @staticmethod
    def _transform_key(key) -> str:
        if isinstance(key, dict):
            return '{lat},{lng}'.format(**key)
        return key

    def __setitem__(self, key, value):
        return super().__setitem__(self._transform_key(key), value)

    def __getitem__(self, item):
        return super().__getitem__(self._transform_key(item))


class MatrixForPolylines:
    @staticmethod
    def build(location_chains):
        unique_locations = MatrixForPolylines._handle_locations(location_chains)
        index_pairs = MatrixForPolylines._prepare_pairs(unique_locations, location_chains)
        builder = DistanceMatrixBuilder(unique_locations)
        builder.build_via_directions_api_by_pairs(index_pairs)

    @staticmethod
    def _handle_locations(location_chains):
        location_map = LocationPointMap()
        for chain in location_chains:
            for location in chain:
                location_map[location].append(location)
        return list(map(latlng_dict_from_str, location_map.keys()))

    @staticmethod
    def _prepare_pairs(unique_locations, location_chains):
        index_pairs = set()
        location_map = LocationMap()
        for index, location in enumerate(unique_locations):
            location_map[location] = index

        for chain in location_chains:
            index_chain = [location_map[location] for location in chain]
            for start_index, end_index in zip(index_chain[:-1], index_chain[1:]):
                if start_index != end_index:
                    index_pairs.add((start_index, end_index))
        return index_pairs


class RefreshPolylinesService:

    def __init__(self, optimisation):
        self.optimisation = optimisation

    def refresh_polylines(self, obj, distance_matrix_cache=None, event_handler=None):
        from route_optimisation.dima import RadaroDimaCache
        api_requests_tracker = GoogleApiRequestsTracker(limit=GOOGLE_API_REQUESTS_LIMIT)
        distance_matrix_cache = distance_matrix_cache or RadaroDimaCache(polylines=True)
        event_handler = event_handler or RadaroEventsHandler(self.optimisation)
        try:
            with GoogleClient.track_merchant(self.optimisation.merchant), api_requests_tracker, \
                    set_dima_cache(distance_matrix_cache), set_event_handler(event_handler):
                location_chains = self.get_location_chains(obj)
                MatrixForPolylines.build(location_chains)
                self.save_polylines(obj)
                logger.info(None, extra=dict(obj=self.optimisation, event=EventType.FILL_POLYLINES))
                return obj
        finally:
            opt = self.optimisation.source_optimisation \
                if isinstance(self.optimisation, DummyOptimisation) else self.optimisation
            opt.backend.track_api_requests_stat(api_requests_tracker)

    def get_location_chains(self, obj):
        raise NotImplementedError()

    def save_polylines(self, obj):
        raise NotImplementedError()


class PostProcessingRefreshPolylines(RefreshPolylinesService):

    def get_location_chains(self, result):
        location_chains = []
        for tour in result.drivers_tours.values():
            location_chains.append([point.location for point in tour.points if point.location is not None])
        return location_chains

    def save_polylines(self, result):
        for tour in result.drivers_tours.values():
            points = [point for point in tour.points if point.location is not None]
            for start_point, end_point in zip(points[:-1], points[1:]):
                if start_point.location == end_point.location:
                    polyline = ''
                else:
                    elem = dima_cache.get_element(start_point.location, end_point.location)
                    polyline = GoogleClient.glue_polylines(elem.get('steps', []))

                start_point.polyline = polyline
                end_point.polyline = None


class OptimisationRefreshPolylines(RefreshPolylinesService):

    def get_location_chains(self, routes_list):
        location_chains = []
        for route in routes_list:
            locations = [
                one_point.point_location.dict_coordinates
                for one_point in route.points.all().order_by('number')
                if one_point.active
            ]
            location_chains.append(locations)
        return location_chains

    def save_polylines(self, routes_list):
        points_list = []

        for route in routes_list:
            active_route_path = False
            route_points_list = []
            for point in route.points.all().order_by('number'):
                if point.active:
                    route_points_list.append(point)
                    active_route_path = True
                else:
                    if active_route_path:
                        point.path_polyline = None
                        point.next_point = None
                        points_list.append(point)

            points_list.extend(route_points_list)
            for start_point, end_point in zip(route_points_list[:-1], route_points_list[1:]):
                if start_point.point_location.dict_coordinates == end_point.point_location.dict_coordinates:
                    polyline = ''
                else:
                    elem = dima_cache.get_element(
                        start_point.point_location.dict_coordinates,
                        end_point.point_location.dict_coordinates,
                    )
                    polyline = GoogleClient.glue_polylines(elem.get('steps', []))

                start_point.next_point = end_point
                start_point.path_polyline = polyline
                end_point.path_polyline = None

        RoutePoint.objects.bulk_update(points_list, fields=['path_polyline', 'next_point'])
