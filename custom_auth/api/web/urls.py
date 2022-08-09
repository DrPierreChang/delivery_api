from django.urls import include, path

from base.utils import DefaultRouter, NestedSimpleRouter
from custom_auth.api.legacy.api import AvailableMerchantsViewSet, UserAuthViewSet, UserViewSet

router = DefaultRouter()
router.register(r'auth', UserAuthViewSet, 'auth')
router.register(r'users', UserViewSet)

merchants_router = NestedSimpleRouter(router, r'users', lookup='users')
merchants_router.register(r'available-merchants', AvailableMerchantsViewSet, basename='available-merchants')

urlpatterns = [
    path('', include(router.urls), {'api_version': 2}),
    path('', include(merchants_router.urls), {'api_version': 2}),
]
