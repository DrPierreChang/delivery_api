from django.urls import include, path

from base.utils import DefaultRouter

from .route_optimisation.v1.views import ExternalRouteOptimisationViewSet
from .route_optimisation.v2.views import ExternalRouteOptimisationViewSetV2

router = DefaultRouter()
router.register('optimisation/v1', ExternalRouteOptimisationViewSet)
router.register('optimisation/v2', ExternalRouteOptimisationViewSetV2)

urlpatterns = [
    path('ro/', include(router.urls)),
]
