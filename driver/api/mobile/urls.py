from django.urls import include, path

from base.utils import BulkNestedRouter, DefaultRouter

from .drivers.v1.views import DriverViewSet
from .drivers.v2.views import V2DriverViewSet

router = DefaultRouter()
router.register('drivers/v1', DriverViewSet)
router.register('drivers/v2', V2DriverViewSet)

drivers_skill_sets_router = BulkNestedRouter(router, 'drivers/v1', lookup='driver')

urlpatterns = [
    path('', include(router.urls)),
]
