import asyncio
import itertools
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from operator import itemgetter

import googlemaps.exceptions

from route_optimisation.engine.dima import dima_cache, set_dima_cache
from route_optimisation.engine.ortools.distance_matrix.matrix import DistanceMatrix
from route_optimisation.engine.ortools.distance_matrix.utils import LocationsList, take_matrix_value
from routing.google import GoogleClient, merchant_registry


class DistanceMatrixComponent(object):
    def __init__(self, locations, base_graph):
        self.locations = LocationsList(locations)
        self.base_graph = base_graph
        self.used_vertices = set()
        self.matrix = DistanceMatrix()
        self.not_compatible = set()
        self.failed_indexes = []

    def _get_route_chains(self, max_chain_length=27):
        current_chain = []
        for vertex in self.base_graph.walk_vertices():
            current_chain.append(vertex)
            if len(current_chain) == max_chain_length:
                yield current_chain
                current_chain = [vertex]
        if len(current_chain) > 1:
            yield current_chain

    def _fill_distance_matrix_with_merchant(self, chain_of_indexes, merchant, dima_cache_obj):
        with GoogleClient.track_merchant(merchant), set_dima_cache(dima_cache_obj):
            return self._fill_distance_matrix(chain_of_indexes)

    def _fill_distance_matrix(self, chain_of_indexes):
        chain_of_points = self.locations.filter_from_indices(chain_of_indexes)
        try:
            routes = chain_of_points.call_directions()
            if len(routes) == 0:
                return False, chain_of_indexes
            for from_, to_, leg in zip(chain_of_indexes[:-1], chain_of_indexes[1:], routes[0]['legs']):
                self.fill_edge(from_, to_, leg)
        except googlemaps.exceptions.ApiError as api_error:
            if api_error.status != 'MAX_ROUTE_LENGTH_EXCEEDED' or len(chain_of_indexes) < 3:
                raise
            result_0, result_1 = self._binary_fill_distance_matrix(chain_of_indexes)
            if not (result_0[0] and result_1[0]):
                return False, chain_of_indexes
        except (googlemaps.exceptions.Timeout, googlemaps.exceptions.TransportError):
            return False, chain_of_indexes
        return True, None

    def _binary_fill_distance_matrix(self, chain_of_indexes):
        middle = len(chain_of_indexes) // 2
        chain_0, chain_1 = chain_of_indexes[:middle+1], chain_of_indexes[middle:]
        result_0 = self._fill_distance_matrix(chain_0)
        result_1 = self._fill_distance_matrix(chain_1)
        return result_0, result_1

    async def fill_distance_matrix(self):
        merchant = merchant_registry.get_merchant()
        dima_cache_obj = dima_cache.get_handler()
        with ThreadPoolExecutor(max_workers=20) as executor:
            loop = asyncio.get_event_loop()
            tasks = [
                loop.run_in_executor(
                    executor, self._fill_distance_matrix_with_merchant, chain_of_indexes, merchant, dima_cache_obj,
                )
                for chain_of_indexes in self._get_route_chains()
            ]
            for res in await asyncio.gather(*tasks):
                if res[0] is False:
                    self.failed_indexes.append(res[1])

    def from_cache(self):
        for chain_of_indexes in self._get_route_chains(max_chain_length=100):
            chain_of_points = self.locations.filter_from_indices(chain_of_indexes)
            pairs_of_points = []
            for from_, to_ in zip(chain_of_points[:-1], chain_of_points[1:]):
                pairs_of_points.append((from_, to_))
            cached_legs = dima_cache.get_elements(pairs_of_points)
            for from_, to_, leg in zip(chain_of_indexes[:-1], chain_of_indexes[1:], cached_legs):
                if leg is not None:
                    self.fill_edge(from_, to_, leg, add_to_used=False)

    def fill_edge(self, from_, to_, leg, add_to_used=True):
        if add_to_used:
            self.used_vertices.update([from_, to_])
        self.base_graph.remove_edge(from_, to_)
        self.matrix[(self.locations[from_], self.locations[to_])] = take_matrix_value(leg)

    def fill_zero_values(self):
        for location in self.locations.filter_from_indices(self.base_graph.all_vertices):
            self.matrix[(location, location)] = dict(zip(['duration', 'distance'], [0, 0]))

    def merge_with(self, other):
        self_vertices = self.base_graph.all_vertices
        other_vertices = other.base_graph.all_vertices
        for v in self_vertices:
            for u in other_vertices:
                self.base_graph.add_full_edge(v, u)
        self.not_compatible.update(other.not_compatible)
        self.matrix.update(other.matrix)

    def is_compatible_for_merge(self, other):
        if self.not_compatible.intersection(other.base_graph.all_vertices):
            return False
        fr_, to_ = self.base_graph.all_vertices[0], other.base_graph.all_vertices[0]
        try:
            elem = dima_cache.single_dima_element(self.locations[fr_], self.locations[to_], track_merchant=True)
        except googlemaps.exceptions.Timeout:
            elem = None
        return elem is not None and elem['status'] == 'OK'

    def get_used_locations(self):
        return [location for i, location in enumerate(self.locations) if i in self.base_graph.all_vertices]

    def find_most_failed_indexes(self, take_n_first=27):
        fails_counter = defaultdict(int)
        for indexes in self.failed_indexes:
            for index in set(indexes):
                fails_counter[index] += 1
        most_failed = reversed(sorted((v, k) for k, v in fails_counter.items()))
        return map(itemgetter(1), itertools.islice(most_failed, take_n_first))
