from typing import Optional

from django.core.cache import caches

import googlemaps.convert

from route_optimisation.engine.dima import DistanceMatrixCache


class RadaroDimaCache(DistanceMatrixCache):
    CACHE_TIMEOUT = 24 * 60 * 60  # 1 day

    def __init__(self, polylines=False):
        super().__init__(polylines=polylines)
        self.cache = caches['optimisation']
        self.caching_params = {'timeout': self.CACHE_TIMEOUT}

    def cache_key(self, start, end):
        # Ensure lat/lng is float, not string
        start = {key: float(value) for key, value in start.items()}
        end = {key: float(value) for key, value in end.items()}
        # Cache key will contain encoded start/end locations as polyline
        return 'rdr-dima-%s' % googlemaps.convert.encode_polyline((start, end))

    def _update_cache_after_directions(self, response, points):
        directions = super()._update_cache_after_directions(response, points)
        for_cache = {}
        for direction in directions:
            key = self.cache_key(direction.pop(self.start_point_cache_key), direction.pop(self.end_point_cache_key))
            # Each key-value pair uses ~160-200 bytes memory of redis cache
            for_cache[key] = direction
        self.cache.set_many(for_cache, **self.caching_params)

    def cached_distance_value(self, cache_object):
        return cache_object[self.distance_cache_key]

    def cached_duration_value(self, cache_object):
        return cache_object[self.duration_cache_key]

    def cached_polyline_value(self, cache_object) -> Optional[str]:
        return cache_object.get(self.polyline_cache_key, None)

    @property
    def distance_cache_key(self):
        return 'm'

    @property
    def duration_cache_key(self):
        return 's'

    @property
    def start_point_cache_key(self):
        return 'f'

    @property
    def end_point_cache_key(self):
        return 't'

    @property
    def status_cache_key(self):
        return 'a'

    @property
    def polyline_cache_key(self):
        return 'p'
