import copy
from collections import deque

from .base import Graph


class EulerPath:
    def __init__(self, graph: Graph, start_vertex=None):
        self.graph = graph
        self.start_vertex = self._find_start_vertex() if start_vertex is None else start_vertex

    def _find_start_vertex(self):
        graph_dict = self.graph.graph
        allowed_vertices = [key for key in list(graph_dict.keys()) if len(graph_dict[key]) > 0]
        return min(allowed_vertices or list(graph_dict.keys()))

    def build(self):
        s = [self.start_vertex]
        path = []

        while s:
            w = s[-1]
            for u in self.graph.graph[w]:
                s.append(u)
                self.graph.remove_edge(w, u)
                break
            if w == s[-1]:
                path.append(s.pop())

        if len(path) == 1:
            path = []

        path.reverse()
        return path


class GraphWalker:
    def __init__(self, graph: Graph):
        self.graph = graph
        self.history = deque(maxlen=3)
        self.history.extend((None, None))

    def walk(self):
        last_edges_count = self.graph.edges_count
        while self.graph.has_edges:
            yield from self.walk_path()
            last_edges_count = self._check_decreasing_edges_count(last_edges_count)

    def walk_path(self):
        graph_copy = copy.deepcopy(self.graph)
        euler_path = EulerPath(self.graph).build()
        if len(euler_path) == 0:
            return
        for point in euler_path:
            if self._skip_point(point):
                continue
            yield from self._fix_possible_bad_euler_path(point, graph_copy)
            yield from self._return_point(point)

    def _skip_point(self, point):
        return point == self.history[-1]

    def _fix_possible_bad_euler_path(self, point, graph_copy):
        if self.history[-2] is not None and self.history[-1] is not None:
            no_edge_from_previous_point = point not in graph_copy.graph.get(self.history[-1])
            exists_edge_from_before_last = point in graph_copy.graph.get(self.history[-2])
            if no_edge_from_previous_point and exists_edge_from_before_last:
                yield from self._return_point(self.history[-2])

    def _return_point(self, point):
        yield point
        self.history.append(point)

    def _check_decreasing_edges_count(self, last_value):
        current_value = self.graph.edges_count
        assert current_value < last_value, 'Bad walking on graph: count of edges is not decreasing'
        return current_value
