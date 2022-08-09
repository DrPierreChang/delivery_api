from django.conf import settings
from django.http import JsonResponse
from django.views.defaults import bad_request, server_error

from rest_framework import status

from base.utils.exceptions.mobile import mobile_exception_formatting


def custom_bad_request(request, exception, *args, **kwargs):
    if request.version == settings.MOBILE_API_VERSION:
        data = mobile_exception_formatting({
                'message': 'Bad Request',
                'code': 'unknown',
            })
        return JsonResponse(data, status=status.HTTP_400_BAD_REQUEST)

    return bad_request(request, exception, *args, **kwargs)


def custom_server_error(request, *args, **kwargs):
    if request.version == settings.MOBILE_API_VERSION:
        data = mobile_exception_formatting({
                'message': 'Server Error',
                'code': 'unknown',
            })
        return JsonResponse(data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return server_error(request, *args, **kwargs)
