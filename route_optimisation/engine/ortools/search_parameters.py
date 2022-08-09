import math

from ortools.constraint_solver import pywrapcp, routing_enums_pb2


class SearchParameters:
    def __init__(self, first_solution_strategy, time_limit, local_search_metaheuristic=None,
                 assignment_time_limit=None):
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        rerun_search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (getattr(routing_enums_pb2.FirstSolutionStrategy,
                                                             first_solution_strategy))
        rerun_search_parameters.first_solution_strategy = (getattr(routing_enums_pb2.FirstSolutionStrategy,
                                                                   first_solution_strategy))
        if local_search_metaheuristic:
            search_parameters.local_search_metaheuristic = (getattr(routing_enums_pb2.LocalSearchMetaheuristic,
                                                                    local_search_metaheuristic))
            rerun_search_parameters.local_search_metaheuristic = (getattr(routing_enums_pb2.LocalSearchMetaheuristic,
                                                                          local_search_metaheuristic))
        search_parameters.time_limit.seconds = time_limit
        rerun_search_parameters.time_limit.seconds = math.ceil(time_limit/2)

        # search_parameters.lns_time_limit.seconds = 1
        # search_parameters.log_search = settings.TESTING_MODE
        self.parameters = search_parameters
        self.rerun_search_parameters = rerun_search_parameters
        self.first_solution_strategy = first_solution_strategy
        self.local_search_metaheuristic = local_search_metaheuristic
        self.assignment_time_limit = assignment_time_limit


class IteratingSearchParameters(SearchParameters):
    def __init__(self, first_solution_strategy, time_limit, local_search_metaheuristic=None,
                 assignment_time_limit=None):
        super().__init__(first_solution_strategy, time_limit, local_search_metaheuristic, assignment_time_limit)
        self.parameters.time_limit.seconds *= 2
