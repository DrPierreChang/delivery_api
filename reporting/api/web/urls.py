from django.urls import include, path

from base.utils import DefaultRouter
from reporting.api.legacy.views import EventViewSet, ExportReportViewSet, ReportViewSet
from reporting.api.web.views import WebEventViewSet

router = DefaultRouter()
router.register(r'reports', ReportViewSet)
router.register(r'export-reports', ExportReportViewSet, basename='export-report')

urlpatterns = [
    path('', include(router.urls), {'api_version': 2}),
    path('new-events/', EventViewSet.as_view({'get': 'get'}), {'api_version': 2}),
    path('dev/new-events/', WebEventViewSet.as_view({'get': 'get'})),
]
