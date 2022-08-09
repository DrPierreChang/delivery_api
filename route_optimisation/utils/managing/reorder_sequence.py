import logging
from typing import List

from django.db import transaction

from reporting.signals import create_event
from route_optimisation.const import GOOGLE_API_REQUESTS_LIMIT, RoutePointKind
from route_optimisation.dima import RadaroDimaCache
from route_optimisation.engine.dima import set_dima_cache
from route_optimisation.logging import EventType
from route_optimisation.models import DriverRoute, RoutePoint
from route_optimisation.push_messages.composers import RouteChangedMessage
from routing.context_managers import GoogleApiRequestsTracker
from routing.google import GoogleClient

from .base import update_points, update_route_from_updated_points


class SequenceReorderService:
    def __init__(self, optimisation):
        self.optimisation = optimisation

    def prepare(self, existing_route: DriverRoute, points_sequence: List[RoutePoint]):
        with GoogleClient.track_merchant(self.optimisation.merchant), set_dima_cache(self.get_distance_matrix_cache()):
            api_requests_tracker = GoogleApiRequestsTracker(limit=GOOGLE_API_REQUESTS_LIMIT)
            try:
                with api_requests_tracker:
                    update_points(existing_route, points_sequence)
                    update_route_from_updated_points(existing_route, points_sequence)
            finally:
                self.optimisation.backend.track_api_requests_stat(api_requests_tracker)

    @transaction.atomic
    def save(self, route: DriverRoute, sequence: List[RoutePoint], initiator):
        route.save(update_fields=('start_time', 'end_time', 'total_time', 'driving_time', 'driving_distance'))
        notify_customers = False
        used_existing_points = set()
        for point in sequence:
            point.save()
            used_existing_points.add(point.id)
            if point.point_kind == RoutePointKind.DELIVERY \
                    and point.start_time_known_to_customer != point.start_time:
                notify_customers = True
        route.points.all().exclude(id__in=used_existing_points).filter(point_kind=RoutePointKind.BREAK).delete()
        if notify_customers and self.optimisation.customers_notified:
            self.optimisation.customers_notified = False
            self.optimisation.save(update_fields=('customers_notified',))
        else:
            create_event({}, {}, initiator=initiator, instance=self.optimisation, sender=None, force_create=True)
        route.driver.send_versioned_push(RouteChangedMessage(self.optimisation, route))
        logger = logging.getLogger('optimisation')
        logger.info(None, extra=dict(obj=self.optimisation, event=EventType.REORDER_SEQUENCE,
                                     event_kwargs=dict(route=route, initiator=initiator)))

    def get_distance_matrix_cache(self):
        return RadaroDimaCache(polylines=True)
