from tasks.mixins.order_status import OrderStatus


class WorkStatus(object):
    WORKING = 'working'
    NOT_WORKING = 'not_working'
    ON_BREAK = 'on_break'


class DriverStatus(object):
    PICK_UP = 'pickup'
    PICKED_UP = 'picked_up'
    IN_PROGRESS = 'in_progress'
    WAY_BACK = 'way_back'
    ASSIGNED = 'assigned'
    UNASSIGNED = 'unassigned'


DRIVER_STATUSES_PARAMS = (
    {'order_attributes': {'status': OrderStatus.IN_PROGRESS, 'deleted': False}, 'status': DriverStatus.IN_PROGRESS},
    {'order_attributes': {'status': OrderStatus.PICK_UP, 'deleted': False}, 'status': DriverStatus.PICK_UP},
    {'order_attributes': {'status': OrderStatus.PICKED_UP, 'deleted': False}, 'status': DriverStatus.PICKED_UP},
    {'order_attributes': {'status': OrderStatus.WAY_BACK, 'deleted': False}, 'status': DriverStatus.WAY_BACK},
    {'order_attributes': {'status': OrderStatus.ASSIGNED, 'deleted': False}, 'status': DriverStatus.ASSIGNED},
)
DEFAULT_DRIVER_STATUS = DriverStatus.UNASSIGNED

DRIVER_STATUSES_MAP = {item['order_attributes']['status']: item['status'] for item in DRIVER_STATUSES_PARAMS}
DRIVER_STATUSES = [item['status'] for item in DRIVER_STATUSES_PARAMS] + [DEFAULT_DRIVER_STATUS]


DRIVER_STATUSES_ORDERING = [DriverStatus.UNASSIGNED, DriverStatus.ASSIGNED, DriverStatus.PICK_UP,
                            DriverStatus.PICKED_UP, DriverStatus.IN_PROGRESS, DriverStatus.WAY_BACK]
DRIVER_STATUSES_ORDERING_MAP_REVERSED = {name: order for order, name in enumerate(DRIVER_STATUSES_ORDERING)}
