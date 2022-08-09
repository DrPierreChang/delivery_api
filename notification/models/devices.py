from django.contrib.contenttypes.models import ContentType
from django.db import models

from push_notifications.models import Device as PushDevice

from ..utils import filter_dict


class DeviceManager(models.Manager):
    def get_queryset(self):
        return DeviceQuerySet(self.model)

    get_query_set = get_queryset


class DeviceQuerySet(models.query.QuerySet):
    def send_message(self, message, **kwargs):
        if self:
            application_ids = self.values_list('application_id', flat=True).distinct() or (None,)
            for app_id in application_ids:
                pks, real_types = zip(*self.filter(application_id=app_id).values_list('pk', 'real_type'))
                real_types = set(real_types)
                for real_type_id in real_types:
                    Model = ContentType.objects.get_for_id(real_type_id).model_class()
                    Model.objects.filter(pk__in=pks) \
                        .send_message(message, application_id=app_id, **filter_dict(kwargs, Model.EXTRA_BULK_ARGS))


class Device(PushDevice):
    real_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)

    app_name = models.CharField(max_length=100, null=True, blank=True)
    app_version = models.CharField(max_length=100, null=True, blank=True)
    device_name = models.CharField(max_length=100, null=True, blank=True)
    os_version = models.CharField(max_length=100, null=True, blank=True)
    api_version = models.PositiveIntegerField(default=1)

    in_use = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True, verbose_name='Last activity at')
    objects = DeviceManager()

    class Meta(PushDevice.Meta):
        abstract = False

    def _get_real_type(self):
        return ContentType.objects.get_for_model(type(self))

    def save(self, *args, **kwargs):
        if not self.id:
            self.real_type = self._get_real_type()
            if self.user and self.user.current_merchant:
                self.application_id = getattr(self.user.current_merchant, 'push_notifications_settings_id', None)
        super(Device, self).save(*args, **kwargs)

    def cast(self):
        """Get child object"""
        return self.real_type.get_object_for_this_type(pk=self.pk)

    def __str__(self):
        return u"%s for %s" % (self.__class__.__name__, self.user or "unknown user")

    def send_message(self, message, **kwargs):
        obj = self.cast()
        kwargs = filter_dict(kwargs, obj.EXTRA_ARGS)
        obj.send_message(message, application_id=self.application_id, **kwargs)


__all__ = ['Device', ]
