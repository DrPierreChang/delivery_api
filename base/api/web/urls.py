from django.urls import include, path

from base.api.legacy.api import InviteViewSet, SampleFileViewSet
from base.utils import DefaultRouter

from .driver.views import DriverViewSet, GroupDriverViewSet

router = DefaultRouter()
router.register(r'invitations', InviteViewSet)
router.register(r'samples', SampleFileViewSet)

subbrand_router = DefaultRouter()
subbrand_router.register('drivers', DriverViewSet)

group_router = DefaultRouter()
group_router.register('drivers', GroupDriverViewSet)

urlpatterns = [
    path('', include(router.urls), {'api_version': 2}),
    path('subbrand/', include(subbrand_router.urls)),
    path('group/', include(group_router.urls)),
]
