import time
from typing import Type

from route_optimisation.engine.events import event_handler
from route_optimisation.logging import EventType

from .base import ORToolsSimpleAssignment


class AssignmentRunTimer:
    def __init__(self, time_limit):
        self._time_limit = time_limit
        self._start = time.time()

    def check_time(self):
        return time.time() - self._start <= self._time_limit


class IteratingServices:
    pass


class IteratingAssignmentImplementation:
    def __init__(self, assignment_instance: ORToolsSimpleAssignment):
        self.assignment_instance = assignment_instance

    def check_break_before_iteration(self) -> bool:
        pass

    def log_before_iteration(self):
        pass

    def init_iteration_services(self) -> IteratingServices:
        pass

    def init_finish_services(self) -> IteratingServices:
        pass

    def on_iteration_start(self, services: IteratingServices):
        pass

    def check_break_after_iteration_start(self, services: IteratingServices) -> bool:
        pass

    def do_iteration_logic(self, services: IteratingServices):
        pass

    def after_iteration(self, services: IteratingServices):
        pass

    def setup_assignment_after_iteration(self, services: IteratingServices):
        pass

    def clean_routes_before_finish(self, services: IteratingServices):
        pass

    def setup_assignment_on_finish(self, services: IteratingServices):
        pass


class IteratingAssignmentRunner:
    def __init__(self, implementation: IteratingAssignmentImplementation):
        self.implementation: IteratingAssignmentImplementation = implementation

    def do_assignment_iteration(self) -> bool:
        if self.implementation.check_break_before_iteration():
            return True
        self.implementation.log_before_iteration()
        services = self.implementation.init_iteration_services()
        self.implementation.on_iteration_start(services)
        if self.implementation.check_break_after_iteration_start(services):
            return True
        self.implementation.do_iteration_logic(services)
        self.implementation.after_iteration(services)
        self.implementation.setup_assignment_after_iteration(services)

    def finish_assignment(self) -> None:
        services = self.implementation.init_finish_services()
        self.implementation.clean_routes_before_finish(services)
        self.implementation.setup_assignment_on_finish(services)


class IteratingAssignment(ORToolsSimpleAssignment):
    runner_abstraction_class: Type[IteratingAssignmentRunner] = IteratingAssignmentRunner
    runner_implementation_class: Type[IteratingAssignmentImplementation] = IteratingAssignmentImplementation

    def __init__(self, search_parameters, *args, **kwargs):
        super().__init__(search_parameters, *args, **kwargs)
        self.current_iteration = 0

    def get_iterations_count(self):
        raise NotImplementedError()

    def planned_inner_steps_count(self):
        return self.get_iterations_count() + 1

    def make_assignment(self, assignment_progress_watcher):
        assignment_timer = AssignmentRunTimer(self.search_parameters.assignment_time_limit)
        assignment_exists = super().make_assignment(assignment_progress_watcher)
        assignment_progress_watcher.step_passed()
        if not assignment_exists:
            return assignment_exists

        self.current_iteration, max_iterations_count = 0, self.get_iterations_count()
        event_handler.dev(EventType.OPTIMISATION_PROCESS,
                          f'[{self.__class__.__name__}] max cycles count: {max_iterations_count}')
        runner_implementation = self.runner_implementation_class(self)
        runner = self.runner_abstraction_class(runner_implementation)
        while self.current_iteration < max_iterations_count:
            self.current_iteration += 1
            if not assignment_timer.check_time():
                event_handler.dev(EventType.OPTIMISATION_PROCESS,
                                  f'Time exceeded: {self.search_parameters.assignment_time_limit} seconds')
                break
            should_break = runner.do_assignment_iteration()
            if should_break:
                break
            assignment_progress_watcher.step_passed()

        event_handler.dev(EventType.OPTIMISATION_PROCESS,
                          f'{self.__class__.__name__} passed. rerun count: {self.current_iteration}')
        runner.finish_assignment()
        return self.assignment is not None
