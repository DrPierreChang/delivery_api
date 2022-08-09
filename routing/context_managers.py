import copy
from decimal import Decimal

from radaro_utils.signals import google_api_request_event
from routing.google import ApiName


class GoogleApiRequestsTracker:
    cost = {
        ApiName.DIMA: Decimal('0.005'),
        ApiName.DIRECTIONS: Decimal('0.005'),
        ApiName.DIRECTIONS_ADVANCED: Decimal('0.01'),
    }

    def __init__(self, limit=None):
        self._count = {
            ApiName.DIMA: 0,
            ApiName.DIRECTIONS: 0,
            ApiName.DIRECTIONS_ADVANCED: 0,
        }
        self._limit = limit
        self.handlers = {
            ApiName.DIMA: self._on_dima_request,
            ApiName.DIRECTIONS: self._on_directions_request,
            ApiName.DIRECTIONS_ADVANCED: self._on_directions_advanced_request,
        }

    def __enter__(self):
        google_api_request_event.connect(self.receiver)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        google_api_request_event.disconnect(self.receiver)

    def receiver(self, api_name, options=None, *args, **kwargs):
        options = options or {}
        handler = self.handlers.get(api_name)
        if not handler:
            return
        api_name, count = handler(options)
        self._count[api_name] += count
        self._assert_limit()

    def _on_dima_request(self, options):
        count = len(options.get('origins', [])) * len(options.get('destinations', []))
        return ApiName.DIMA, count

    def _on_directions_request(self, options):
        api_name = ApiName.DIRECTIONS
        waypoints_count = len(options.get('waypoints', []))
        if waypoints_count >= 10 or options.get('optimize_waypoints', False):
            api_name = ApiName.DIRECTIONS_ADVANCED
        return api_name, 1

    def _on_directions_advanced_request(self, options):
        return ApiName.DIRECTIONS_ADVANCED, 1

    @property
    def stat(self):
        cost = Decimal('0.000')
        for api_name, count in self._count.items():
            cost += self.cost[api_name] * count
        result = copy.copy(self._count)
        result['cost'] = float(cost)
        return result

    def _assert_limit(self):
        if self._limit is None:
            return
        requests_count = sum(self._count.values())
        error_msg = 'Over limit of Google API requests. ' \
                    'There are {} requests allowed in current tracker'.format(self._limit)
        assert requests_count <= self._limit, error_msg
