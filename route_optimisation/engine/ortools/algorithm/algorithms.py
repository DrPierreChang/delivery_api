from functools import cmp_to_key
from operator import attrgetter
from typing import Iterable, List

from route_optimisation.const import MerchantOptimisationFocus
from route_optimisation.engine.base_classes.algorithm import AlgorithmBase
from route_optimisation.engine.base_classes.parameters import EngineParameters
from route_optimisation.engine.events import event_handler
from route_optimisation.engine.ortools.assignment import (
    AllDriversBalancedAssignment,
    ExtendedTimeWindowAssignment,
    ORToolsSimpleAssignment,
    SoftWindowAllDriversBalancedAssignment,
    SoftWindowAssignmentBase,
    SoftWindowTimeBalancedAssignment,
    SoftWindowUseAllDriversAssignment,
    TimeBalancedAssignment,
    UseAllDriversAssignment,
)
from route_optimisation.engine.ortools.context import AssignmentContextManager, GroupAssignmentContext, current_context
from route_optimisation.engine.ortools.search_parameters import IteratingSearchParameters, SearchParameters
from route_optimisation.logging import EventType
from route_optimisation.logging.logs.progress import ProgressConst

from ..assignment import BalancedAssignment, MinimizeTimeAssignment
from ..assignment.base import ORToolsAssignmentBase
from ..defaults import calc_assignment_time_limit, default_search_time_limit, default_solo_search_time_limit
from .assignment_selector import AssignmentSelector, OneDriverAssignmentSelector


class OrToolsAssignmentsManager:
    assignment_selector_class = None

    def __init__(self):
        self.passed_assignments_steps_count = 0
        self.planned_assignments_steps_count = None
        self.assignments_choices = set()
        self.all_assignments = []

    def select_best_assignment(self):
        assignments_choices = self.assignments_choices
        assignments_choices = list(filter(attrgetter('is_successful'), assignments_choices))
        return self.assignment_selector_class(assignments_choices).select_best()

    def set_planned_assignments_count(self, count):
        self.planned_assignments_steps_count = count
        self.log_assignment_progress()

    def add_successful_assignment(self, assignment):
        self.assignments_choices.add(assignment)

    def add_assignment(self, assignment):
        self.all_assignments.append(assignment)

    def log_assignment_progress(self):
        assert self.planned_assignments_steps_count is not None
        event_handler.progress(stage=ProgressConst.ALGORITHM, num=self.passed_assignments_steps_count,
                               count=self.planned_assignments_steps_count)

    def assignment_progress_watcher(self, steps_count):
        this = self

        class AssignmentProgressWatcher:
            def __init__(self):
                self.start_value = this.passed_assignments_steps_count

            @staticmethod
            def step_passed():
                this.passed_assignments_steps_count += 1
                this.log_assignment_progress()

            def passed(self):
                this.passed_assignments_steps_count = self.start_value + steps_count
                this.log_assignment_progress()

        return AssignmentProgressWatcher()

    def clean(self):
        for assignment in self.all_assignments:
            assignment.clean()


class GroupAssignmentsManager(OrToolsAssignmentsManager):
    assignment_selector_class = AssignmentSelector


class OneDriverAssignmentsManager(OrToolsAssignmentsManager):
    assignment_selector_class = OneDriverAssignmentSelector


class OptimisationAlgorithmStep:
    CONTINUE = 'continue'
    EXIT = 'exit'

    def do(self, manager: OrToolsAssignmentsManager):
        raise NotImplementedError()


class AssignmentStep(OptimisationAlgorithmStep):
    def __init__(self, assignment: ORToolsSimpleAssignment):
        self.assignment = assignment

    def do(self, manager: OrToolsAssignmentsManager):
        assignment_progress_watcher = manager.assignment_progress_watcher(self.steps_count())
        if self.assignment.make_assignment(assignment_progress_watcher):
            manager.add_successful_assignment(self.assignment)
        manager.add_assignment(self.assignment)
        assignment_progress_watcher.passed()
        return self.CONTINUE

    def steps_count(self):
        return self.assignment.planned_inner_steps_count() + 1


