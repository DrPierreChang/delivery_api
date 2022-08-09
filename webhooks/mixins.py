from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny

from merchant.permissions import IsNotBlocked

from .authentication import MerchantAPIKeyAuthentication
from .models import MerchantAPIKey, MerchantAPIKeyEvents


class MerchantAPIKeyMixin(object):
    authentication_classes = [MerchantAPIKeyAuthentication, ]
    permission_classes = [AllowAny, IsNotBlocked]
    
    def __init__(self, *args, **kwargs):
        super(MerchantAPIKeyMixin, self).__init__(*args, **kwargs)
        self.request_log = None
        self.merchant_api_key = None

    def perform_authentication(self, request):
        super(MerchantAPIKeyMixin, self).perform_authentication(request)
        self.merchant_api_key = self.request.auth

    def initial(self, *args, **kwargs):
        try:
            super(MerchantAPIKeyMixin, self).initial(*args, **kwargs)
        finally:
            self.request_log = MerchantAPIKeyEvents.get_request_log(self.request)

    def dispatch(self, request, *args, **kwargs):
        response = None
        try:
            response = super(MerchantAPIKeyMixin, self).dispatch(request, *args, **kwargs)
            return response
        finally:
            if getattr(self.request, 'auth') is not None:
                self.request.auth.used(self.request, self.request_log, response)
            else:
                MerchantAPIKey.anonymous_used(self.request, self.request_log, response)
