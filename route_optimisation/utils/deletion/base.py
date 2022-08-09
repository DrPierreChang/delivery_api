import logging
import time
from operator import itemgetter

from django.contrib.contenttypes.models import ContentType

from route_optimisation.logging import EventType
from route_optimisation.push_messages.composers import RemovedOptimisationPushMessage
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

logger = logging.getLogger('optimisation')


class DeleteService:
    def __init__(self, optimisation):
        self.optimisation = optimisation

    def delete(self, initiator, unassign, cms_user):
        unassigned_count = None
        if unassign:
            unassigned_count = self._unassign_jobs(initiator)
        for driver_route in self.optimisation.routes.all():
            driver_route.driver.send_versioned_push(RemovedOptimisationPushMessage(self.optimisation, driver_route))
        logger.info(None, extra=dict(obj=self.optimisation, event=EventType.DELETE_RO, event_kwargs={
            'unassign': unassign,
            'unassigned_count': unassigned_count,
            'initiator': initiator,
            'cms_user': cms_user,
        }))

    def _unassign_jobs(self, initiator):
        orders_for_unassign = self._get_orders_for_unassign()
        unassigned_count = orders_for_unassign.count()
        drivers_with_unassigned = orders_for_unassign.distinct('driver_id').values_list('driver_id', flat=True)
        unassigned_orders_counter = dict()
        for driver in drivers_with_unassigned:
            orders_ids = orders_for_unassign.filter(driver=driver).values_list('id', flat=True)
            unassigned_orders_counter[int(time.time())] = orders_ids.count()
            Order.aggregated_objects.bulk_status_change(order_ids=orders_ids, to_status=OrderStatus.NOT_ASSIGNED,
                                                        initiator=initiator)

            # We need to unassign orders slowly enough, so there will be created only about 200 events per 15 seconds.
            # So /new-events/ api will work.
            period_15_sec = time.time() - 15
            unassigned_orders_counter = {k: v for k, v in unassigned_orders_counter.items() if k >= period_15_sec}
            if sum(unassigned_orders_counter.values()) > 200:
                time.sleep(15)

        return unassigned_count

    def _get_orders_for_unassign(self):
        from route_optimisation.models import RoutePoint

        order_ct = ContentType.objects.get_for_model(Order)
        existing_jobs_in_optimisation = RoutePoint.objects \
            .filter(point_content_type=order_ct, route__optimisation=self.optimisation,
                    point_object_id__in=self._get_previously_not_assigned_jobs()) \
            .values_list('point_object_id', flat=True)
        qs = Order.aggregated_objects.filter_by_merchant(self.optimisation.merchant)
        return qs.filter(status=OrderStatus.ASSIGNED, id__in=existing_jobs_in_optimisation)

    def _get_previously_not_assigned_jobs(self):
        not_assigned_jobs = (x for x in self.optimisation.optimisation_options.get('jobs', [])
                             if x['driver_member_id'] is None)
        return list(map(itemgetter('id'), not_assigned_jobs))