class SimpleAssignmentFoundCheck(OptimisationAlgorithmStep):
    def do(self, manager: OrToolsAssignmentsManager):
        if len(manager.assignments_choices) == 0:
            event_handler.dev(EventType.OPTIMISATION_PROCESS, 'No simple assignment found')
            return self.EXIT
        best_simple_assignment = sorted(
            manager.assignments_choices,
            key=cmp_to_key(ORToolsAssignmentBase.compare_by_estimated_time)
        )[0]
        event_handler.dev(EventType.OPTIMISATION_PROCESS, 'Best of simple assignments\n{}\n{}'.format(
            best_simple_assignment.default_printer(),
            str(best_simple_assignment)
        ))
        return self.CONTINUE


class AssignmentFoundCheck(OptimisationAlgorithmStep):
    def do(self, manager: OrToolsAssignmentsManager):
        if len(manager.assignments_choices) == 0:
            event_handler.dev(EventType.OPTIMISATION_PROCESS, 'No assignment found')
            return self.EXIT
        return self.CONTINUE


class OrToolsAlgorithm(AlgorithmBase):
    assignment_context_class = GroupAssignmentContext
    assignment_manager_class = None
    first_solution_strategies = (
        'PATH_CHEAPEST_ARC',
        'PATH_MOST_CONSTRAINED_ARC',
        'GLOBAL_CHEAPEST_ARC',
    )

    def __init__(self, search_time_limit=None, search_time_limit_with_pickup=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.search_parameters_list = None
        self.soft_window_search_parameters = None
        self.iterating_search_parameters = None
        self.search_time_limit = search_time_limit
        self.search_time_limit_with_pickup = search_time_limit_with_pickup or search_time_limit
        self.assignments_manager = self.assignment_manager_class()

    def assign(self, params: EngineParameters):
        with AssignmentContextManager(params, self.assignment_context_class):
            self._init_search_parameters_list()
            return super().assign(params)

    def _init_search_parameters_list(self):
        time_limit = self._calc_time_limit()
        assignment_time_limit = calc_assignment_time_limit(
            algorithms_count=2 if current_context.focus == MerchantOptimisationFocus.ALL else 1
        )
        self.search_parameters_list = list(
            SearchParameters(
                strategy, time_limit=time_limit,
                local_search_metaheuristic='GUIDED_LOCAL_SEARCH',
                assignment_time_limit=assignment_time_limit,
            ) for strategy in self.first_solution_strategies
        )
        self.soft_window_search_parameters = SearchParameters(
            'PATH_MOST_CONSTRAINED_ARC', time_limit=time_limit,
            local_search_metaheuristic='GUIDED_LOCAL_SEARCH',
            assignment_time_limit=assignment_time_limit,
        )
        self.iterating_search_parameters = IteratingSearchParameters(
            'PATH_MOST_CONSTRAINED_ARC', time_limit=time_limit,
            local_search_metaheuristic='GUIDED_LOCAL_SEARCH',
            assignment_time_limit=assignment_time_limit,
        )

    def _calc_time_limit(self):
        time_limit = self.search_time_limit_with_pickup if current_context.has_pickup else self.search_time_limit
        return time_limit or default_search_time_limit()

    def optimise(self):
        event_handler.dev(EventType.OPTIMISATION_PROCESS, 'Start optimisation')
        steps = self.define_steps()
        self.assignments_manager.set_planned_assignments_count(
            sum(map(
                lambda _step: _step.steps_count(),
                filter(lambda _step: isinstance(_step, AssignmentStep), steps)
            ))
        )
        for step in steps:
            what_next = step.do(self.assignments_manager)
            if what_next == OptimisationAlgorithmStep.CONTINUE:
                continue
            elif what_next == OptimisationAlgorithmStep.EXIT:
                return
        return self.assignments_manager.select_best_assignment()

    def define_steps(self) -> Iterable[OptimisationAlgorithmStep]:
        raise NotImplementedError()

    def clean(self):
        self.assignments_manager.clean()
        for search_parameters in (self.search_parameters_list or []):
            search_parameters.parameters = None
            search_parameters.rerun_search_parameters = None
        if self.soft_window_search_parameters:
            self.soft_window_search_parameters.parameters = None
            self.soft_window_search_parameters.rerun_search_parameters = None
        if self.iterating_search_parameters:
            self.iterating_search_parameters.parameters = None
            self.iterating_search_parameters.rerun_search_parameters = None


class GroupAlgorithm(OrToolsAlgorithm):
    assignment_manager_class = GroupAssignmentsManager
    time_balancing_coefficients = (20, )
    route_balancing_allowed_diffs = (10, )  # allowed percent to difference between avg route time and max deviation

    def define_steps(self) -> Iterable[OptimisationAlgorithmStep]:
        if current_context.focus == MerchantOptimisationFocus.OLD:
            return self.old_define_steps()

        steps: List[OptimisationAlgorithmStep] = []

        if current_context.num_vehicles <= 1:
            steps.append(AssignmentStep(MinimizeTimeAssignment(self.iterating_search_parameters)))
        else:
            if current_context.focus in [MerchantOptimisationFocus.ALL, MerchantOptimisationFocus.MINIMAL_TIME]:
                steps.append(AssignmentStep(MinimizeTimeAssignment(self.iterating_search_parameters)))
            if current_context.focus in [MerchantOptimisationFocus.ALL, MerchantOptimisationFocus.TIME_BALANCE]:
                steps.append(AssignmentStep(
                    BalancedAssignment(self.iterating_search_parameters, self.route_balancing_allowed_diffs[0])
                ))
        steps.append(AssignmentFoundCheck())
        return steps

    def old_define_steps(self) -> Iterable[OptimisationAlgorithmStep]:
        steps: List[OptimisationAlgorithmStep] = [
            AssignmentStep(SoftWindowAssignmentBase(self.soft_window_search_parameters))]
        steps.extend([
            AssignmentStep(ORToolsSimpleAssignment(search_parameters))
            for search_parameters in self.search_parameters_list
        ])
        steps.append(SimpleAssignmentFoundCheck())
        if current_context.num_vehicles > 1:
            steps.append(AssignmentStep(SoftWindowUseAllDriversAssignment(self.soft_window_search_parameters)))
            steps.extend([
                AssignmentStep(UseAllDriversAssignment(search_parameters))
                for search_parameters in self.search_parameters_list
            ])
            steps.extend([
                AssignmentStep(SoftWindowAllDriversBalancedAssignment(self.soft_window_search_parameters, coefficient))
                for coefficient in self.time_balancing_coefficients
            ])
            steps.extend([
                AssignmentStep(AllDriversBalancedAssignment(search_parameters, coefficient))
                for search_parameters in self.search_parameters_list
                for coefficient in self.time_balancing_coefficients
            ])
            steps.extend([
                AssignmentStep(SoftWindowTimeBalancedAssignment(self.soft_window_search_parameters, coefficient))
                for coefficient in self.time_balancing_coefficients
            ])
            steps.extend([
                AssignmentStep(TimeBalancedAssignment(search_parameters, coefficient))
                for search_parameters in self.search_parameters_list
                for coefficient in self.time_balancing_coefficients
            ])
        return steps


class OneDriverBase(OrToolsAlgorithm):
    def _init_search_parameters_list(self):
        time_limit = self._calc_time_limit()
        assignment_time_limit = calc_assignment_time_limit()
        self.search_parameters_list = list(
            SearchParameters(
                strategy, time_limit=time_limit,
                local_search_metaheuristic='GUIDED_LOCAL_SEARCH',
                assignment_time_limit=assignment_time_limit,
            ) for strategy in self.first_solution_strategies
        )

    def _calc_time_limit(self):
        time_limit = self.search_time_limit_with_pickup if current_context.has_pickup else self.search_time_limit
        return time_limit or default_solo_search_time_limit()


class OneDriverAlgorithm(OneDriverBase):
    assignment_manager_class = OneDriverAssignmentsManager

    def define_steps(self) -> Iterable[OptimisationAlgorithmStep]:
        steps: List[OptimisationAlgorithmStep] = [
            AssignmentStep(ORToolsSimpleAssignment(search_parameters))
            for search_parameters in self.search_parameters_list
        ]
        steps.append(SimpleAssignmentFoundCheck())
        return steps


class SoftOneDriverAlgorithm(OneDriverBase):
    assignment_manager_class = OneDriverAssignmentsManager

    def define_steps(self) -> Iterable[OptimisationAlgorithmStep]:
        steps: List[OptimisationAlgorithmStep] = [
            AssignmentStep(ExtendedTimeWindowAssignment(search_parameters))
            for search_parameters in self.search_parameters_list
        ]
        steps.append(SimpleAssignmentFoundCheck())
        return steps
