from __future__ import absolute_import, unicode_literals

from collections import namedtuple

from django.utils.translation import gettext_lazy as _

groups = [
    'ALL',
    'SUCCESSFUL',
    'UNSUCCESSFUL',
    'UNFINISHED',
    'FINISHED',
    'TRACKABLE',
    'PICKUP_TRACKABLE',
    'STARTED',
    'ACTIVE',
    'ACTIVE_DRIVER',
    'MONITORED',
]
OrderGroups = namedtuple('OrderGroups', groups)


class OrderStatus(object):
    FAILED = 'failed'
    TERMINATED = 'terminated'
    NOT_ASSIGNED = 'not_assigned'
    ASSIGNED = 'assigned'
    PICK_UP = 'pickup'
    PICKED_UP = 'picked_up'
    IN_PROGRESS = 'in_progress'
    WAY_BACK = 'way_back'
    DELIVERED = 'delivered'

    _status = (
        (NOT_ASSIGNED, _('Not assigned')),
        (ASSIGNED, _('Assigned')),
        (PICK_UP, _('Pick up')),
        (PICKED_UP, _('Picked up')),
        (IN_PROGRESS, _('In progress')),
        (WAY_BACK, _('Way back')),
        (DELIVERED, _('Completed')),
        (FAILED, _('Failed')),
    )
    _status_dict = dict(_status)

    # status_groups
    _unfinished_group = [NOT_ASSIGNED, ASSIGNED, PICK_UP, PICKED_UP, IN_PROGRESS, WAY_BACK]
    _trackable_group = [IN_PROGRESS, WAY_BACK, DELIVERED, FAILED]
    _pickup_trackable_group = [PICK_UP, PICKED_UP, IN_PROGRESS, FAILED]
    _active_driver_group = [ASSIGNED, PICK_UP, PICKED_UP, IN_PROGRESS, WAY_BACK]
    status_groups = OrderGroups(**{
        'ALL': [st[0] for st in _status],
        'SUCCESSFUL': [DELIVERED, ],
        'UNSUCCESSFUL': [FAILED, ],
        'UNFINISHED': _unfinished_group,
        'FINISHED': [DELIVERED, FAILED],
        'TRACKABLE': _trackable_group,
        'PICKUP_TRACKABLE': _pickup_trackable_group,
        'STARTED': [PICK_UP] + _trackable_group,
        'ACTIVE': _unfinished_group,
        'ACTIVE_DRIVER': _active_driver_group,
        'MONITORED': [PICK_UP, PICKED_UP, IN_PROGRESS],
    })
    status_rates = {st[0]: ind_ for ind_, st in enumerate(_status)}

    _order_status_map = {
        FAILED: [],
        NOT_ASSIGNED: [ASSIGNED, FAILED, DELIVERED],
        ASSIGNED: [NOT_ASSIGNED, IN_PROGRESS, FAILED, DELIVERED],
        PICK_UP: [PICKED_UP, IN_PROGRESS, FAILED],
        PICKED_UP: [IN_PROGRESS, FAILED],
        IN_PROGRESS: [DELIVERED, FAILED],
        WAY_BACK: [DELIVERED, FAILED],
        DELIVERED: [],
    }
    _pick_up_modification = {
        ASSIGNED: [NOT_ASSIGNED, PICK_UP, IN_PROGRESS, FAILED, DELIVERED],
    }
    _way_back_modification = {
        IN_PROGRESS: [DELIVERED, WAY_BACK, FAILED],
    }

    _merchant_available_statuses = [NOT_ASSIGNED, ASSIGNED, PICK_UP, IN_PROGRESS, WAY_BACK, DELIVERED, FAILED]
    _driver_available_statuses = [NOT_ASSIGNED, ASSIGNED, PICK_UP, PICKED_UP, IN_PROGRESS,
                                  FAILED, DELIVERED, WAY_BACK]
    _customer_available_statuses = []
    _can_confirm_statuses = [IN_PROGRESS, DELIVERED, WAY_BACK, FAILED]
    _can_pre_confirm_statuses = [IN_PROGRESS, FAILED]
    _can_confirm_pick_up_statuses = [PICK_UP, PICKED_UP, IN_PROGRESS, FAILED]
    _can_edit_job_statuses = [NOT_ASSIGNED, ASSIGNED]

    _statuses_with_required_driver = [ASSIGNED, PICK_UP, PICKED_UP, IN_PROGRESS, DELIVERED]

    _order_status_map_in_concatenated_order = {
        FAILED: [FAILED],
        NOT_ASSIGNED: [NOT_ASSIGNED, FAILED],
        ASSIGNED: [ASSIGNED, FAILED],
        PICK_UP: [PICK_UP, ASSIGNED, FAILED],
        PICKED_UP: [PICKED_UP, ASSIGNED, FAILED],
        IN_PROGRESS: [IN_PROGRESS, FAILED],
        WAY_BACK: [WAY_BACK, FAILED],
        DELIVERED: [DELIVERED, FAILED],
   }

    def available_to_change_statuses(self, user):
        if user.is_anonymous:
            return self._customer_available_statuses
        if user.is_driver:
            return self._driver_available_statuses
        if user.is_admin or user.is_manager or user.is_staff:
            return self._merchant_available_statuses
        return []

    def get_order_status_map(self):
        return self._order_status_map

    def get_current_available_statuses(self, status):
        return self.get_order_status_map()[status]

    def current_available_statuses_for_user(self, status, user):
        return set(self.get_current_available_statuses(status)) & set(self.available_to_change_statuses(user))

    def get_available_statuses_for_concatenated(self, concatenated_order_status):
        """Orders with what status can be in a concatenated order with the specified status."""
        return self._order_status_map_in_concatenated_order[concatenated_order_status]

    @classmethod
    def get_status_ordering(cls, finished_equal=False):
        ordering = {status_tuple[0]: index for index, status_tuple in enumerate(cls._status)}
        if finished_equal:
            ordering[cls.FAILED] = ordering[cls.DELIVERED]
        return ordering

    @classmethod
    def can_confirm_with_status(cls, status):
        return status in cls._can_confirm_statuses

    @classmethod
    def can_pre_confirm_with_status(cls, status):
        return status in cls._can_pre_confirm_statuses

    @classmethod
    def can_confirm_pick_up_with_status(cls, status):
        return status in cls._can_confirm_pick_up_statuses

    @classmethod
    def is_driver_required_for(cls, status):
        return status in cls._statuses_with_required_driver


