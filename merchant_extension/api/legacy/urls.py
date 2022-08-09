from django.conf.urls import include, url

from base.utils import DefaultRouter

from .api import ResultChecklistViewSet, SurveyMerchantViewSet, SurveyResultCSVView, SurveyResultViewSet

router = DefaultRouter()
router.register(r'driver-checklist', ResultChecklistViewSet)
router.register(r'surveys', SurveyResultViewSet)
router.register(r'surveys-merchant', SurveyMerchantViewSet)


merchant_extension_api_patterns = [
    url(r'surveys-result-csv', SurveyResultCSVView.as_view()),
    url(r'', include(router.urls)),
]
