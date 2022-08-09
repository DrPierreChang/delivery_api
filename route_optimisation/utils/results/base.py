import copy
import logging
import time
from typing import List

from django.contrib.contenttypes.models import ContentType

from base.models import Member
from merchant.models import Hub
from route_optimisation.const import RoutePointKind
from route_optimisation.engine.base_classes.result import AssignmentResult, Point
from route_optimisation.logging import EventType
from route_optimisation.logging.logs.progress import ProgressConst
from route_optimisation.models import DriverRoute, RoutePoint
from route_optimisation.models.driver_route import DriverRouteColorPicker
from route_optimisation.models.location import DriverRouteLocation
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

logger = logging.getLogger('optimisation')


class DriverRouteResult:
    def __init__(self, driver, tour_data, color):
        self.content_types = ContentType.objects.get_for_models(Order, Hub, DriverRouteLocation)
        self.route = DriverRoute(
            driver=driver,
            options={},
            start_time=tour_data.points[0].start_time,
            end_time=tour_data.points[-1].end_time,
            total_time=tour_data.full_time,
            driving_time=tour_data.driving_time,
            driving_distance=tour_data.driving_distance,
            color=color,
        )
        self.points = list(self.make_route_point(self.route, index, point)
                           for index, point in enumerate(tour_data.points))

    def make_route_point(self, driver_route, index, point: Point):
        prototype = copy.copy(point.point_prototype)
        if not prototype:
            # For points without a model: breaks
            return RoutePoint(
                number=index + 1,
                route=driver_route,
                point_kind=point.point_kind,
                service_time=point.service_time,
                driving_time=point.driving_time,
                distance=point.distance,
                start_time=point.start_time,
                end_time=point.end_time,
                utilized_capacity=point.utilized_capacity,
                path_polyline=point.polyline,
            )

        point_id = prototype.pop('id', None)
        if point_id is None:
            created_point = point.model_class.objects.create(**prototype)
            point_id = created_point.id
        return RoutePoint(
            number=index + 1,
            route=driver_route,
            point_kind=point.point_kind,
            point_content_type=self.content_types[point.model_class],
            point_object_id=point_id,
            service_time=point.service_time,
            driving_time=point.driving_time,
            distance=point.distance,
            start_time=point.start_time,
            end_time=point.end_time,
            utilized_capacity=point.utilized_capacity,
            path_polyline=point.polyline,
        )


class OptimisationResult:
    def __init__(self, routes: List[DriverRouteResult]):
        self.routes = routes


