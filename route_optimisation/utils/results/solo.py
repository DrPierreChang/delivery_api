import logging

from django.db import transaction

from reporting.signals import create_event
from route_optimisation.const import RoutePointKind
from route_optimisation.engine.base_classes.result import AssignmentResult
from route_optimisation.push_messages.composers import (
    NewRoutePushMessage,
    RouteChangedMessage,
    SoloOptimisationStatusChangeMessage,
)

from ...models import RoutePoint
from .base import OptimisationResult, ResultKeeper
from .move_orders import is_same_locations, is_same_points

logger = logging.getLogger('optimisation')


class SoloResultKeeper(ResultKeeper):
    def push_to_drivers(self, successful):
        if self.optimisation.created_by and self.optimisation.created_by.is_driver:
            self.optimisation.created_by.send_versioned_push(
                SoloOptimisationStatusChangeMessage(self.optimisation, successful))

        elif successful:
            for driver_route in self.optimisation.routes.all():
                driver_route.driver.send_versioned_push(NewRoutePushMessage(self.optimisation, driver_route))


class RefreshSoloResultKeeper(ResultKeeper):
    fields_for_update = ('number', 'service_time', 'driving_time', 'distance',
                         'start_time', 'end_time', 'utilized_capacity', 'path_polyline')

    def prepare(self, result: AssignmentResult) -> OptimisationResult:
        prepared_optimisation_result = super().prepare(result)
        prepared_route_info = prepared_optimisation_result.routes[0]
        route, points = prepared_route_info.route, prepared_route_info.points
        prepared_route_info.route, prepared_route_info.points = self.update_routes_points_info(route, points)
        return prepared_optimisation_result

    @transaction.atomic
    def save(self, result: AssignmentResult, optimisation_result: OptimisationResult, **params):
        if result.good:
            existing_points = self.get_existing_points()
            self.save_driver_tours(optimisation_result)
            self.process_skipped(result.skipped_orders, result.skipped_drivers)
            self.process_drivers_routes(exclude_points=existing_points)
        self.push_to_drivers(result.good)

    def save_driver_tours(self, optimisation_result: OptimisationResult):
        notify_customers = False
        for route_info in optimisation_result.routes:
            route_info.route.optimisation = self.optimisation.source_optimisation
            route_info.route.save()
            used_existing_points = set()
            for point in route_info.points:
                point.route = route_info.route
                point.next_point = None
                point.save()
                used_existing_points.add(point.id)
                if point.point_kind == RoutePointKind.DELIVERY \
                        and point.start_time_known_to_customer != point.start_time:
                    notify_customers = True
            route_info.route.points.all().exclude(id__in=used_existing_points) \
                .filter(point_kind=RoutePointKind.BREAK).delete()

            saved_points = [
                point for point in route_info.route.points.order_by('number')
                if point.point_location is not None
            ]
            for start_point, end_point in zip(saved_points[:-1], saved_points[1:]):
                start_point.next_point = end_point
                end_point.next_point = None
            RoutePoint.objects.bulk_update(saved_points, fields=['next_point'])

        if notify_customers and self.optimisation.source_optimisation.customers_notified:
            self.optimisation.source_optimisation.customers_notified = False
            self.optimisation.source_optimisation.save(update_fields=('customers_notified',))
        else:
            create_event(
                {}, {}, initiator=self.optimisation.created_by, instance=self.optimisation.source_optimisation,
                sender=None, force_create=True
            )

    def push_to_drivers(self, successful):
        if successful:
            for driver_route in self.optimisation.source_optimisation.routes.all():
                driver_route.driver.send_versioned_push(
                    RouteChangedMessage(self.optimisation.source_optimisation, driver_route))
        else:
            initiator = self.optimisation.created_by
            if initiator and initiator.is_driver:
                initiator.send_versioned_push(
                    SoloOptimisationStatusChangeMessage(self.optimisation.source_optimisation, successful))

    def get_existing_points(self):
        return {
            route.id: list(route.points.all().values_list('id', flat=True))
            for route in self.optimisation_routes
        }

    @property
    def optimisation_routes(self):
        return self.optimisation.source_optimisation.routes.all()

    def update_routes_points_info(self, route, points):
        existing_route = self.optimisation_routes.filter(driver=route.driver).first()
        assert existing_route
        existing_route_points = list(existing_route.points.all().order_by('number'))
        new_points, used_existing = [], set()
        for point in points:
            used = False
            for existing in existing_route_points:
                if existing.id in used_existing:
                    continue
                if is_same_points(point, existing) or is_same_locations(point, existing):
                    for field in self.fields_for_update:
                        setattr(existing, field, getattr(point, field))
                    new_points.append(existing)
                    used_existing.add(existing.id)
                    used = True
                    break
            if used:
                continue
            point.route = existing_route
            new_points.append(point)
        existing_route.driving_distance = route.driving_distance
        existing_route.driving_time = route.driving_time
        existing_route.total_time = route.total_time
        existing_route.start_time = route.start_time
        existing_route.end_time = route.end_time
        return existing_route, new_points
