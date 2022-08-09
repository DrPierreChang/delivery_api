from django.conf import settings
from django.urls import include, path

from base.utils import DefaultRouter, NestedSimpleRouter
from route_optimisation.api.web.temp_legacy.views import OptimisationTaskViewSet as OptimisationTaskViewSetLegacy
from route_optimisation.api.web.temp_legacy.views import RouteOptimisationViewSet as RouteOptimisationViewSetLegacy
from route_optimisation.api.web.views import (
    AvailableForAddOrderViewSet,
    ClusteringView,
    DriverRouteLocationViewSet,
    IntelligentClusteringView,
    OptimisationExampleView,
    OptimisationTaskViewSet,
    RouteOptimisationViewSet,
    RoutePolylinesViewSet,
)

legacy_router = DefaultRouter()
legacy_router.register('optimisation', RouteOptimisationViewSetLegacy)
legacy_router.register('optimisation-task', OptimisationTaskViewSetLegacy)

router = DefaultRouter()
router.register('optimisation', RouteOptimisationViewSet)
router.register('optimisation-task', OptimisationTaskViewSet)
router.register('locations', DriverRouteLocationViewSet)
router.register('route_polylines', RoutePolylinesViewSet)

optimisation_router = NestedSimpleRouter(router, 'optimisation', lookup='optimisation')
optimisation_router.register('available_for_add', AvailableForAddOrderViewSet, basename='available_for_add')

urlpatterns = [
    path('ro/', include(router.urls)),
    path('ro/', include(optimisation_router.urls)),
    path('dev/ro/', include(legacy_router.urls)),
]

if settings.DEBUG:
    urlpatterns += [
        path('ro/intelligent-clustering', IntelligentClusteringView.as_view(), name='intelligent-clustering'),
        path('ro/simple-clustering', ClusteringView.as_view(), name='simple-clustering'),
        path('ro/optimisation-example', OptimisationExampleView.as_view(), name='optimisation-example'),
    ]