class ResultKeeper:
    def __init__(self, optimisation):
        self.optimisation = optimisation
        self._assigned_orders_store = []

    def prepare(self, result: AssignmentResult) -> OptimisationResult:
        if result.good:
            optimisation_result = self.prepare_driver_tours(result.drivers_tours)
            return optimisation_result

    def prepare_driver_tours(self, drivers_tours):
        routes, color_picker = [], DriverRouteColorPicker()
        for driver_member_id, tour_data in drivers_tours.items():
            driver = Member.objects.get(member_id=driver_member_id)
            used_colors = list(DriverRoute.objects.get_used_colors_for_date(driver, self.optimisation.day))
            routes.append(DriverRouteResult(driver, tour_data, color_picker(used_colors)))
        return OptimisationResult(routes)

    def save(self, result: AssignmentResult, optimisation_result: OptimisationResult):
        self._assigned_orders_store = []
        try:
            if result.good:
                self.save_driver_tours(optimisation_result)
                self.process_skipped(result.skipped_orders, result.skipped_drivers)
                logger.info(None, extra=dict(obj=self.optimisation, event=EventType.PROGRESS,
                                             event_kwargs=dict(stage=ProgressConst.ASSIGN, assign_percent=30),
                                             labels=[], ))
                self._assigned_orders_store = []
                self.process_drivers_routes()
            self.push_to_drivers(result.good)
        except Exception:
            self._undo_saved()
            raise

    def _undo_saved(self):
        if self._assigned_orders_store:
            Order.aggregated_objects.bulk_status_change(
                order_ids=self._assigned_orders_store, to_status=OrderStatus.NOT_ASSIGNED, initiator=None
            )

    def prepare_and_save(self, result: AssignmentResult):
        optimisation_result = self.prepare(result)
        self.save(result, optimisation_result)

    def save_driver_tours(self, optimisation_result: OptimisationResult):
        route_points = []
        for route_info in optimisation_result.routes:
            route_info.route.optimisation = self.optimisation
            route_info.route.save()
            for point in route_info.points:
                point.route = route_info.route
                point.next_point = None
            route_points.extend(route_info.points)
        RoutePoint.objects.bulk_create(route_points)

        for route_info in optimisation_result.routes:
            points = [point for point in route_info.points if point.point_location is not None]
            for start_point, end_point in zip(points[:-1], points[1:]):
                start_point.next_point = end_point
                end_point.next_point = None
        RoutePoint.objects.bulk_update(route_points, fields=['next_point'])

    def process_skipped(self, skipped_orders, skipped_drivers):
        if len(skipped_orders) > 0:
            logger.info(None, extra=dict(obj=self.optimisation, event=EventType.SKIPPED_OBJECTS,
                                         event_kwargs={'objects': skipped_orders, 'code': 'order'}))
        if len(skipped_drivers) > 0:
            logger.info(None, extra=dict(obj=self.optimisation, event=EventType.SKIPPED_OBJECTS,
                                         event_kwargs={'objects': skipped_drivers, 'code': 'driver'}))

    def process_drivers_routes(self, exclude_points=None):
        exclude_points = exclude_points or {}
        saved_routes_counter = dict()
        for driver_route in self.optimisation_routes.select_related('driver'):
            order_ids = driver_route.points.all() \
                .filter(point_content_type__model='order', point_kind=RoutePointKind.DELIVERY) \
                .exclude(id__in=exclude_points.get(driver_route.id, [])) \
                .values_list('point_object_id', flat=True)
            orders_count = order_ids.count()
            qs = Order.aggregated_objects.filter_by_merchant(self.optimisation.merchant)
            not_assigned_orders = qs.filter(id__in=order_ids, status=Order.NOT_ASSIGNED) \
                .values_list('id', flat=True)
            previously_assigned_orders = qs.filter(id__in=order_ids).exclude(status=Order.NOT_ASSIGNED) \
                .values_list('id', flat=True)
            previously_assigned_orders = list(previously_assigned_orders)
            if not_assigned_orders.exists():
                not_assigned_orders = list(not_assigned_orders)
                Order.aggregated_objects.bulk_status_change(
                    order_ids=not_assigned_orders,
                    to_status=OrderStatus.ASSIGNED,
                    driver=driver_route.driver
                )
                self._assigned_orders_store.extend(not_assigned_orders)
                saved_routes_counter[int(time.time())] = len(not_assigned_orders)
            else:
                not_assigned_orders = []
            self.log_driver_route(driver_route, not_assigned_orders, previously_assigned_orders, orders_count)

            # We need to save orders slowly enough, so there will be created only about 200 events per 15 seconds.
            # So /new-events/ api will work.
            period_15_sec = time.time() - 15
            saved_routes_counter = {k: v for k, v in saved_routes_counter.items() if k >= period_15_sec}
            if sum(saved_routes_counter.values()) > 200:
                time.sleep(15)

    def log_driver_route(self, driver_route, from_not_assigned, previously_assigned, orders_count):
        if orders_count + len(from_not_assigned) + len(previously_assigned) == 0:
            return
        logger.info(None, extra=dict(obj=self.optimisation, event=EventType.ASSIGNED_AFTER_RO, event_kwargs={
            'driver': driver_route.driver,
            'count': orders_count,
            'assigned': from_not_assigned,
            'previously_assigned': previously_assigned,
        }))

    @property
    def optimisation_routes(self):
        return self.optimisation.routes.all()

    def push_to_drivers(self, successful):
        pass
