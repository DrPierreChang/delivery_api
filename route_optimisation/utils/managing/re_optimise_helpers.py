import logging

from route_optimisation.const import RoutePointKind
from route_optimisation.dima import RadaroDimaCache
from route_optimisation.engine import Algorithms
from route_optimisation.exceptions import MoveOrdersError
from route_optimisation.logging import EventType
from route_optimisation.logging.logs.progress import ProgressConst
from route_optimisation.models import DummyOptimisation, EngineRun
from route_optimisation.optimisation_events import RadaroEventsHandler
from route_optimisation.utils.managing import MoveOrdersType
from routing.google import GoogleClient, merchant_registry

from ...models.engine_run import EngineOptions
from .base import MoveOrdersType

logger = logging.getLogger('optimisation')


class RouteReOptimiseHelper:
    dummy_backend = None

    def __init__(self, source_optimisation, dima_cache=None, pp_dima_cache=None):
        self.source_optimisation = source_optimisation
        self.dummy_optimisation = None
        self.dima_cache = dima_cache or RadaroDimaCache()
        self.pp_dima_cache = pp_dima_cache or RadaroDimaCache(polylines=True)

    def optimise(self):
        result = self.engine_run(Algorithms.ONE_DRIVER)
        if not result.good or len(result.skipped_orders) > 0:
            result = self.engine_run(Algorithms.SOFT_ONE_DRIVER)
            if not result.good or len(result.skipped_orders) > 0:
                raise MoveOrdersError('Can not place new orders in target drivers route')
        return result

    def engine_run(self, algorithm):
        success = False
        try:
            options = EngineOptions(
                params=self.dummy_optimisation.backend.get_params_for_engine(),
                algorithm=algorithm, algorithm_params={'search_time_limit': 2}
            )
            engine_run = EngineRun.objects.create(optimisation=self.source_optimisation, engine_options=options)
            engine_run.dummy_optimisation = self.dummy_optimisation
            logger.info(None, extra=dict(obj=self.dummy_optimisation, event=EventType.PROGRESS,
                                         event_kwargs=dict(stage=ProgressConst.START), labels=[], ))
            result = engine_run.run_engine(dima_cache=self.dima_cache)

            success = result.good
            if success:
                self.dummy_optimisation.backend.post_processing(result, distance_matrix_cache=self.pp_dima_cache)
            if not result.good:
                self.dummy_optimisation.backend.on_fail(engine_result=result)
        except Exception as exc:
            self.dummy_optimisation.backend.on_fail(exception=exc)
        finally:
            logger.info(None, extra=dict(obj=self.dummy_optimisation, event=EventType.PROGRESS,
                                         event_kwargs=dict(stage=ProgressConst.FINISH, success=success), labels=[], ))
        return result

    def prepare(self, initiator, driver, moved_points, serializer_context):
        self.dummy_optimisation = DummyOptimisation(
            self.source_optimisation,  self.source_optimisation.day, self.source_optimisation.merchant,
            initiator, self.dummy_backend
        )
        options = {
            key: self.source_optimisation.options.get(key)
            for key in ['start_place', 'start_hub', 'start_location', 'end_place', 'end_hub', 'end_location',
                        'use_vehicle_capacity', 'working_hours', 'service_time', 'pickup_service_time']
            if key in self.source_optimisation.options
        }
        self.update_dummy_optimisation_options(options, driver, moved_points)
        self.dummy_optimisation.backend.on_create(options, serializer_context)

    def update_dummy_optimisation_options(self, options, driver, moved_points):
        options.update({
            'jobs_ids': list(set(p.point_object_id for p in moved_points)), 'drivers_ids': [driver.id]
        })

    def finish(self, engine_result, **params):
        with GoogleClient.track_merchant(self.dummy_optimisation.merchant):
            return self.dummy_optimisation.backend.on_finish(engine_result, **params)


class NewRouteOptimiseHelper(RouteReOptimiseHelper):
    dummy_backend = MoveOrdersType.NEW_SOLO


class NewAdvancedRouteOptimisationHelper(RouteReOptimiseHelper):
    dummy_backend = MoveOrdersType.NEW_ADVANCED


class ExistingRouteOptimiseHelper(RouteReOptimiseHelper):
    dummy_backend = MoveOrdersType.EXISTING_ADVANCED

    def __init__(self, target_route, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_route = target_route

    def update_dummy_optimisation_options(self, options, driver, moved_points):
        route_points = moved_points + list(self.target_route.points.filter(
            point_kind__in=(RoutePointKind.PICKUP, RoutePointKind.DELIVERY)))
        options.update({
            'jobs_ids': list(set(p.point_object_id for p in route_points)), 'drivers_ids': [driver.id]
        })
