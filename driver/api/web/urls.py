from django.urls import include, path

from base.utils import BulkNestedRouter, DefaultRouter, NestedSimpleRouter
from driver.api.legacy.views import DriverHubViewSet, DriverLocationViewSet, DriverSkillSetsViewSet, DriverViewSet

from .drivers.views import WebDriverViewSet

router = DefaultRouter()
router.register(r'drivers', DriverViewSet)

drivers_router = NestedSimpleRouter(router, r'drivers', lookup='driver')
drivers_router.register(r'locations', DriverLocationViewSet)
drivers_router.register(r'hubs', DriverHubViewSet, basename='driver-hubs')

drivers_skill_sets_router = BulkNestedRouter(router, r'drivers', lookup='driver')
drivers_skill_sets_router.register(r'skill-sets', DriverSkillSetsViewSet, basename='skill-sets')

web_router = DefaultRouter()
web_router.register(r'drivers', WebDriverViewSet)

urlpatterns = [
    path('', include(router.urls), {'api_version': 2}),
    path('', include(drivers_router.urls), {'api_version': 2}),
    path('', include(drivers_skill_sets_router.urls), {'api_version': 2}),

    path('dev/', include(web_router.urls)),
]
