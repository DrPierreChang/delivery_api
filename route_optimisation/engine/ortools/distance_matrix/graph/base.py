import copy
from collections import defaultdict


class Graph(object):
    def __init__(self, directed=False, vertices_indexes=None):
        self.directed = directed
        self.graph = defaultdict(list)
        for idx in (vertices_indexes or []):
            self.graph[idx] = []

    def add_edge(self, u, v):
        if v not in self.graph[u]:
            self.graph[u].append(v)
        if not self.directed and u not in self.graph[v]:
            self.graph[v].append(u)

    def add_full_edge(self, u, v):
        self.add_edge(u, v)
        if self.directed:
            self.add_edge(v, u)

    def remove_edge(self, u, v):
        if v in self.graph[u]:
            self.graph[u].remove(v)
        if not self.directed and u in self.graph[v]:
            self.graph[v].remove(u)

    def edges_gen(self):
        for src in self.graph:
            for dest in self.graph[src]:
                yield src, dest

    def add_vertex(self, vertex_index):
        for v in self.all_vertices:
            self.add_full_edge(v, vertex_index)

    def add_vertices(self, vertices):
        for vertex in vertices:
            self.add_vertex(vertex)

    def remove_vertex(self, vertex_index):
        if vertex_index in self.graph:
            del self.graph[vertex_index]
        for k in self.graph:
            if vertex_index in self.graph[k]:
                self.graph[k].remove(vertex_index)

    def remove_vertices(self, vertices):
        for vertex in vertices:
            self.remove_vertex(vertex)

    @property
    def all_vertices(self):
        all_vertices = set(self.graph.keys())
        for v in self.graph.values():
            all_vertices.update(v)
        return list(all_vertices)

    @property
    def has_edges(self):
        for key in self.graph:
            if self.graph[key]:
                return True
        return False

    @property
    def edges_count(self):
        return sum(map(len, self.graph.values()))

    @staticmethod
    def completed_directed_graph(vertices_indexes):
        graph = Graph(directed=True, vertices_indexes=vertices_indexes)
        for i in vertices_indexes:
            for j in vertices_indexes:
                if i != j:
                    graph.add_edge(i, j)
        return graph

    @staticmethod
    def pair_filled_directed_graph(vertices_indexes, pairs):
        graph = Graph(directed=True, vertices_indexes=vertices_indexes)
        for start, end in pairs:
            graph.add_edge(start, end)
        return graph

    @staticmethod
    def completed_undirected_graph(vertices_indexes):
        graph = Graph(directed=False, vertices_indexes=vertices_indexes)
        indexes_count = len(vertices_indexes)
        for i in range(indexes_count):
            for j in range(i, indexes_count):
                if i != j:
                    graph.add_edge(vertices_indexes[i], vertices_indexes[j])
        return graph

    def walk_vertices(self):
        self_copy = copy.deepcopy(self)
        from .graph_walk import GraphWalker
        yield from GraphWalker(self_copy).walk()

    def join_vertices_in_one_vertex(self, vertex1, vertex2):
        new_graph = Graph(directed=False)
        for key in self.graph:
            if key in (vertex1, vertex2):
                continue
            for dest in self.graph[key]:
                if dest not in (vertex1, vertex2):
                    new_graph.add_edge(key, dest)
            if vertex1 in self.graph[key] and vertex2 in self.graph[key]:
                new_graph.add_edge(key, vertex1)
        return new_graph
