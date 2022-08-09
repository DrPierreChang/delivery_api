import warnings

from django.core.exceptions import PermissionDenied
from django.http import Http404

from rest_framework import exceptions
from rest_framework.exceptions import ErrorDetail
from rest_framework.response import Response
from rest_framework.views import set_rollback


def mobile_exception_message_check(dict_detail):
    has_message = 'message' in dict_detail and isinstance(dict_detail['message'], str)
    has_code = 'code' in dict_detail and isinstance(dict_detail['code'], str)

    if has_message and has_code:
        return True
    return False


def mobile_exception_message_formatting(detail):
    if isinstance(detail, ErrorDetail):
        return {
            'message': detail,
            'code': detail.code
        }
    if not mobile_exception_message_check(detail):
        warnings.warn('Incorrect exception message format!', UserWarning)
    return detail


def mobile_exception_formatting(detail, errors=None):
    return {
        'detail': mobile_exception_message_formatting(detail),
        'errors': errors,
    }


def get_mobile_full_details(detail):
    if isinstance(detail, list):
        return [get_mobile_full_details(item) for item in detail]

    elif isinstance(detail, dict):
        if mobile_exception_message_check(detail):
            return detail
        return {key: get_mobile_full_details(value) for key, value in detail.items()}

    return mobile_exception_message_formatting(detail)


def get_mobile_first_detail(detail):
    if isinstance(detail, list):
        for item in detail:
            value = get_mobile_first_detail(item)
            if value:
                return value
    if isinstance(detail, dict):
        if mobile_exception_message_check(detail):
            return detail
        for item in detail.values():
            value = get_mobile_first_detail(item)
            if value:
                return value
    return detail


def mobile_exception_handler(exc, context):
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    if isinstance(exc, exceptions.APIException):
        headers = {}
        if getattr(exc, 'auth_header', None):
            headers['WWW-Authenticate'] = exc.auth_header
        if getattr(exc, 'wait', None):
            headers['Retry-After'] = '%d' % exc.wait

        data = mobile_exception_formatting(get_mobile_first_detail(exc.detail), get_mobile_full_details(exc.detail))
        set_rollback()
        return Response(data, status=exc.status_code, headers=headers)

    return None
