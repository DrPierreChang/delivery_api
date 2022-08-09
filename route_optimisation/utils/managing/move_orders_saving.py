import logging
from operator import attrgetter

from django.db import transaction

from reporting.signals import create_event
from route_optimisation.celery_tasks.state_tracking import StateChange
from route_optimisation.const import OPTIMISATION_TYPES, RoutePointKind
from route_optimisation.logging import EventType, move_dummy_optimisation_log
from route_optimisation.models import DriverRoute, DummyOptimisation, OptimisationTask, RouteOptimisation
from route_optimisation.push_messages.composers import NewRoutePushMessage, RouteChangedMessage
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

from .base import MovingPreliminaryResult

logger = logging.getLogger('optimisation')


class MoveOrderSaveService:
    def __init__(self, optimisation):
        self.optimisation = optimisation

    @transaction.atomic
    def save(self, preliminary_result: MovingPreliminaryResult, initiator):
        reassigned_orders = self._reassign_driver(preliminary_result)
        source_notify_customers = self._save_source_route_data(preliminary_result)
        target_notify_customers = self._save_target_route_data(preliminary_result)
        StateChange().process_possible_finished(DriverRoute.objects.get(id=preliminary_result.source_route.id))
        source_changed, _ = self._set_customers_notified(
            preliminary_result, source_notify_customers, target_notify_customers
        )
        self._log(preliminary_result, reassigned_orders, initiator)
        if not source_changed:
            create_event(
                {}, {}, initiator=initiator, instance=preliminary_result.source_route.optimisation,
                sender=None, force_create=True
            )

    def _reassign_driver(self, preliminary_result: MovingPreliminaryResult):
        route, points = preliminary_result.target_route, preliminary_result.result_target_points
        reassigned_orders = []
        for point in points:
            if point.point_kind != RoutePointKind.DELIVERY:
                continue
            if point.point_object.driver == route.driver:
                continue
            reassigned_orders.append(point.point_object)
        Order.aggregated_objects.bulk_status_change(
            order_ids=list(map(attrgetter('id'), reassigned_orders)),
            to_status=OrderStatus.ASSIGNED,
            driver=route.driver,
        )
        return reassigned_orders

    def _save_source_route_data(self, preliminary_result: MovingPreliminaryResult):
        route, points = preliminary_result.source_route, preliminary_result.result_source_points
        route.save()
        notify_customers = False
        used_existing_points = set()
        for point in points:
            point.route = route
            point.save()
            used_existing_points.add(point.id)
            if point.point_kind == RoutePointKind.DELIVERY \
                    and point.start_time_known_to_customer != point.start_time:
                notify_customers = True
        route.points.all().exclude(id__in=used_existing_points).filter(point_kind=RoutePointKind.BREAK).delete()
        route.driver.send_versioned_push(RouteChangedMessage(route.optimisation, route))
        return notify_customers

    def _save_target_route_data(self, preliminary_result: MovingPreliminaryResult) -> bool:
        route, points = preliminary_result.target_route, preliminary_result.result_target_points
        is_new_route = route.pk is None
        route.save()
        notify_customers = False
        used_existing_points = set()
        for point in points:
            point.route = route
            point.save()
            used_existing_points.add(point.id)
            if point.point_kind == RoutePointKind.DELIVERY \
                    and point.start_time_known_to_customer != point.start_time:
                notify_customers = True
        route.points.all().exclude(id__in=used_existing_points).filter(point_kind=RoutePointKind.BREAK).delete()
        notification_class = NewRoutePushMessage if is_new_route else RouteChangedMessage
        route.driver.send_versioned_push(notification_class(route.optimisation, route))
        return notify_customers

    def _set_customers_notified(self, preliminary_result: MovingPreliminaryResult,
                                source_notify_customers: bool, target_notify_customers: bool) -> (bool, bool):
        raise NotImplementedError()

    def _log(self, preliminary_result: MovingPreliminaryResult, reassigned_orders, initiator):
        source_route, target_route = preliminary_result.source_route, preliminary_result.target_route
        logger.info(None, extra=dict(
            obj=source_route.optimisation, event=EventType.MOVE_JOBS,
            event_kwargs=dict(source_route=source_route, target_route=target_route,
                              jobs=reassigned_orders, initiator=initiator)
        ))
        dummy_optimisation, target = preliminary_result.dummy_optimisation, preliminary_result.target_optimisation
        move_dummy_optimisation_log(dummy_optimisation, target)


class SoloMoveOrderSaveService(MoveOrderSaveService):
    def _save_target_route_data(self, preliminary_result: MovingPreliminaryResult) -> bool:
        route = preliminary_result.target_route
        dummy_optimisation: DummyOptimisation = preliminary_result.dummy_optimisation
        new_optimisation = RouteOptimisation(
            day=dummy_optimisation.day, type=OPTIMISATION_TYPES.SOLO,
            merchant=dummy_optimisation.merchant, created_by=dummy_optimisation.created_by,
            state=RouteOptimisation.STATE.COMPLETED, optimisation_options=dummy_optimisation.optimisation_options,
            options=dummy_optimisation.options,
        )
        new_optimisation.save()
        logger.info(None, extra=dict(
            obj=new_optimisation, event=EventType.CREATE_RO_AFTER_MOVE_JOBS,
            event_kwargs=dict(source_route=preliminary_result.source_route, target_route=route,
                              initiator=dummy_optimisation.created_by)
        ))
        task = OptimisationTask(optimisation=new_optimisation)
        task.begin()
        task.complete()
        task.save()
        route.optimisation = new_optimisation
        preliminary_result.target_optimisation = new_optimisation
        return super()._save_target_route_data(preliminary_result)

    def _set_customers_notified(self, preliminary_result: MovingPreliminaryResult,
                                source_notify_customers: bool, target_notify_customers: bool):
        source_route, target_route = preliminary_result.source_route, preliminary_result.target_route
        source_changed, target_changed = False, False
        if source_notify_customers and source_route.optimisation.customers_notified:
            source_route.optimisation.customers_notified = False
            source_route.optimisation.save(update_fields=('customers_notified',))
            source_changed = True
        if target_notify_customers and target_route.optimisation.customers_notified:
            target_route.optimisation.customers_notified = False
            target_route.optimisation.save(update_fields=('customers_notified',))
            target_changed = True
        return source_changed, target_changed

    def _log(self, preliminary_result: MovingPreliminaryResult, reassigned_orders, initiator):
        super()._log(preliminary_result, reassigned_orders, initiator)
        source_route, target_route = preliminary_result.source_route, preliminary_result.target_route
        optimisation = preliminary_result.target_optimisation
        logger.info(None, extra=dict(
            obj=optimisation, event=EventType.MOVE_JOBS,
            event_kwargs=dict(source_route=source_route, target_route=target_route,
                              jobs=reassigned_orders, initiator=initiator)
        ))


class AdvancedMoveOrderSaveService(MoveOrderSaveService):
    def _save_target_route_data(self, preliminary_result: MovingPreliminaryResult) -> bool:
        route = preliminary_result.target_route
        optimisation = preliminary_result.target_optimisation
        route.optimisation = optimisation
        return super()._save_target_route_data(preliminary_result)

    def _set_customers_notified(self, preliminary_result: MovingPreliminaryResult,
                                source_notify_customers: bool, target_notify_customers: bool) -> (bool, bool):
        source_route = preliminary_result.source_route
        if (source_notify_customers or target_notify_customers) and source_route.optimisation.customers_notified:
            source_route.optimisation.customers_notified = False
            source_route.optimisation.save(update_fields=('customers_notified',))
            return True, False
        return False, False
