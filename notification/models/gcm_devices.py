import copy

from django.db import models

from push_notifications.models import CLOUD_MESSAGE_TYPES

from ..gcm import GCMError, send_bulk_message, send_message
from .devices import Device
from .notifications import save_notification


class GCMDeviceManager(models.Manager):
    def get_queryset(self):
        return GCMDeviceQuerySet(self.model)

    get_query_set = get_queryset  # Django < 1.6 compatiblity


class GCMDeviceQuerySet(models.query.QuerySet):
    @save_notification
    def send_message(self, message, **kwargs):
        if self:
            add_kwargs = {i: {} for i, _ in CLOUD_MESSAGE_TYPES}
            for cloud_type in add_kwargs:
                for device_type, _ in GCMDevice.DEVICE_TYPES:
                    registration_ids = list(self.filter(cloud_message_type=cloud_type, device_type=device_type)
                                            .values_list("registration_id", flat=True))
                    if registration_ids:
                        data = kwargs.pop("extra", {})
                        data["data"] = message

                        # This 'if' needed to fcm device can handle message in background
                        # only messages with field 'notification' and priority >= 10(?) are allowed
                        if cloud_type == GCMDevice.FCM and device_type == GCMDevice.IOS:
                            content_available = kwargs.pop("content_available", False)
                            if not content_available:
                                data["message"] = message["data"]["text"]
                                add_kwargs.update({
                                    'priority': 10,
                                    'sound': 'default'
                                })
                            else:
                                add_kwargs.update({
                                    'content_available': content_available
                                })

                        collapse_key = message['type']
                        packs = [registration_ids[i:i + 500] for i in range(0, len(registration_ids), 500)]
                        for pack in packs:
                            try:
                                return send_bulk_message(
                                    registration_ids=pack,
                                    data=copy.copy(data),
                                    cloud_type=cloud_type,
                                    collapse_key=collapse_key,
                                    **dict(kwargs, **add_kwargs))
                            except GCMError as e:
                                for registration_id in pack:
                                    return send_message(registration_ids=registration_id,
                                                        data=copy.copy(data),
                                                        cloud_type=cloud_type,
                                                        collapse_key=collapse_key,
                                                        **dict(kwargs, **add_kwargs))


class GCMDevice(Device):
    EXTRA_ARGS = (
        'extra',
        'collapse_key',
        'delay_while_idle',
        'time_to_live',
        'content_available',
    )

    # Check CLOUD_MESSAGE_TYPES
    FCM = 'FCM'
    GCM = 'GCM'

    IOS = 'ios'
    ANDROID = 'android'

    DEVICE_TYPES = (
        (IOS, 'IOS'),
        (ANDROID, 'Android')
    )

    EXTRA_BULK_ARGS = EXTRA_ARGS

    device_id = models.CharField(verbose_name="Device ID", blank=False, null=True, unique=True, max_length=255,
                                 help_text="ANDROID_ID / TelephonyManager.getDeviceId() (always as hex)", db_index=True)
    registration_id = models.TextField(verbose_name="Registration ID")

    # Unfortunately this field is used to detect type of device, since there's difference in handling notifications:
    # - IOS cannot handle `data` in background - only `notification`
    # - Android can handle `data`, but cannot customize `notification` - as a result we should handle
    # icons, sound etc. on server.
    # See more at https://firebase.google.com/docs/cloud-messaging/http-server-ref#notification-payload-support
    device_type = models.CharField(max_length=16, choices=DEVICE_TYPES, default=ANDROID)

    cloud_message_type = models.CharField(
        verbose_name="Cloud Message Type", max_length=3,
        choices=CLOUD_MESSAGE_TYPES, default="GCM",
        help_text="You should choose FCM or GCM"
    )
    objects = GCMDeviceManager()

    class Meta:
        verbose_name = "GCM device"

    @save_notification
    def send_message(self, message, **kwargs):
        data = kwargs.pop("extra", {})
        data["data"] = message
        collapse_key = message['type']

        try:
            return send_message(registration_id=self.registration_id, data=data, cloud_type=self.cloud_message_type,
                                collapse_key=collapse_key, **kwargs)
        except GCMError:
            pass
            # self.delete()


__all__ = ['GCMDevice', ]
