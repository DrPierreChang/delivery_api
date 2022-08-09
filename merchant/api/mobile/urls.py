from django.urls import include, path

from rest_framework.routers import DefaultRouter

from .hubs.v1.views import MerchantHubViewSet
from .labels.v1.views import MerchantLabelsViewSet
from .merchant.v1.views import MerchantView
from .skill_sets.v1.views import MerchantSkillSetViewSet
from .sub_branding.v1.views import MerchantSubBrandingViewSet

router = DefaultRouter()
router.register('labels/v1', MerchantLabelsViewSet)
router.register('skill_sets/v1', MerchantSkillSetViewSet)
router.register('sub_branding/v1', MerchantSubBrandingViewSet)
router.register('hubs/v1', MerchantHubViewSet)

urlpatterns = [
    path('merchant/v1/', MerchantView.as_view()),
    path('', include(router.urls)),
]
