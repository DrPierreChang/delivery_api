from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from merchant.models import Hub
from radaro_utils.signals import post_admin_page_action
from reporting.models import Event
from route_optimisation.celery_tasks import remove_route_point
from route_optimisation.const import RoutePointKind
from tasks.mixins.order_status import OrderStatus
from tasks.models import ConcatenatedOrder, Order


class RemoveRoutePointCase(object):
    case_type = None

    def __init__(self, event):
        self.event = event
        assert self.case_type is not None, 'Specify case_type'

    def should_remove(self):
        raise NotImplementedError()

    def remove(self):
        callback = lambda: remove_route_point.delay(
            [self._get_object_id()],
            point_content_type=self._get_point_ct(),
            event_type=self.case_type,
        )
        callback() if settings.TESTING_MODE else transaction.on_commit(callback)

    def _get_object_id(self):
        return self.event.object_id

    def _get_point_ct(self):
        # In the optimisation, the concatenated order and order are considered the same type
        concatenated_order_type = ContentType.objects.get_for_model(ConcatenatedOrder, for_concrete_model=False)
        if self.event.content_type == concatenated_order_type:
            return ContentType.objects.get_for_model(Order)
        return self.event.content_type


class OrderOrHubDeletionCase(RemoveRoutePointCase):
    case_type = 'delete'

    def should_remove(self):
        content_types = ContentType.objects.get_for_models(Order, Hub, ConcatenatedOrder, for_concrete_models=False)
        if self.event.content_type not in content_types.values():
            return False

        if self.event.event == Event.DELETED:
            return True
        if self.event.event == Event.MODEL_CHANGED and self.event.obj_dump['new_values'].get('deleted', False):
            return True

        return False

    def _get_object_id(self):
        if self.event.event == Event.DELETED:
            return self.event.obj_dump.get('id')
        return super()._get_object_id()


class PickupDeletionCase(RemoveRoutePointCase):
    case_type = 'delete'

    def should_remove(self):
        if self.event.event != Event.MODEL_CHANGED:
            return False
        order_ct = ContentType.objects.get_for_model(Order)
        if self.event.content_type != order_ct:
            return False

        have_old_pickup = self.event.obj_dump['old_values'].get('pickup_address', None) is not None
        have_new_pickup = self.event.obj_dump['new_values'].get('pickup_address', None) is not None
        return have_old_pickup and not have_new_pickup

    def remove(self):
        callback = lambda: remove_route_point.delay(
            [self._get_object_id()],
            point_content_type=self._get_point_ct(),
            event_type=self.case_type,
            point_kind=RoutePointKind.PICKUP,
        )
        callback() if settings.TESTING_MODE else transaction.on_commit(callback)


class OrderUnassignCase(RemoveRoutePointCase):
    case_type = 'unassign'

    def should_remove(self):
        ev = self.event
        return ev.event == Event.CHANGED \
            and ev.field == 'status' \
            and ev.new_value == OrderStatus.NOT_ASSIGNED \
            and ev.content_type == ContentType.objects.get_for_model(Order)


class ConcatenatedOrderUnassignCase(RemoveRoutePointCase):
    case_type = 'unassign'

    def should_remove(self):
        ev = self.event
        return ev.event == Event.CHANGED \
            and ev.field == 'status' \
            and ev.new_value == OrderStatus.NOT_ASSIGNED \
            and ev.content_type == ContentType.objects.get_for_model(ConcatenatedOrder, for_concrete_model=False)

    def _get_point_ct(self):
        return ContentType.objects.get_for_model(Order)


@receiver(post_save, sender=Event)
def remove_optimisation_route_point(sender, instance, *args, **kwargs):
    for case_klass in (OrderUnassignCase, OrderOrHubDeletionCase, PickupDeletionCase, ConcatenatedOrderUnassignCase):
        remove_route_point_case = case_klass(instance)
        if remove_route_point_case.should_remove():
            remove_route_point_case.remove()
            return


@receiver(post_admin_page_action, sender=Order)
def remove_optimisation_route_point_after_cms_action(sender, signal, ids=None, action_type=None, *args, **kwargs):
    if ids is None or action_type not in ['unassign', 'delete']:
        return
    remove_route_point.delay(ids, model=Order, event_type=action_type)
