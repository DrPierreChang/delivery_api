import logging

from django.conf import settings
from django.db import transaction

from route_optimisation.celery_tasks import ptv_import_calculate_driving_distance
from route_optimisation.const import OPTIMISATION_TYPES
from route_optimisation.models import DriverRoute, RouteOptimisation, RoutePoint
from route_optimisation.models.driver_route import DriverRouteColor
from route_optimisation.push_messages.composers import NewRoutePushMessage
from route_optimisation.utils.backends.base import OptimisationBackend
from route_optimisation.utils.backends.registry import backend_registry
from route_optimisation.utils.deletion import DeleteService
from route_optimisation.utils.managing import SequenceReorderService

logger = logging.getLogger('optimisation')


@backend_registry.register(OPTIMISATION_TYPES.PTV_EXPORT)
class PTVExportOptimisationBackend(OptimisationBackend):
    deletion_class = DeleteService
    sequence_reorder_service_class = SequenceReorderService

    def on_create(self, options=None, serializer_context=None):
        super().on_create()
        self.optimisation.state_to(RouteOptimisation.STATE.OPTIMISING)
        try:
            with transaction.atomic():
                self._create_routes(options.pop('driver_routes', []))
                for driver_route in self.optimisation.routes.all():
                    driver_route.driver.send_versioned_push(NewRoutePushMessage(self.optimisation, driver_route))
                self.optimisation.state_to(RouteOptimisation.STATE.COMPLETED)
                callback = lambda: ptv_import_calculate_driving_distance.delay(self.optimisation.id)
                callback() if settings.TESTING_MODE else transaction.on_commit(callback)
        except Exception as exc:
            self.on_fail(exception=exc)
        finally:
            self.optimisation.delayed_task.complete()
            self.optimisation.delayed_task.save(update_fields=('status',))

    def _create_routes(self, drivers_routes):
        instance = self.optimisation
        color_generator = DriverRouteColor.gen()
        for route in drivers_routes:
            route_points = route.pop('route_points', [])
            driver_route = DriverRoute.objects.create(optimisation=instance, color=next(color_generator), **route)
            RoutePoint.objects.bulk_create([RoutePoint(route=driver_route, **point) for point in route_points])
