import logging
from operator import attrgetter
from typing import List, Optional, Tuple

from route_optimisation.const import GOOGLE_API_REQUESTS_LIMIT, RoutePointKind
from route_optimisation.dima import RadaroDimaCache
from route_optimisation.engine import set_dima_cache
from route_optimisation.logging import move_dummy_optimisation_log
from route_optimisation.models import DriverRoute, DummyOptimisation, RouteOptimisation, RoutePoint
from routing.context_managers import GoogleApiRequestsTracker
from routing.google import GoogleClient

from .base import MovingPreliminaryResult, update_points, update_route_from_updated_points
from .re_optimise_helpers import ExistingRouteOptimiseHelper, NewAdvancedRouteOptimisationHelper, NewRouteOptimiseHelper

logger = logging.getLogger('optimisation')


class MoveOrderPrepareService:
    def __init__(self, optimisation):
        self.optimisation = optimisation

    def prepare(self, points: List[RoutePoint], source_route: DriverRoute, target_driver, initiator, context) \
            -> MovingPreliminaryResult:
        moved_points = list(self.get_moved_points(points, source_route))
        with GoogleClient.track_merchant(self.optimisation.merchant):
            original_route, original_points = self.get_updated_source_route(moved_points, source_route)
        dummy_optimisation, target_optimisation, target_route, target_points = self.optimise_target_route(
            target_driver, source_route, moved_points, initiator, context
        )
        return MovingPreliminaryResult(
            original_route, original_points, target_route, target_points,
            dummy_optimisation=dummy_optimisation, target_optimisation=target_optimisation,
        )

    def get_distance_matrix_cache(self):
        return RadaroDimaCache()

    def get_pp_distance_matrix_cache(self):
        return RadaroDimaCache(polylines=True)

    def optimise_target_route(self, driver, source_route, moved_points, initiator, context) \
            -> Tuple[Optional[DummyOptimisation], Optional[RouteOptimisation], DriverRoute, List[RoutePoint]]:
        raise NotImplementedError()

    def get_moved_points(self, points: List[RoutePoint], source_route: DriverRoute):
        point_object_ids = list(map(attrgetter('point_object_id'), points))
        source_route_points = source_route.points \
            .filter(point_kind__in=(RoutePointKind.PICKUP, RoutePointKind.DELIVERY)) \
            .order_by('number')
        for point in source_route_points:
            if point.point_kind == RoutePointKind.PICKUP:
                object_id = point.point_object_id if point.point_object.concatenated_order_id is None \
                    else point.point_object.concatenated_order_id
                if object_id in point_object_ids:
                    yield point
            else:
                if point.point_object_id in point_object_ids:
                    yield point

    def get_updated_source_route(self, deleted_points: List[RoutePoint], route: DriverRoute):
        with set_dima_cache(self.get_pp_distance_matrix_cache()):
            api_requests_tracker = GoogleApiRequestsTracker(limit=GOOGLE_API_REQUESTS_LIMIT)
            try:
                with api_requests_tracker:
                    return self._get_updated_source_route(deleted_points, route)
            finally:
                self.optimisation.backend.track_api_requests_stat(api_requests_tracker)

    def _get_updated_source_route(self, deleted_points: List[RoutePoint], route: DriverRoute):
        target_route = DriverRoute.objects.get(id=route.id)
        points = list(target_route.points.all()
                      .exclude(id__in=map(attrgetter('id'), deleted_points))
                      .exclude(point_kind=RoutePointKind.BREAK)
                      .order_by('number'))
        update_points(target_route, points)
        update_route_from_updated_points(target_route, points)
        return target_route, points

    def _save_log_after_error(self, dummy_optimisation):
        if dummy_optimisation is None:
            return
        move_dummy_optimisation_log(dummy_optimisation, self.optimisation)


class SoloMoveOrderPrepareService(MoveOrderPrepareService):
    def optimise_target_route(self, driver, source_route, moved_points, initiator, context):
        helper = NewRouteOptimiseHelper(
            source_route.optimisation,
            dima_cache=self.get_distance_matrix_cache(),
            pp_dima_cache=self.get_pp_distance_matrix_cache(),
        )
        try:
            helper.prepare(initiator, driver, moved_points, context)
            result = helper.optimise()
            result_route, result_points = helper.finish(result, moved_points=moved_points)
        except Exception:
            self._save_log_after_error(helper.dummy_optimisation)
            raise
        return helper.dummy_optimisation, None, result_route, result_points


class AdvancedMoveOrderPrepareService(MoveOrderPrepareService):
    def optimise_target_route(self, driver, source_route, moved_points, initiator, context):
        target_route = DriverRoute.objects.filter(
            optimisation=self.optimisation, driver=driver,
            state__in=(DriverRoute.STATE.CREATED, DriverRoute.STATE.RUNNING),
        ).first()
        if target_route:
            helper = ExistingRouteOptimiseHelper(
                target_route,
                source_route.optimisation,
                dima_cache=self.get_distance_matrix_cache(),
                pp_dima_cache=self.get_pp_distance_matrix_cache(),
            )
        else:
            helper = NewAdvancedRouteOptimisationHelper(
                source_route.optimisation,
                dima_cache=self.get_distance_matrix_cache(),
                pp_dima_cache=self.get_pp_distance_matrix_cache(),
            )
        try:
            helper.prepare(initiator, driver, moved_points, context)
            result = helper.optimise()
            result_route, result_points = helper.finish(result, moved_points=moved_points, target_route=target_route)
        except Exception:
            self._save_log_after_error(helper.dummy_optimisation)
            raise
        return helper.dummy_optimisation, source_route.optimisation, result_route, result_points
