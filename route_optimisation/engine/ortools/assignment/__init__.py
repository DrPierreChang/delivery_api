from .balanced_assignment import BalancedAssignment
from .base import (
    ExtendedTimeWindowAssignment,
    ORToolsSimpleAssignment,
    TimeBalancedAssignmentMixin,
    UseAllDriversAssignmentMixin,
)
from .minimize_time_assignment import MinimizeTimeAssignment
from .soft_window_assignment import SoftWindowAssignmentBase


class TimeBalancedAssignment(TimeBalancedAssignmentMixin, ORToolsSimpleAssignment):
    pass


class UseAllDriversAssignment(UseAllDriversAssignmentMixin, ORToolsSimpleAssignment):
    pass


class AllDriversBalancedAssignment(UseAllDriversAssignmentMixin,
                                   TimeBalancedAssignmentMixin,
                                   ORToolsSimpleAssignment):
    pass


class SoftWindowTimeBalancedAssignment(TimeBalancedAssignmentMixin, SoftWindowAssignmentBase):
    pass


class SoftWindowUseAllDriversAssignment(UseAllDriversAssignmentMixin, SoftWindowAssignmentBase):
    pass


class SoftWindowAllDriversBalancedAssignment(UseAllDriversAssignmentMixin,
                                             TimeBalancedAssignmentMixin,
                                             SoftWindowAssignmentBase):
    pass
