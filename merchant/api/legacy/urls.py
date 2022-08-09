from django.conf.urls import include, url

from base.utils import BulkNestedRouter, DefaultRouter, NestedSimpleRouter

from .api import (
    AllowedCountriesList,
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

router = DefaultRouter()
router.register(r'merchant', MerchantViewSet)
router.register(r'merchant-customers',  MerchantCustomerViewSet)
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

merchant_api_patterns = [
    url(r'', include(router.urls)),
    url(r'', include(card_router.urls)),
    url(r'', include(label_router.urls)),
    url(r'', include(skill_sets_router.urls)),
    url(r'', include(skill_sets_drivers_router.urls)),
    url(r'^allowed-countries/?$', AllowedCountriesList.as_view(), name='allowed-countries'),
    url(r'^search/$', SearchAPI.as_view(), ),
]
