from django.urls import include, path

from base.utils import DefaultRouter

from .driver_routes.v1.views import LegacyDriverRouteViewSetV1
from .views import DriverRouteViewSet, RouteOptimisationViewSet

router = DefaultRouter()
router.register('route-optimization', RouteOptimisationViewSet)
router.register('driver-routes', DriverRouteViewSet)
router.register('driver-routes/v1/', LegacyDriverRouteViewSetV1)

urlpatterns = [
    path('', include(router.urls)),
]
