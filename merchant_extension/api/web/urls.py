from django.urls import include, path

from base.utils import DefaultRouter
from merchant_extension.api.legacy.api import (
    ResultChecklistViewSet,
    SurveyMerchantViewSet,
    SurveyResultCSVView,
    SurveyResultViewSet,
)

router = DefaultRouter()
router.register('driver-checklist', ResultChecklistViewSet)
router.register('surveys', SurveyResultViewSet)
router.register('surveys-merchant', SurveyMerchantViewSet)


urlpatterns = [
    path('surveys-result-csv', SurveyResultCSVView.as_view(), {'api_version': 2}),
    path('', include(router.urls), {'api_version': 2}),
]