for ind, k in enumerate(groups):
    setattr(OrderStatus, k, ind)


class StatusFilterConditions(object):
    ACTIVE = 'active'
    ACTIVE_DRIVER = 'active_driver'
    INACTIVE = 'inactive'
    SUCCESSFUL = 'successful'
    UNSUCCESSFUL = 'unsuccessful'
    PICK_UP = 'pickup'
    IN_PROGRESS = 'in_progress'
    ASSIGNED = 'assigned'
    NOT_ASSIGNED = 'not_assigned'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CONFIRMED = 'confirmed'
    WAY_BACK = 'way_back'

    status_groups = {
        ACTIVE: dict(status__in=OrderStatus.status_groups.UNFINISHED),
        ACTIVE_DRIVER: dict(status__in=OrderStatus.status_groups.ACTIVE_DRIVER),
        INACTIVE: dict(status__in=OrderStatus.status_groups.FINISHED),
        SUCCESSFUL: dict(status__in=OrderStatus.status_groups.SUCCESSFUL),
        UNSUCCESSFUL: dict(status__in=OrderStatus.status_groups.UNSUCCESSFUL),
        ASSIGNED: dict(status=OrderStatus.ASSIGNED),
        NOT_ASSIGNED: dict(status=OrderStatus.NOT_ASSIGNED),
        PICK_UP: dict(status=OrderStatus.PICK_UP),
        IN_PROGRESS: dict(status=OrderStatus.IN_PROGRESS),
        COMPLETED: dict(status=OrderStatus.DELIVERED),
        FAILED: dict(status=OrderStatus.FAILED),
        CONFIRMED: dict(status=OrderStatus.DELIVERED, is_confirmed_by_customer=True),
        WAY_BACK: dict(status=OrderStatus.WAY_BACK),
    }
    available = list(status_groups.keys())
