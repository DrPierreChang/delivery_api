from django.conf.urls import url

from .views import GeofencesComparisonView, RoutesComparisonView

urlpatterns = [
    url(r'^order/(?P<order_id>[0-9]+)/routes/?$', RoutesComparisonView.as_view(), name='routes_comparison'),
    url(r'^order/(?P<order_id>[0-9]+)/geofences/?$', GeofencesComparisonView.as_view(), name='geofences_comparison'),
]
