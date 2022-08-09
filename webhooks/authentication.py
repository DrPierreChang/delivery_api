from rest_framework import authentication, exceptions

from webhooks.models import MerchantAPIKey
from webhooks.utils import validate_uuid4


class MerchantAPIKeyAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        try:
            key = validate_uuid4(request.GET.get('key', request.META.get('HTTP_X_API_KEY', None)))
            if not key:
                raise KeyError('Key parameter is not valid.')
            merchant_api_key = MerchantAPIKey.objects.get(key=key, available=True)
            user = merchant_api_key.creator
        except Exception:
            raise exceptions.AuthenticationFailed('Merchant API key is not provided, wrong or unavailable.')
        return user, merchant_api_key

    def authenticate_header(self, request):
        return 'Api-Key'
