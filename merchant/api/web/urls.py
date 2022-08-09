from django.urls import include, path

from base.utils import BulkNestedRouter, DefaultRouter, NestedSimpleRouter
from merchant.api.legacy.api import (
    CardViewSet,
    HubViewSet,
    MerchantCustomerViewSet,
    MerchantLabelsViewSet,
    MerchantSkillSetDriversViewSet,
    MerchantSkillSetsViewSet,
    MerchantSubBrandingViewSet,
    MerchantViewSet,
    SearchAPI,
)

from .labels.views import GroupLabelsViewSet, LabelsViewSet
from .search.views import WebSearchViewSet

router = DefaultRouter()
router.register(r'merchant', MerchantViewSet)
router.register(r'merchant-customers', MerchantCustomerViewSet)
router.register(r'sub-branding', MerchantSubBrandingViewSet)
router.register(r'hubs', HubViewSet)

card_router = NestedSimpleRouter(router, r'merchant', lookup='merchant')
card_router.register(r'cards', CardViewSet, basename='cards')

label_router = NestedSimpleRouter(router, r'merchant', lookup='merchant')
label_router.register(r'labels', MerchantLabelsViewSet, basename='labels')

skill_sets_router = NestedSimpleRouter(router, r'merchant', lookup='merchant')
skill_sets_router.register(r'skill-sets', MerchantSkillSetsViewSet, basename='skill-sets')

skill_sets_drivers_router = BulkNestedRouter(skill_sets_router, r'skill-sets', lookup='skill_set')
skill_sets_drivers_router.register(r'drivers', MerchantSkillSetDriversViewSet, basename='drivers')

web_router = DefaultRouter()
web_router.register('subbrand/labels', LabelsViewSet)
web_router.register('group/labels', GroupLabelsViewSet)
web_router.register('dev/search', WebSearchViewSet)

urlpatterns = [
    path('', include(router.urls), {'api_version': 2}),
    path('', include(card_router.urls), {'api_version': 2}),
    path('', include(label_router.urls), {'api_version': 2}),
    path('', include(skill_sets_router.urls), {'api_version': 2}),
    path('', include(skill_sets_drivers_router.urls), {'api_version': 2}),
    path('search/', SearchAPI.as_view(), {'api_version': 2}),
    path('', include(web_router.urls)),
]
