from django.conf.urls import include, url

from base.utils import DefaultRouter

from .views import EventViewSet, ExportReportViewSet, ReportViewSet

router = DefaultRouter()
router.register(r'reports', ReportViewSet)
router.register(r'export-reports', ExportReportViewSet, basename='export-report')

reporting_api_patterns = \
    [
        url(r'', include(router.urls)),
        url(r'^new-events/?$', EventViewSet.as_view({'get': 'get'})),
    ]
