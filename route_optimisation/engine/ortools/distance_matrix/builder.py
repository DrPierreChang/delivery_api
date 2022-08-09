import asyncio
from collections import defaultdict
from operator import attrgetter
from typing import List

import googlemaps.exceptions

from route_optimisation.engine.dima import dima_cache
from route_optimisation.engine.events import event_handler

from .component import DistanceMatrixComponent
from .graph import Graph
from .matrix import DistanceMatrix
from .utils import EnsureEventLoopExists, LocationsList, take_matrix_value


class DistanceMatrixBuilder(object):
    def __init__(self, locations):
        self.locations = LocationsList(locations)
        self.components: List[DistanceMatrixComponent] = []
        self._cache_matrix = DistanceMatrix()

    def _init_components(self):
        base_graph = Graph.completed_directed_graph(list(range(len(self.locations))))
        self.components.append(DistanceMatrixComponent(self.locations, base_graph))

    def split_points_on_components(self):
        self._init_components()
        self._split_points(list(range(len(self.locations))))

    def build_via_directions_api(self):
        self._init_components()
        self._build()

    def _init_components_by_pairs(self, pairs):
        base_graph = Graph.pair_filled_directed_graph(list(range(len(self.locations))), pairs)
        self.components.append(DistanceMatrixComponent(self.locations, base_graph))

    def build_via_directions_api_by_pairs(self, pairs):
        self._init_components_by_pairs(pairs)
        self._build()

    def complete_existing_matrix(self, matrix):
        base_graph = Graph.completed_directed_graph(list(range(len(self.locations))))
        for from_index, from_point in enumerate(self.locations):
            for to_index, to_point in enumerate(self.locations):
                elem = (from_point, to_point)
                if matrix.get(elem, None):
                    base_graph.remove_edge(from_index, to_index)
        component = DistanceMatrixComponent(self.locations, base_graph)
        component.matrix = matrix
        self.components.append(component)
        self._build()

    @property
    def _has_more_edges(self):
        return any(map(attrgetter('base_graph.has_edges'), self.components))

    def _build(self):
        self._fill_from_cache()
        edges_count_history = [self._edges_count]
        for _ in range(10):
            if not self._has_more_edges:
                break
            self._run_filling_matrix()
            self._process_failed_points()
            if not self._has_more_edges:
                self._merge_components()
            self._fill_from_cache()

            current_value = self._edges_count
            decreasing_check_count = 3
            lower_than_at_least_one = any(
                (current_value < value) for value in edges_count_history[-decreasing_check_count:]
            )
            if len(edges_count_history) >= decreasing_check_count and not lower_than_at_least_one:
                event_handler.dev_msg(f'Count of edges is not decreasing, so break cycle. {edges_count_history}')
                break
            edges_count_history.append(current_value)

        for component in self.components:
            component.fill_zero_values()

    def _run_filling_matrix(self):
        for component in self.components:
            with EnsureEventLoopExists() as loop:
                future = asyncio.ensure_future(component.fill_distance_matrix())
                loop.run_until_complete(future)

    @property
    def _edges_count(self):
        return sum(map(attrgetter('base_graph.edges_count'), self.components))

    def _fill_from_cache(self):
        for component in self.components:
            component.from_cache()

    def _merge_components(self):
        new_components, i = [], 0
        while i < len(self.components):
            current_component, component_for_merge = self.components[i], None
            for component in self.components[i+1:]:
                if current_component.is_compatible_for_merge(component):
                    component_for_merge = component
                    break
            if component_for_merge:
                current_component.merge_with(component_for_merge)
                self.components.remove(component_for_merge)
            new_components.append(current_component)
            i += 1
        self.components = new_components

    def _process_failed_points(self):
        indexes_for_split = []
        for component in self.components:
            component_most_failed_indexes = list(component.find_most_failed_indexes())
            component.failed_indexes = []
            indexes_for_split.append(component_most_failed_indexes)
        for indexes in indexes_for_split:
            self._split_points(indexes)

    def _split_points(self, point_indexes):
        connected_indexes_list, separated_indexes_list = self._find_connected_locations(point_indexes), []
        for connected_indexes in connected_indexes_list:
            if not self._vertices_used_in_some_component(connected_indexes):
                separated_indexes_list.append(connected_indexes)
                for matrix_component in self.components:
                    matrix_component.base_graph.remove_vertices(connected_indexes)
        for indexes_list in separated_indexes_list:
            graph = Graph.completed_directed_graph(indexes_list)
            matrix_component = DistanceMatrixComponent(self.locations, graph)
            matrix_component.not_compatible.update(set(point_indexes).difference(indexes_list))
            self._fill_matrix_from_cache(indexes_list, matrix_component)
            matrix_component.from_cache()
            self.components.append(matrix_component)
        self.components = [c for c in self.components if c.base_graph.graph]

    def _vertices_used_in_some_component(self, vertices_indexes):
        for matrix_component in self.components:
            if set(vertices_indexes).intersection(matrix_component.used_vertices):
                return True
        return False

    def _find_connected_locations(self, chain_of_indexes):
        vertices = list(set(chain_of_indexes))
        graph = Graph.completed_undirected_graph(vertices)
        component_map = {vertex: vertex for vertex in vertices}
        while graph.has_edges:
            for from_vertex, to_vertex in graph.edges_gen():
                from_vertex, to_vertex = sorted([from_vertex, to_vertex])
                try:
                    elem = dima_cache.single_dima_element(
                        self.locations[from_vertex], self.locations[to_vertex], track_merchant=True
                    )
                except googlemaps.exceptions.Timeout:
                    elem = None
                if elem is None or elem['status'] == 'ZERO_RESULTS':
                    graph.remove_edge(from_vertex, to_vertex)
                elif elem['status'] == 'OK':
                    self._cache_matrix[(self.locations[from_vertex], self.locations[to_vertex])] \
                        = take_matrix_value(elem)
                    old_vertex_component = component_map[to_vertex]
                    component_map[to_vertex] = component_map[from_vertex]
                    for vertex, component_index in component_map.items():
                        if component_index == old_vertex_component:
                            component_map[vertex] = component_map[from_vertex]
                    graph = graph.join_vertices_in_one_vertex(from_vertex, to_vertex)
                    break

        components = defaultdict(list)
        for k, v in component_map.items():
            components[v].append(k)
        return list(components.values())

    @property
    def matrix(self):
        return self._merge_matrices()

    def _merge_matrices(self):
        result = {}
        for component in self.components:
            result.update(component.matrix)
        return DistanceMatrix(result)

    def _fill_matrix_from_cache(self, indexes_list, matrix_component):
        for from_ in indexes_list:
            for to_ in indexes_list:
                elem = (self.locations[from_], self.locations[to_])
                value = self._cache_matrix.get(elem, None)
                if value:
                    matrix_component.matrix[elem] = value

    @staticmethod
    def create_matrix_from_directions_response(resp, points):
        matrix = DistanceMatrix()
        for from_, to_, leg in zip(points[:-1], points[1:], resp[0]['legs']):
            matrix[(from_.location, to_.location)] = take_matrix_value(leg)
        return matrix
