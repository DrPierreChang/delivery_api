from operator import attrgetter

from route_optimisation.engine.events import event_handler
from route_optimisation.logging import EventType


class AssignmentSelectorBase:
    MAX_ALLOWED_DISTANCE_COEFFICIENT = 1.14

    def __init__(self, assignments_choices):
        self.assignments_choices = assignments_choices

    def select_best(self):
        event_handler.dev(EventType.OPTIMISATION_PROCESS,
                          'Start choose best assignment. Count of choices: %d' % len(self.assignments_choices))
        if len(self.assignments_choices) == 0:
            return None

        self._filter_by_skipped_orders()
        self._filter_by_skipped_drivers()
        self.assignments_choices.sort(key=attrgetter('result.driving_distance'))
        self._log_good_choices()
        self._filter_by_driving_distance()
        event_handler.dev(EventType.OPTIMISATION_PROCESS,
                          'Assignments count after filtering: %d' % len(self.assignments_choices))
        for ortools_assignment in self.assignments_choices:
            event_handler.dev(EventType.OPTIMISATION_PROCESS, str(ortools_assignment))
        best = self._choose_best()
        event_handler.dev(EventType.OPTIMISATION_PROCESS, 'BEST ASSIGNMENT:\n%s' % str(best))
        event_handler.dev(EventType.OPTIMISATION_PROCESS, best.default_printer())
        event_handler.dev(EventType.OPTIMISATION_PROCESS, 'End choose best assignment')
        return best

    def _choose_best(self):
        return self.assignments_choices[0]

    def _log_good_choices(self):
        pass

    def _filter_by_skipped_orders(self):
        def lambda_len_skipped(choice):
            return len(choice.result.skipped_orders)

        min_skipped_orders, max_skipped_orders = [func(list(map(lambda_len_skipped, self.assignments_choices)))
                                                  for func in (min, max)]
        event_handler.dev(EventType.OPTIMISATION_PROCESS,
                          'Min skipped orders: %s; Max skipped orders: %s' % (min_skipped_orders, max_skipped_orders))
        self.assignments_choices = [ch for ch in self.assignments_choices
                                    if lambda_len_skipped(ch) == min_skipped_orders]

    def _filter_by_skipped_drivers(self):
        def lambda_len_skipped(choice):
            return len(choice.result.skipped_drivers)

        min_skipped_drivers, max_skipped_drivers = [func(list(map(lambda_len_skipped, self.assignments_choices)))
                                                    for func in (min, max)]
        event_handler.dev(EventType.OPTIMISATION_PROCESS,
                          'Min skipped drivers: %s; Max skipped drivers: %s'
                          % (min_skipped_drivers, max_skipped_drivers))
        self.assignments_choices = [ch for ch in self.assignments_choices
                                    if lambda_len_skipped(ch) == min_skipped_drivers]

    def _filter_by_driving_distance(self):
        def lambda_driving_distance(choice):
            return choice.result.driving_distance

        min_distance = min(map(lambda_driving_distance, self.assignments_choices))
        max_allowed_distance = min_distance * self.MAX_ALLOWED_DISTANCE_COEFFICIENT
        event_handler.dev(EventType.OPTIMISATION_PROCESS,
                          'Min distance: %s; Max allowed distance: %s' % (min_distance, max_allowed_distance))
        self.assignments_choices = [ch for ch in self.assignments_choices
                                    if lambda_driving_distance(ch) <= max_allowed_distance]


class AssignmentSelector(AssignmentSelectorBase):
    def _choose_best(self):
        return sorted(self.assignments_choices, key=attrgetter('tour_time_diff_to_avg', 'result.avg_start_time'))[0]

    def _log_good_choices(self):
        event_handler.dev(EventType.OPTIMISATION_PROCESS,
                          'Min Distance Assignment:\n%s' % str(self.assignments_choices[0]))
        most_balanced = sorted(self.assignments_choices, key=attrgetter('tour_time_diff_to_avg'))[0]
        event_handler.dev(EventType.OPTIMISATION_PROCESS, 'Most Balanced Assignment:\n%s' % str(most_balanced))


class OneDriverAssignmentSelector(AssignmentSelectorBase):
    def _choose_best(self):
        return sorted(self.assignments_choices, key=attrgetter('result.driving_distance'))[0]

    def _log_good_choices(self):
        event_handler.dev(EventType.OPTIMISATION_PROCESS,
                          'Min Distance Assignment:\n%s' % str(self.assignments_choices[0]))
