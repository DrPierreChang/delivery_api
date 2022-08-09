import time
from typing import List

from route_optimisation.engine.ortools.assignment.base import ORToolsSimpleAssignment

from .points_reassign import ReassignPointsManager
from .types import ClosenessScore, RoutePointIndex


class ToRouteCloseness:
    __slots__ = ('vehicle_idx', 'closeness_score')

    def __init__(self, vehicle_idx: int, closeness_score: ClosenessScore):
        self.vehicle_idx = vehicle_idx
        self.closeness_score = closeness_score


class PointsRouteCloseness:
    __slots__ = ('delivery_point_index', 'closeness_score', 'another_routes_scores', 'have_another_routes')

    def __init__(self, delivery_point_index: RoutePointIndex, closeness_score: ClosenessScore,
                 another_routes_scores: List[ToRouteCloseness]):
        self.delivery_point_index = delivery_point_index
        self.closeness_score = closeness_score
        self.another_routes_scores = another_routes_scores
        self.have_another_routes = len(another_routes_scores) > 0


class PreviousRunStore:
    """
    Keeps result information of few previous assignment runs.
    """

    def __init__(self, assignment: ORToolsSimpleAssignment):
        self.assignment = assignment
        self.prev_reruns = []
        self.prev_skipped_jobs = []
        self.not_changing = False
        self.not_changing_orders_count = False

    def process_changes(self):
        _time, _distance = self.assignment.result.driving_time, self.assignment.result.driving_distance
        self.prev_reruns.append((_time, _distance))
        if len(self.prev_reruns) > 1:
            if self.prev_reruns[-2][0] == _time and self.prev_reruns[-2][1] == _distance:
                self.not_changing = True

    def process_skipped(self, reassign_points: ReassignPointsManager):
        self.prev_skipped_jobs.append(len(reassign_points.points_to_reassign))
        self.not_changing_orders_count = len(self.prev_skipped_jobs) > 1 \
            and self.prev_skipped_jobs[-2] == self.prev_skipped_jobs[-1]


class SimpleTimer:
    def __init__(self, on_exit):
        self.on_exit = on_exit

    def timeit(self, name):
        this = self

        class With:
            def __init__(self):
                self.start = None

            def __enter__(self):
                self.start = time.time()

            def __exit__(self, exc_type, exc_val, exc_tb):
                this.on_exit(name, time.time() - self.start)

        return With()
