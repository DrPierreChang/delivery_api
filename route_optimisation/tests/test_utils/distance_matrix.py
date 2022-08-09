import json
import os
import time
from threading import RLock
from typing import Optional

from django.conf import settings
from django.core.cache import caches

from route_optimisation.dima import RadaroDimaCache
from route_optimisation.engine.dima import DistanceMatrixCache
from routing.utils import get_geo_distance

dima_lock = RLock()


class LocalCacheDiMa(RadaroDimaCache):
    def __init__(self):
        super().__init__()
        self.cache = caches['test_optimisation']


class CacheLikeAdapter(dict):
    def get_many(self, keys):
        return {key: self[key] for key in keys if key in self}

    def set(self, key, value):
        self[key] = value


class TestDiMaCache(DistanceMatrixCache):
    def __init__(self, cache_file_name=None, polylines=False):
        super().__init__(polylines)
        cache_file_name = cache_file_name or ('dima_cache_polylines.json' if polylines else 'dima_cache.json')
        self.cache_file_path = os.path.join(settings.BASE_DIR, 'route_optimisation', 'tests', 'test_utils',
                                            cache_file_name)
        with open(self.cache_file_path) as test_data_file:
            distance_matrix = json.load(test_data_file)
        self.cache = CacheLikeAdapter(distance_matrix)
        self.counter = 0

    def save_distance_matrix(self, force=False, wait=True):
        with dima_lock:
            self.counter += 1
            if self.counter <= 100 and not force:
                return
            if self.counter == 0:
                return
            self.counter = 0
            print(f'[{self.__class__.__name__}] SAVE DIMA. Do not use KeyboardInterrupt now!')
            with open(self.cache_file_path, 'w') as test_data_file:
                json.dump(self.cache, test_data_file)
            print(f'[{self.__class__.__name__}] SAVED DIMA')
            if wait:
                print('...waiting 3 seconds for possible KeyboardInterrupt')
                time.sleep(3)

    def _update_cache_after_directions(self, response, points):
        directions = super()._update_cache_after_directions(response, points)
        with dima_lock:
            for direction in directions:
                start, end = direction.pop('start'), direction.pop('end')
                key = self.cache_key(start, end)
                self.cache[key] = direction
        self.save_distance_matrix()

    def _update_cache_after_distance_matrix(self, response, origin, destination):
        with dima_lock:
            super(TestDiMaCache, self)._update_cache_after_distance_matrix(response, origin, destination)
        self.save_distance_matrix()

    def cached_distance_value(self, cache_object):
        return cache_object.get('distance', cache_object.get(self.distance_cache_key))

    def cached_duration_value(self, cache_object):
        return cache_object.get('duration', cache_object.get(self.duration_cache_key))

    def cached_polyline_value(self, cache_object) -> Optional[str]:
        return cache_object.get('polyline', cache_object.get(self.polyline_cache_key, None))

    @property
    def distance_cache_key(self):
        return 'di'

    @property
    def duration_cache_key(self):
        return 'du'

    @property
    def start_point_cache_key(self):
        return 'start'

    @property
    def end_point_cache_key(self):
        return 'end'

    @property
    def status_cache_key(self):
        return 'st'

    @property
    def polyline_cache_key(self):
        return 'p'


class FakeCacheAdapter:
    def get_many(self, keys):
        return {key: self[key] for key in keys}

    def __getitem__(self, item):
        (start_lng, start_lat), (end_lng, end_lat) = item
        distance = get_geo_distance(*map(float, (start_lng, start_lat, end_lng, end_lat)))
        return {
            'distance': int(distance),
            'duration': int(distance / 14. * 1.),
        }

    def get(self, key):
        return self[key]

    def set(self, key, value):
        pass


class TestFakeDiMaCache(DistanceMatrixCache):
    def __init__(self):
        super().__init__()
        self.cache = FakeCacheAdapter()

    def cache_key(self, start, end):
        return (start['lng'], start['lat']), (end['lng'], end['lat'])

    def cached_distance_value(self, cache_object) -> int:
        return cache_object[self.distance_cache_key]

    def cached_duration_value(self, cache_object) -> int:
        return cache_object[self.duration_cache_key]

    def cached_polyline_value(self, cache_object) -> Optional[str]:
        return None

    @property
    def distance_cache_key(self):
        return 'distance'

    @property
    def duration_cache_key(self):
        return 'duration'

    @property
    def start_point_cache_key(self):
        return 'start'

    @property
    def end_point_cache_key(self):
        return 'end'

    @property
    def status_cache_key(self):
        return 'status'

    @property
    def polyline_cache_key(self):
        return 'polyline'
