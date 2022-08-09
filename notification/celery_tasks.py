from __future__ import absolute_import

from django.apps import apps

import sentry_sdk

from delivery.celery import app
from notification.models import Device


@app.task()
def send_device_notification(message, content_available, device_ids=None):
    device_ids = device_ids or []
    try:
        Device.objects.filter(id__in=device_ids).send_message(
            message, content_available=content_available
        )
    except Exception as ex:
        sentry_sdk.capture_exception(ex)


@app.task()
def send_template_notification(model_name, object_id):
    Model = apps.get_model('notification', model_name)
    obj = Model.objects.filter(id=object_id).first()

    if not obj:
        return

    notification = obj.build_message()
    try:
        notification.send()
    except Exception as exc:
        obj.dispatch(is_sent=False)
        sentry_sdk.capture_exception(exc)
    else:
        obj.handle_message(notification)
    finally:
        obj.save()
