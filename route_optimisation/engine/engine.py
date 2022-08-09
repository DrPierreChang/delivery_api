from route_optimisation.const import GOOGLE_API_REQUESTS_LIMIT
from route_optimisation.engine.base_classes.algorithm import AlgorithmBase
from route_optimisation.engine.base_classes.result import AssignmentResult
from route_optimisation.engine.const import Algorithms
from route_optimisation.engine.dima import DistanceMatrixCache, set_dima_cache
from route_optimisation.engine.errors import ROError
from route_optimisation.engine.events import EventHandler, set_event_handler
from route_optimisation.logging import EventType
from route_optimisation.logging.logs.progress import ProgressConst
from routing.context_managers import GoogleApiRequestsTracker


class Engine:
    def __init__(
            self, algorithm,
            event_handler: EventHandler = None,
            distance_matrix_cache: DistanceMatrixCache = None,
            algorithm_params=None
    ):
        self.algorithm_name = algorithm
        self.event_handler: EventHandler = event_handler or EventHandler()
        self.distance_matrix_cache: DistanceMatrixCache = distance_matrix_cache or DistanceMatrixCache()
        self.algorithm_params = algorithm_params or {}
        self.api_requests_tracker = GoogleApiRequestsTracker(limit=GOOGLE_API_REQUESTS_LIMIT)

    def run(self, params):
        with self.api_requests_tracker:
            try:
                algorithm = self.get_algorithm()
                with set_event_handler(self.event_handler), set_dima_cache(self.get_distance_matrix_cache()):
                    self._log_classes(type(algorithm))
                    assignment = algorithm.assign(params=params)
            except ROError as exc:
                self.event_handler.error(exc.message)
                assignment = AssignmentResult.failed_assignment(exc)
            finally:
                self.event_handler.progress(stage=ProgressConst.ENGINE_FINISH)
                algorithm.clean()
        return assignment

    def get_distance_matrix_cache(self):
        return self.distance_matrix_cache

    def get_algorithm(self) -> AlgorithmBase:
        return Algorithms.map.get(self.algorithm_name)(**self.algorithm_params)

    def _log_classes(self, algorithm_class):
        self.event_handler.dev(
            EventType.SIMPLE_MESSAGE,
            'Algorithm class: %s. Event Handler class: %s. DiMa Cache class: %s.' % (
                algorithm_class, type(self.event_handler), type(self.get_distance_matrix_cache()))
        )
