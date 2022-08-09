from django.urls import include, path

from base.utils import DefaultRouter
from route_optimisation.api.mobile.routes import DriverRouteViewSetV1
from route_optimisation.api.mobile.v1.views import OptimisationTaskViewSet, RouteOptimisationViewSet

router = DefaultRouter()
router.register('optimisation/v1', RouteOptimisationViewSet)
router.register('optimisation-task/v1', OptimisationTaskViewSet)

router.register('routes/v1', DriverRouteViewSetV1)

urlpatterns = [
    path('ro/', include(router.urls)),
]
