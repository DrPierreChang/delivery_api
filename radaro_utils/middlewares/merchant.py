import threading

from django.utils.encoding import force_bytes, force_text
from django.utils.functional import empty
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from radaro_utils.utils import base64_to_text


class AdditionalDataFromHeader(threading.local):
    merchant_id = None
    role = empty


def base64_to_number(base64_str):
    if not base64_str:
        return None

    try:
        number = int(force_text(urlsafe_base64_decode(base64_str)))
    except ValueError:
        return None

    return number


def number_to_base64(number):
    return urlsafe_base64_encode(force_bytes(number))


class SetMerchantMiddleware:
    MERCHANT_ID_HEADER = 'X-Merchant'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from_headers.merchant_id = base64_to_number(request.headers.get(self.MERCHANT_ID_HEADER))

        response = self.get_response(request)

        if from_headers.merchant_id is not None:
            response.setdefault(self.MERCHANT_ID_HEADER, number_to_base64(from_headers.merchant_id))

        return response


class CurrentRoleMiddleware:
    CURRENT_ROLE_HEADER = 'X-Role'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        role = request.headers.get(self.CURRENT_ROLE_HEADER, empty)
        from_headers.role = base64_to_text(role) if role is not empty else role

        response = self.get_response(request)

        if from_headers.role is not empty:
            response.setdefault(self.CURRENT_ROLE_HEADER, urlsafe_base64_encode(force_bytes(from_headers.role)))

        return response


from_headers = AdditionalDataFromHeader()
