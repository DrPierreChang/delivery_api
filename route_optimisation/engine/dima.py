import logging
import threading
from typing import Optional

from routing.google import GoogleClient

logger = logging.getLogger('radaro-dev')


class DistanceMatrixCache:
    def __init__(self, polylines=False):
        self.gmaps_client = GoogleClient()
        self.cache = None
        self.caching_params = {}
        self.polylines = polylines

    def cache_key(self, start, end):
        start = '%s,%s' % (start['lat'], start['lng'])
        end = '%s,%s' % (end['lat'], end['lng'])
        return '%s->%s' % (start, end)

    def single_dima_element(self, origin, destination, *args, **kwargs):
        if self._should_make_distance_matrix_request(origin, destination):
            gmaps_requester = self.gmaps_client.single_dima_element_with_polyline \
                if self.polylines else self.gmaps_client.single_dima_element
            # logger.debug(f'DIMA CACHE {gmaps_requester.__name__}() {origin}, {destination}, {args}, {kwargs}')
            response = gmaps_requester(origin, destination, *args, **kwargs)
            self._update_cache_after_distance_matrix(response, origin, destination)
        else:
            response = self._make_response_from_cache_distance_matrix(origin, destination)
        return response

    def pure_directions_request(self, origin, destination, waypoints=None, *args, **kwargs):
        points = [origin] + (waypoints or []) + [destination]
        if self._should_make_directions_request(points):
            # logger.debug(f'DIMA CACHE pure_directions(), {args}, {kwargs}')
            response = self.gmaps_client.pure_directions_request(origin, destination, waypoints=waypoints, *args,
                                                                 **kwargs)
            self._update_cache_after_directions(response, points)
        else:
            response = self._make_response_from_cache(points)
        return response

    def get_elements(self, pairs_of_locations, *args, **kwargs):
        keys = [self.cache_key(from_, to_) for from_, to_ in pairs_of_locations]
        cache_result = self.cache.get_many(keys)
        return [
            self.make_leg_object(cache_result[key])
            if (key in cache_result and self.can_make_leg_object(cache_result[key]))
            else None
            for key in keys
        ]

    def get_element(self, from_, to_, *args, **kwargs):
        cache_result = self.cache.get(self.cache_key(from_, to_))
        if cache_result and self.can_make_leg_object(cache_result):
            return self.make_leg_object(cache_result)

    def make_leg_object(self, cache_object) -> dict:
        step = {}
        polyline_value = self.cached_polyline_value(cache_object)
        if polyline_value is not None:
            step['polyline'] = {'points': polyline_value}
        return {
            'distance': {'value': self.cached_distance_value(cache_object)},
            'duration': {'value': self.cached_duration_value(cache_object)},
            'steps': [step],
        }

    def can_make_leg_object(self, cache_object):
        if self.is_cache_distance_matrix_zero_result(cache_object):
            return False
        if self.polylines and not self.cached_polyline_value(cache_object):
            return False
        return True

    def cached_distance_value(self, cache_object) -> int:
        raise NotImplementedError()

    def cached_duration_value(self, cache_object) -> int:
        raise NotImplementedError()

    def cached_polyline_value(self, cache_object) -> Optional[str]:
        raise NotImplementedError()

    def is_cache_distance_matrix_zero_result(self, cache_object) -> bool:
        return self.status_cache_key in cache_object and cache_object[self.status_cache_key] == 'ZERO_RESULTS'

    @property
    def distance_cache_key(self):
        raise NotImplementedError()

    @property
    def duration_cache_key(self):
        raise NotImplementedError()

    @property
    def start_point_cache_key(self):
        raise NotImplementedError()

    @property
    def end_point_cache_key(self):
        raise NotImplementedError()

    @property
    def status_cache_key(self):
        raise NotImplementedError()

    @property
    def polyline_cache_key(self):
        raise NotImplementedError()

    def _should_make_directions_request(self, points):
        keys = []
        for item in range(len(points) - 1):
            start, end = points[item:item + 2]
            keys.append(self.cache_key(start, end))
        cache_result = self.cache.get_many(keys)
        if self.polylines:
            for value in cache_result.values():
                if self.polyline_cache_key not in value:
                    return True
        return len(cache_result) != len(keys)

    def _update_cache_after_directions(self, response, points):
        directions = []
        for route in response:
            for leg, point_from, point_to in zip(route['legs'], points[:-1], points[1:]):
                leg_result = {
                    self.distance_cache_key: leg['distance']['value'],
                    self.duration_cache_key: leg['duration']['value'],
                    self.start_point_cache_key: point_from,
                    self.end_point_cache_key: point_to,
                }
                if self.polylines:
                    leg_result[self.polyline_cache_key] = self.gmaps_client.glue_polylines(leg['steps'])
                directions.append(leg_result)
        return directions

    def _make_response_from_cache(self, points):
        keys = [self.cache_key(start, end) for start, end in zip(points[:-1], points[1:])]
        cached_objects = self.cache.get_many(keys)
        for cache_object in cached_objects.values():
            if not self.can_make_leg_object(cache_object):
                return []
        legs = [self.make_leg_object(cached_objects[key]) for key in keys]
        return [{'legs': legs}]

    def _should_make_distance_matrix_request(self, origin, destination):
        from_cache = self.cache.get(self.cache_key(origin, destination))
        if from_cache is None:
            return True
        if self.polylines and self.polyline_cache_key not in from_cache:
            return True
        return False

    def _update_cache_after_distance_matrix(self, response, origin, destination):
        for_cache = None
        if response['status'] == 'OK':
            for_cache = {
                self.distance_cache_key: response['distance']['value'],
                self.duration_cache_key: response['duration']['value'],
            }
            if self.polylines:
                for_cache[self.polyline_cache_key] = self.gmaps_client.glue_polylines(response['steps'])
        elif response['status'] == 'ZERO_RESULTS':
            for_cache = {self.status_cache_key: 'ZERO_RESULTS'}
        if for_cache is not None:
            key = self.cache_key(origin, destination)
            self.cache.set(key, for_cache, **self.caching_params)

    def _make_response_from_cache_distance_matrix(self, origin, destination):
        cache_object = self.cache.get(self.cache_key(origin, destination))
        if self.is_cache_distance_matrix_zero_result(cache_object):
            return {'status': 'ZERO_RESULTS'}
        else:
            step = {}
            polyline_value = self.cached_polyline_value(cache_object)
            if polyline_value is not None:
                step['polyline'] = {'points': polyline_value}
            return {
                'distance': {'value': self.cached_distance_value(cache_object)},
                'duration': {'value': self.cached_duration_value(cache_object)},
                'steps': [step],
                'status': 'OK'
            }

    def ensure_chain_cashed(self, location_chain, *req_args, **req_kwargs):
        for locations in self._get_chains(location_chain):
            self.pure_directions_request(locations[0], locations[-1], locations[1:-1], *req_args, **req_kwargs)

    @staticmethod
    def _get_chains(locations, max_chain_length=27):
        current_chain = []
        for loc in locations:
            current_chain.append(loc)
            if len(current_chain) == max_chain_length:
                yield current_chain
                current_chain = [loc]
        if len(current_chain) > 1:
            yield current_chain


class set_dima_cache:
    def __init__(self, handler):
        self.handler = handler

    def __enter__(self):
        dima_cache.set_handler(self.handler)

    def __exit__(self, exc_type, exc_val, exc_tb):
        dima_cache.set_handler(None)


class CurrentDiMaCacheKeeper(threading.local):
    def __init__(self):
        self._handler = None

    def set_handler(self, value):
        self._handler = value

    def get_handler(self):
        return self._handler

    def __getattr__(self, item):
        assert self._handler is not None, 'No Distance Matrix Cache set'
        assert hasattr(self._handler, item), 'Distance Matrix Cache have no "%s" attribute' % item
        return getattr(self._handler, item)


dima_cache = CurrentDiMaCacheKeeper()
