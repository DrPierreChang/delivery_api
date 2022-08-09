from django.db import models

from push_notifications.apns import APNSError, apns_send_message

from .devices import Device
from .notifications import save_notification


class APNSDeviceManager(models.Manager):
    def get_queryset(self):
        return APNSDeviceQuerySet(self.model)

    get_query_set = get_queryset  # Django < 1.6 compatiblity


class APNSDeviceQuerySet(models.query.QuerySet):
    @save_notification
    def send_message(self, message, **kwargs):
        if self:
            from push_notifications.apns import apns_send_bulk_message

            alert, sound = (None, None) if kwargs.get('content_available', False) \
                else (message['data']['text'], '"default"')

            try:
                return apns_send_bulk_message(
                    registration_ids=list(self.values_list("registration_id", flat=True)),
                    alert=alert, sound=sound, extra=message, **kwargs
                )
            except APNSError as exc:
                for registration_id in list(self.values_list("registration_id", flat=True)):
                    try:
                        return apns_send_message(
                            registration_id=registration_id, alert=alert,
                            badge=0, extra=message, sound=sound, **kwargs)
                    except APNSError as exc:
                        pass


class APNSDevice(Device):
    EXTRA_BULK_ARGS = [
        'badge',
        'sound',
        'category',
        'content_available',
        'action_loc_key',
        'loc_key',
        'loc_args',
        'extra',
        'expiration',
        'priority',
    ]
    EXTRA_ARGS = EXTRA_BULK_ARGS + ['identifier', 'socket']

    device_id = models.CharField(verbose_name="Device ID", blank=False, null=True, unique=True, max_length=255,
                                 help_text="UDID / UIDevice.identifierForVendor()", db_index=True)
    registration_id = models.CharField(verbose_name="Registration ID", max_length=256, unique=True)

    objects = APNSDeviceManager()

    class Meta:
        verbose_name = "APNS device"

    @save_notification
    def send_message(self, message, **kwargs):
        alert, sound = (None, None) if kwargs.get('content_available', False) \
            else (message['data']['text'], '"default"')

        apns_send_message(registration_id=self.registration_id, alert=alert,
                          badge=0, extra=message, sound=sound, ** kwargs)


__all__ = ['APNSDevice', ]
