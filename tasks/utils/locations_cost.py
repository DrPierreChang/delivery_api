import decimal
from datetime import datetime

import pytz

from tasks.models import OrderStatus


def calculate_locations_cost(order):
    track = order.serialized_track
    cost = 0
    track = list(filter(lambda location: location.get('in_progress_orders', 0) > 0 and location.get('google_requests') > 0,
                   track or []))
    if track:
        start_count_locations = order.events\
            .filter(field='status', new_value=OrderStatus.IN_PROGRESS)\
            .values_list('happened_at', flat=True).order_by('happened_at').first()
        finish_count_locations = order.events\
            .filter(field='status', new_value__in=[OrderStatus.DELIVERED, OrderStatus.FAILED, OrderStatus.WAY_BACK])\
            .values_list('happened_at', flat=True).order_by('happened_at').first()

        def filter_by_location_time(location):
            created_at = pytz.utc.localize(datetime.utcfromtimestamp(location['timestamp']))
            return start_count_locations <= created_at < finish_count_locations

        for loc in filter(filter_by_location_time, track):
            cost += decimal.Decimal(loc['google_request_cost']) * loc['google_requests'] / loc['in_progress_orders']
    return decimal.Decimal(cost).quantize(decimal.Decimal('.01'), rounding=decimal.ROUND_DOWN)
