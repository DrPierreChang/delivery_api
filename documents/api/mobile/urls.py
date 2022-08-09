from django.urls import include, path

from rest_framework.routers import DefaultRouter

from .tags.v1.views import TagViewSet

router = DefaultRouter()
router.register('tags/v1', TagViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
