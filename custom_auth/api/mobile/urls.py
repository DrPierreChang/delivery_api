from django.urls import include, path

from base.utils import DefaultRouter

from .auth.v1.views import UserAuthViewSet
from .auth.v2.views import V2UserAuthViewSet

router = DefaultRouter()
router.register(r'auth/v1', UserAuthViewSet, 'auth/v1')
router.register(r'auth/v2', V2UserAuthViewSet, 'auth/v2')

urlpatterns = [
    path('', include(router.urls)),
]
