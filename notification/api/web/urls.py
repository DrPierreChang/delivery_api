from django.urls import include, path

from base.utils import BulkRouter
from notification.api.legacy import views

router = BulkRouter()
router.register('message-templates', views.MerchantMessageTemplatesViewSet)

urlpatterns = [
    path('', include(router.urls), {'api_version': 2}),
]
