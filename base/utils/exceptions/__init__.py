from django.conf import settings

from .legacy import legacy_exception_handler
from .mobile import mobile_exception_handler


def custom_exception_handler(exc, context):
    if getattr(context['request'], 'version', None) and context['request'].version == settings.MOBILE_API_VERSION:
        return mobile_exception_handler(exc, context)
    return legacy_exception_handler(exc, context)
