from functools import wraps

from django.core.cache import cache

from drf_secure_token.models import Token

from custom_auth.saml2.utils import create_saml_login_request
from custom_auth.saml2.views import AUTH_TOKEN_CACHE_KEY_PREFIX, AUTH_TOKEN_HEADER


def saml_login(view):
    @wraps(view)
    def inner(*args, **kwargs):
        self = args[0]
        serializer = self.login_serializer_class(
            data=self.request.data, context=self.get_serializer_context(self.stage.PREFETCH), **kwargs
        )
        serializer.is_valid(raise_exception=True)

        user = serializer.prefetch_user()
        if not user or not user.current_merchant.enable_saml_auth:
            response = view(*args, **kwargs)
            return response

        serializer.is_valid_login(
            user, self.request.query_params.get('force', False),
            self.request.query_params.get('device_id', None)
        )

        response = create_saml_login_request(self.request)
        # pre-generate auth token
        token = Token.generate_key()
        cache.set(AUTH_TOKEN_CACHE_KEY_PREFIX.format(user.username), token)
        response[AUTH_TOKEN_HEADER] = token
        return response
    return inner
