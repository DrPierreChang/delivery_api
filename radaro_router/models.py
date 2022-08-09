from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import JSONField
from django.db import models

from radaro_router.utils import DeliveryRouter


class RadaroRouter(models.Model):
    DELETED = -1
    CREATED = 0
    UPDATED = 1

    action_choices = (
        (DELETED, 'Deleted'),
        (CREATED, 'Created'),
        (UPDATED, 'Updated')
    )

    remote_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    synced = models.BooleanField(default=False)
    last_action = models.IntegerField(choices=action_choices, default=CREATED)
    extra = JSONField(null=True, blank=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        unique_together = ('content_type', 'object_id')

    def __str__(self):
        return 'Radaro router instance: {}'.format(self.remote_id)

    def set_remote_id(self, remote_id):
        self.remote_id = remote_id
        self.save(update_fields=('remote_id', ))

    def _sync_new_object(self, remote_id):
        self.remote_id = remote_id
        self.synced = True
        self.save(update_fields=('remote_id', 'synced'))

    def set_object_null(self):
        self.object_id = None
        self.save(update_fields=('object_id', ))

    def start_sync(self, action, extra=None):
        self.synced = False
        self.last_action = action
        self.extra = extra
        self.save(update_fields=('synced', 'last_action', 'extra'))

    def end_sync(self):
        self.synced = True
        self.save(update_fields=('synced', ))

    def create_remote_instance(self, data):
        with DeliveryRouter(settings.RADARO_ROUTER_TOKEN) as client:
            create = getattr(client, 'create_{}'.format(self.content_type.model))
            response = create(data)
            self._sync_new_object(response.get('id'))

    def update_remote_instance(self, data):
        with DeliveryRouter(settings.RADARO_ROUTER_TOKEN) as client:
            update = getattr(client, 'update_{}'.format(self.content_type.model))
            update(self.remote_id, data=data)

    def delete_remote_instance(self):
        instance_type = self.content_type.model
        if not self.remote_id:
            return
        with DeliveryRouter(settings.RADARO_ROUTER_TOKEN) as client:
            delete = getattr(client, 'delete_{}'.format(instance_type))
            delete(self.remote_id)

    def deactivate_remote_instance(self):
        instance_type = self.content_type.model
        if not self.remote_id:
            return
        with DeliveryRouter(settings.RADARO_ROUTER_TOKEN) as client:
            deactivate = getattr(client, 'deactivate_{}'.format(instance_type))
            deactivate(self.remote_id)

    def activate_remote_instance(self):
        instance_type = self.content_type.model
        if not self.remote_id:
            return
        with DeliveryRouter(settings.RADARO_ROUTER_TOKEN) as client:
            activate = getattr(client, 'activate_{}'.format(instance_type))
            activate(self.remote_id)


class RadaroRouterRelationMixin(models.Model):
    radaro_router_manager = GenericRelation(RadaroRouter)

    class Meta:
        abstract = True

    def create_radaro_router(self, extra=None):
        extra = extra or {}
        if not self.radaro_router:
            self.radaro_router_manager.create(extra=extra)

    def update_radaro_router(self, **kwargs):
        self.radaro_router_manager.update(**kwargs)

    def unset_radaro_router(self):
        self.radaro_router_manager.update(object_id=None)

    @property
    def radaro_router(self):
        return self.radaro_router_manager.last()
