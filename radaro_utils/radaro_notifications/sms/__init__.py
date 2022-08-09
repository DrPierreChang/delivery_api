from django.conf import settings
from django.utils.module_loading import import_string

from radaro_utils.radaro_notifications.sms.message import SMSMessage

__all__ = ['get_sms_settings', 'get_connection', 'send_sms', 'empty']


class empty:
    pass


def get_sms_settings(name, default=empty, required=True, kwargs=None, service_name=None):
    kwargs = kwargs or {}
    value = kwargs.get(name, None)

    if value and not required:
        return value

    setting = name.upper()
    if service_name:
        setting = "{}_{}".format(service_name.upper(), setting)
    sms_setting = "SMS_{}".format(setting)

    try:
        return settings.SMS_SENDING_PARAMETERS[setting]
    except (AttributeError, KeyError):
        try:
            return getattr(settings, sms_setting)
        except (AttributeError, KeyError):
            if default is empty:
                raise ValueError('provide setting')
            return default


def get_connection(backend=None, fail_silently=False, **kwargs):
    """Load an sms backend and return an instance of it.

    If backend is None (default) settings.SMS_BACKEND is used.

    Both fail_silently and other keyword arguments are used in the
    constructor of the backend.
    """
    klass = import_string(backend or settings.SMS_BACKEND)
    return klass(fail_silently=fail_silently, **kwargs)


def send_sms(message, sender, phone_number, fail_silently=False, connection=None):
    """
    Easy wrapper for sending a single sms to a phone_number.
    """
    connection = connection or get_connection(fail_silently=fail_silently)
    mail = SMSMessage(message, sender, phone_number, connection=connection)

    return mail.send()
