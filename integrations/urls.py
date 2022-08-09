from django.conf.urls import include, url

from base.utils import DefaultRouter

from .api import RevelSystemIntegration

router = DefaultRouter()
router.register(r'revel', RevelSystemIntegration)


sales_systems_api_patterns = [
    url(r'^integrations/', include(router.urls)),
]
