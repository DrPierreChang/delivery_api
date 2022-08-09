from django.conf.urls import include, url

from base.utils import BulkNestedRouter, DefaultRouter, NestedSimpleRouter

from .views import DriverHubViewSet, DriverLocationViewSet, DriverSkillSetsViewSet, DriverViewSet

router = DefaultRouter()
router.register(r'drivers', DriverViewSet)

drivers_router = NestedSimpleRouter(router, r'drivers', lookup='driver')
drivers_router.register(r'locations', DriverLocationViewSet)
drivers_router.register(r'hubs', DriverHubViewSet, basename='driver-hubs')


drivers_skill_sets_router = BulkNestedRouter(router, r'drivers', lookup='driver')
drivers_skill_sets_router.register(r'skill-sets', DriverSkillSetsViewSet, basename='skill-sets')

driver_api_patterns = \
    [
        url(r'', include(router.urls)),
        url(r'', include(drivers_router.urls)),
        url(r'', include(drivers_skill_sets_router.urls)),
    ]
