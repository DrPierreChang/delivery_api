import base64
import os
import uuid

import factory

from notification.models import APNSDevice, GCMDevice, PushNotificationsSettings


class DeviceFactory(factory.django.DjangoModelFactory):
    device_id = factory.LazyAttribute(lambda self: uuid.uuid4().hex.upper())
    registration_id = factory.LazyAttribute(lambda self: base64.b64encode(os.urandom(128)).decode())
    in_use = True


class GCMDeviceFactory(DeviceFactory):
    cloud_message_type = GCMDevice.GCM

    class Meta:
        model = GCMDevice


class FCMDeviceFactory(DeviceFactory):
    cloud_message_type = GCMDevice.FCM

    class Meta:
        model = GCMDevice


class FCMDeviceFactoryIOS(DeviceFactory):
    cloud_message_type = GCMDevice.FCM
    device_type = GCMDevice.IOS

    class Meta:
        model = GCMDevice


class APNSDeviceFactory(DeviceFactory):
    class Meta:
        model = APNSDevice


class PushNotificationsSettingsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PushNotificationsSettings

    fcm_key = factory.LazyAttribute(lambda self: base64.b64encode(os.urandom(128)))
    gcm_key = factory.LazyAttribute(lambda self: base64.b64encode(os.urandom(128)))
