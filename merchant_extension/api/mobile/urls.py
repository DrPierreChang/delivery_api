from django.urls import include, path

from base.utils import DefaultRouter

from .checklists.v1.views import DriverChecklistViewSet
from .checklists.v2.views import V2DriverChecklistViewSet

router = DefaultRouter()
router.register('checklists/v1', DriverChecklistViewSet)
router.register('checklists/v2', V2DriverChecklistViewSet)

urlpatterns = [
    path('', include(router.urls))
]
