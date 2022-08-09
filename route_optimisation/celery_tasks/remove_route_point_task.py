import logging

from django.contrib.contenttypes.models import ContentType
from django.db import models

from delivery.celery import app
from radaro_utils.db import LockedAtomicTransaction, LockMode
from reporting.signals import create_event
from route_optimisation.celery_tasks.state_tracking import StateChange
from route_optimisation.logging import EventType
from route_optimisation.models import RouteOptimisation, RoutePoint

logger = logging.getLogger('optimisation')


@app.task()
def remove_route_point(point_object_ids, point_content_type=None, model=None, event_type='delete', **kwargs):
    assert point_content_type is not None or model is not None, 'You should specify point_content_type or model'
    if point_content_type is None:
        point_content_type = ContentType.objects.get_for_model(model, for_concrete_model=False)

    with LockedAtomicTransaction(RoutePoint, lock_mode=LockMode.EXCLUSIVE):
        # TODO: recalculate other RoutePoint's fields
        points = RoutePoint.objects.filter(
            point_object_id__in=point_object_ids, point_content_type=point_content_type, **kwargs,
        ).select_related('route__optimisation')
        routes = set()
        for point in points.exclude(route__optimisation__state=RouteOptimisation.STATE.REMOVED).order_by('-number'):
            RoutePoint.objects.filter(route=point.route, number__gt=point.number).update(number=models.F('number') - 1)
            optimisation = point.route.optimisation
            logger.info(None, extra=dict(obj=optimisation, event=EventType.REMOVE_ROUTE_POINT,
                                         event_kwargs={'model': point_content_type.model,
                                                       'point_kind': point.point_kind,
                                                       'obj_id': point.point_object_id,
                                                       'event_type': event_type}))
            routes.add(point.route)
        points.delete()

        state_change_service = StateChange()
        for route in routes:
            state_change_service.process_possible_finished(route)
            create_event({}, {}, initiator=None, instance=route.optimisation, sender=None, force_create=True)
