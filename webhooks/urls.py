from django.conf.urls import include, url

from base.utils import DefaultRouter
from webhooks import api

router = DefaultRouter()
router.register(r'webhooks/jobs', api.WebhooksViewSet)
router.register(r'webhooks/drivers', api.ExternalDriversViewSet)
router.register(r'webhooks/sub-brands', api.ExternalSubBrandingViewSet)
router.register(r'webhooks/labels', api.ExternalLabelViewSet)
router.register(r'webhooks/skill-sets', api.ExternalSkillSetViewSet)
router.register(r'webhooks/route-optimizations', api.ExternalRouteOptimizationViewSet)
router.register(r'webhooks/hubs', api.ExternalHubViewSet)
router.register(r'webhooks/completion-codes', api.ExternalCompletionCodeViewSet)
router.register(r'api-key', api.APIKeyViewSet)
router.register(r'csv-upload', api.ExternalCSVUploadViewSet)

webhooks_api_patterns = [
    url(r'', include(router.urls)),
    url(r'webhooks/checklists', api.ExternalChecklistAPIView.as_view())
]

web_router = DefaultRouter()
web_router.register(r'api-key', api.APIKeyViewSet)
web_router.register(r'csv-upload', api.ExternalCSVUploadViewSet)

urlpatterns = [
    url(r'', include(router.urls)),
]
