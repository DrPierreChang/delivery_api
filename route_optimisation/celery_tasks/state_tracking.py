import logging

from django.contrib.contenttypes.models import ContentType

from delivery.celery import app
from route_optimisation.models import DriverRoute, RouteOptimisation, RoutePoint
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

logger = logging.getLogger('optimisation')


@app.task()
def track_state_change(order_id):
    state_change_service = StateChange()
    point = state_change_service.find_changed_point(order_id)
    if not point:
        return

    order = point.point_object
    route = point.route
    if order.status in state_change_service.start_statuses:
        state_change_service.process_possible_running(route)
    elif order.status in state_change_service.end_statuses:
        state_change_service.process_possible_finished(route)


class StateChange:
    start_statuses = (OrderStatus.PICK_UP, OrderStatus.PICKED_UP, OrderStatus.IN_PROGRESS, OrderStatus.WAY_BACK,)
    end_statuses = (OrderStatus.DELIVERED, OrderStatus.FAILED,)

    def __init__(self):
        self.order_ct = ContentType.objects.get_for_model(Order)

    def find_changed_point(self, order_id):
        return RoutePoint.objects.filter(
            point_content_type=self.order_ct, point_object_id=order_id,
            route__optimisation__state__in=(RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING),
        ).select_related('route__optimisation').prefetch_related('point_object').first()

    def process_possible_running(self, route):
        optimisation = route.optimisation
        if route.state == DriverRoute.STATE.CREATED:
            route.state_to(RouteOptimisation.STATE.RUNNING)
        if optimisation.state == RouteOptimisation.STATE.COMPLETED:
            optimisation.state_to(RouteOptimisation.STATE.RUNNING)

    def process_possible_finished(self, route):
        optimisation = route.optimisation
        qs = Order.aggregated_objects.filter_by_merchant(optimisation.merchant)
        if route.state in (DriverRoute.STATE.CREATED, DriverRoute.STATE.RUNNING):
            order_ids = RoutePoint.objects.filter(route=route, point_content_type=self.order_ct) \
                .values_list('point_object_id', flat=True)
            bad_orders = qs.filter(id__in=order_ids).exclude(status__in=self.end_statuses)
            if not bad_orders.exists():
                route.state_to(RouteOptimisation.STATE.FINISHED)
            if not order_ids:
                route.delete()
        if optimisation.state in (RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING):
            order_ids = RoutePoint.objects.filter(route__optimisation=optimisation, point_content_type=self.order_ct) \
                .values_list('point_object_id', flat=True)
            bad_orders = qs.filter(id__in=order_ids).exclude(status__in=self.end_statuses)
            if not bad_orders.exists():
                optimisation.state_to(RouteOptimisation.STATE.FINISHED)
