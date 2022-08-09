from functools import wraps

from django.core.cache import cache
from django.shortcuts import render
from django.utils.decorators import method_decorator

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.settings import api_settings

from djangosaml2.views import AssertionConsumerServiceView
from drf_secure_token.models import Token

from custom_auth.saml2.utils import create_saml_login_request

AUTH_TOKEN_CACHE_KEY_PREFIX = 'auth_token_{}'
AUTH_TOKEN_HEADER = 'X-Token'


def saml_login(roles: tuple):
    def decorator(view):
        @wraps(view)
        def inner(*args, **kwargs):
            self = args[0]
            serializer = self.get_login_serializer()
            serializer.is_valid(raise_exception=True)
            user = serializer.prefetch_user()
            if not user or not user.current_merchant.enable_saml_auth:
                response = view(*args, roles=roles, **kwargs)
                return response

            if not any([getattr(user, role) for role in roles]):
                raise ValidationError({
                        api_settings.NON_FIELD_ERRORS_KEY: ['Invalid username or password.'],
                    })

            if 'is_driver' in roles and user.user_auth_tokens.filter(marked_for_delete=False).exists()\
                    and user.device_set.filter(in_use=True).exists():
                if not self.request.query_params.get('force', False):
                    raise ValidationError({
                        api_settings.NON_FIELD_ERRORS_KEY: ['You\'re currently online on another device.'],
                    })
                device_id = self.request.query_params.get('device_id', None)
                user.on_force_login(device_id)

            response = create_saml_login_request(self.request)

            # pre-generate auth token
            token = Token.generate_key()
            cache.set(AUTH_TOKEN_CACHE_KEY_PREFIX.format(user.username), token)
            response[AUTH_TOKEN_HEADER] = token

            return response
        return inner
    return decorator


def access_token(view):
    def wrapped_view(*args, **kwargs):
        request = args[0]
        response = view(*args, **kwargs)
        if request.user.is_authenticated:
            token = cache.get(AUTH_TOKEN_CACHE_KEY_PREFIX.format(request.user.username))
            # token expired or user provided different credentials set for a third-party auth
            if not token:
                response = render(request, template_name='custom_auth/saml2/login_fail.html',
                                  status=status.HTTP_400_BAD_REQUEST)
            else:
                request.user.user_auth_tokens.create(key=token)
        cache.delete(AUTH_TOKEN_CACHE_KEY_PREFIX.format(request.user.username))
        return response
    return wraps(view)(wrapped_view)


@method_decorator(access_token, name='dispatch')
class RadaroACSView(AssertionConsumerServiceView):
    pass
