from django.urls import include, path, register_converter

from rest_framework.routers import DefaultRouter

from ...utils import MobileAppVersionsConstants
from .app_version.v1.views import MobileAppVersionView
from .invitations.v1.views import InviteViewSet
from .invitations.v2.views import V2InviteViewSet


class AppTypeConverter:
    regex = '({})'.format('|'.join(MobileAppVersionsConstants.APP_TYPES))  # '(ta_ios|android|ios|ta_android)'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(AppTypeConverter, 'app_type')

router = DefaultRouter()
router.register('invitations/v1', InviteViewSet)
router.register('invitations/v2', V2InviteViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('app_version/v1/<app_type:app_type>/', MobileAppVersionView.as_view()),
]
