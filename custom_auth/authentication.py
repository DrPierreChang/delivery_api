from django.conf import settings
from django.utils import translation

from rest_framework.authentication import BasicAuthentication

from drf_secure_token.authentication import SecureTokenAuthentication


class I18NAuthenticationMixin:
    def authenticate(self, request):
        if request.version != settings.MOBILE_API_VERSION:
            return super().authenticate(request)

        request_language = translation.get_language_from_request(request) or settings.MOBILE_API_LANGUAGE_CODE
        with translation.override(request_language):
            user_auth_tuple = super().authenticate(request)

        user = user_auth_tuple[0] if user_auth_tuple else None
        self.activate_translation(user, request)
        return user_auth_tuple

    def activate_translation(self, user, request):
        if user and user.is_authenticated:
            language = user.language
        else:
            language = translation.get_language_from_request(request) or settings.MOBILE_API_LANGUAGE_CODE
        translation.activate(language)
        request.LANGUAGE_CODE = translation.get_language()


class I18NSecureTokenAuthentication(I18NAuthenticationMixin, SecureTokenAuthentication):
    pass


class I18NBasicAuthentication(I18NAuthenticationMixin, BasicAuthentication):
    pass
