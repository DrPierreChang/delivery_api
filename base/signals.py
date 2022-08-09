from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import Signal, receiver

from base.models import Invite, Member
from radaro_router.celery_tasks import (
    create_radaro_router_instance,
    delete_radaro_router_instance,
    update_radaro_router_instance,
)
from radaro_router.serializers import RadaroRouterInviteSerializer, RadaroRouterUserSerializer

logout_event = Signal(providing_args=['user'])

post_bulk_create = Signal(providing_args=['instances'])


def get_serializer_class(instance_type):
    delivery_router_serializers_map = {
        'Member': RadaroRouterUserSerializer,
        'Invite': RadaroRouterInviteSerializer
    }
    return delivery_router_serializers_map[instance_type]


def create_routing_instance(instance):
    if settings.TESTING_MODE:
        return
    serializer_class = get_serializer_class(type(instance).__name__)
    serializer = serializer_class(instance)
    instance.create_radaro_router(serializer.data)
    transaction.on_commit(lambda: create_radaro_router_instance.delay(instance.radaro_router.id, serializer.data))


def update_routing_instance(instance):
    if not instance.has_changed or not instance.radaro_router or settings.TESTING_MODE:
        return
    serializer_class = get_serializer_class(type(instance).__name__)
    serializer = serializer_class(instance)
    extra = serializer.data
    if not instance.radaro_router.remote_id:
        instance.update_radaro_router(extra=extra)
        return
    transaction.on_commit(lambda: update_radaro_router_instance.delay(instance.radaro_router.id, serializer.data))


@receiver(post_save, sender=Member)
@receiver(post_save, sender=Invite)
def handle_routing_instance_save(instance, created, *args, **kwargs):
    if type(instance).__name__ == 'Member' and instance.role == instance.NOT_DEFINED:
        # This is necessary so that the administrator of the admin page does not try to create a RadaroRouter.
        return
    if getattr(instance, 'deleted', False):
        return
    if not instance.radaro_router:
        create_routing_instance(instance)
        return
    update_routing_instance(instance)


@receiver(pre_delete, sender=Member)
@receiver(pre_delete, sender=Invite)
def delete_routing_instance(sender, instance, *args, **kwargs):
    if not (instance.radaro_router and instance.radaro_router.remote_id) or settings.TESTING_MODE:
        return
    if getattr(instance, 'deleted', False):
        return
    router_id = instance.radaro_router.id
    instance.unset_radaro_router()
    transaction.on_commit(lambda: delete_radaro_router_instance.delay(router_id))
