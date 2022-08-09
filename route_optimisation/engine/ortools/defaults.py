from django.conf import settings

from .constants import ORTOOLS_SEARCH_TIME_LIMIT, ORTOOLS_SOLO_SEARCH_TIME_LIMIT
from .context import current_context


def default_search_time_limit():
    settings_pickup_time_limit = getattr(settings, 'ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP', None)
    settings_simple_time_limit = getattr(settings, 'ORTOOLS_SEARCH_TIME_LIMIT', None)
    settings_time_limit = settings_pickup_time_limit if current_context.has_pickup else settings_simple_time_limit
    return settings_time_limit or _calc_time()


def default_solo_search_time_limit():
    settings_pickup_time_limit = getattr(settings, 'ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP', None)
    settings_simple_time_limit = getattr(settings, 'ORTOOLS_SEARCH_TIME_LIMIT', None)
    settings_time_limit = settings_pickup_time_limit if current_context.has_pickup else settings_simple_time_limit
    return settings_time_limit or _calc_solo_time()


ORDERS_LIMIT_FOR_CONSTANT_TIME_LIMIT = 400
ORDERS_LIMIT_FOR_CONSTANT_TIME_LIMIT_SOLO = 50


def _calc_time():
    orders_points_count = len(current_context.orders)  # pickup and delivery points count
    if orders_points_count <= ORDERS_LIMIT_FOR_CONSTANT_TIME_LIMIT:
        return ORTOOLS_SEARCH_TIME_LIMIT
    max_allowed_time = int(ORTOOLS_SEARCH_TIME_LIMIT * 2.5)
    orders_multiplier = orders_points_count / ORDERS_LIMIT_FOR_CONSTANT_TIME_LIMIT
    return min(int(ORTOOLS_SEARCH_TIME_LIMIT * orders_multiplier), max_allowed_time)


def _calc_solo_time():
    orders_points_count = len(current_context.orders)  # pickup and delivery points count
    if orders_points_count <= ORDERS_LIMIT_FOR_CONSTANT_TIME_LIMIT_SOLO:
        return ORTOOLS_SOLO_SEARCH_TIME_LIMIT
    max_allowed_time = int(ORTOOLS_SEARCH_TIME_LIMIT * 2.5)
    orders_multiplier = orders_points_count / ORDERS_LIMIT_FOR_CONSTANT_TIME_LIMIT_SOLO
    return min(int(ORTOOLS_SOLO_SEARCH_TIME_LIMIT * orders_multiplier), max_allowed_time)


ORDERS_LIMIT_FOR_CONSTANT_ASSIGNMENT_TIME_LIMIT = 200
ASSIGNMENT_TIME_LIMIT = 7 * 60
MAX_ASSIGNMENT_TIME_LIMIT = 20 * 60


def get_assignment_time_limit():
    return getattr(settings, 'ORTOOLS_ASSIGNMENT_TIME_LIMIT', ASSIGNMENT_TIME_LIMIT)


def get_max_assignment_time_limit():
    return getattr(settings, 'ORTOOLS_MAX_ASSIGNMENT_TIME_LIMIT', MAX_ASSIGNMENT_TIME_LIMIT)


def calc_assignment_time_limit(algorithms_count=1):
    orders_points_count = len(current_context.orders)  # pickup and delivery points count
    if orders_points_count <= ORDERS_LIMIT_FOR_CONSTANT_ASSIGNMENT_TIME_LIMIT:
        return get_assignment_time_limit()
    orders_multiplier = (orders_points_count / ORDERS_LIMIT_FOR_CONSTANT_ASSIGNMENT_TIME_LIMIT) ** 0.9
    max_assignment_time_limit = int(get_max_assignment_time_limit() / algorithms_count)
    return min(int(get_assignment_time_limit() * orders_multiplier), max_assignment_time_limit)
