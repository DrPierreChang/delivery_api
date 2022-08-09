from tasks.mixins.order_status import OrderStatus


class StatusTimeDistance(object):
    status_name = None

    @staticmethod
    def exists(order, pick_up_start, picked_up_start, in_progress_start, wayback_start):
        raise NotImplementedError()

    @staticmethod
    def calc(order, pick_up_start, picked_up_start, in_progress_start, wayback_start):
        raise NotImplementedError()

    @staticmethod
    def format_timedelta_seconds(delta):
        return int(delta.total_seconds()) if delta is not None else delta


class PickUpStatusTimeDistance(StatusTimeDistance):
    status_name = OrderStatus.PICK_UP

    @staticmethod
    def exists(order, pick_up_start, *args):
        return pick_up_start

    @staticmethod
    def calc(order, pick_up_start, picked_up_start, in_progress_start, *args):
        if picked_up_start:
            _time = picked_up_start - pick_up_start
            _distance = order.pick_up_distance
        elif in_progress_start:
            _time = in_progress_start - pick_up_start
            _distance = order.pick_up_distance
        elif order.status in [OrderStatus.FAILED, OrderStatus.DELIVERED] and order.finalized:
            # ASSIGNED -> PICK_UP -> FAILED
            _time = order.finished_at - pick_up_start if order.finished_at else None
            _distance = order.order_distance
        else:
            _time = None
            _distance = order.pick_up_distance
        return _time, _distance


class InProgressStatusTimeDistance(StatusTimeDistance):
    status_name = OrderStatus.IN_PROGRESS

    @staticmethod
    def exists(order, pick_up_start, picked_up_start, in_progress_start, *args):
        return in_progress_start

    @staticmethod
    def calc(order, pick_up_start, picked_up_start, in_progress_start, wayback_start):
        if wayback_start:
            # ASSIGNED -> PICK_UP -> IN_PROGRESS -> WAY_BACK -> DELIVERED/FAILED
            # ASSIGNED -> IN_PROGRESS -> WAY_BACK -> DELIVERED/FAILED
            _time = wayback_start - in_progress_start
        else:
            # ASSIGNED -> PICK_UP -> IN_PROGRESS -> DELIVERED/FAILED
            # ASSIGNED -> IN_PROGRESS -> DELIVERED/FAILED
            _time = order.finished_at - in_progress_start if order.finished_at else None
        if order.order_distance is not None:
            _distance = order.order_distance - (order.wayback_distance or 0) - (order.pick_up_distance or 0)
        else:
            _distance = 0
        return _time, _distance


class WayBackStatusTimeDistance(StatusTimeDistance):
    status_name = OrderStatus.WAY_BACK

    @staticmethod
    def exists(order, pick_up_start, picked_up_start, in_progress_start, wayback_start):
        return wayback_start

    @staticmethod
    def calc(order, pick_up_start, picked_up_start, in_progress_start, wayback_start):
        # ASSIGNED -> PICK_UP -> IN_PROGRESS -> WAY_BACK -> DELIVERED/FAILED
        # ASSIGNED -> IN_PROGRESS -> WAY_BACK -> DELIVERED/FAILED
        _time = order.finished_at - wayback_start if order.finished_at else None
        _distance = order.wayback_distance
        return _time, _distance


class OverallTimeDistance(StatusTimeDistance):
    status_name = 'overall'

    @staticmethod
    def exists(order, *args):
        return order.status in [OrderStatus.FAILED, OrderStatus.DELIVERED]

    @staticmethod
    def calc(order, pick_up_start, picked_up_start, in_progress_start, *args):
        _time = None
        if order.finished_at and order.started_at:
            _time = order.finished_at - order.started_at
            if in_progress_start and picked_up_start:
                _picked_up_time = in_progress_start - picked_up_start
                _time -= _picked_up_time
        _distance = order.order_distance
        return _time, _distance


time_distance_calculators = [
    PickUpStatusTimeDistance,
    InProgressStatusTimeDistance,
    WayBackStatusTimeDistance,
    OverallTimeDistance
]
