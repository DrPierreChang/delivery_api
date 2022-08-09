from django.conf.urls import url

from .views import ROClusteringView, RORoutesView

urlpatterns = [
    url(r'^route_optimisation/(?P<ro_id>[0-9]+)/routes/?$', RORoutesView.as_view(), name='ro_routes_admin'),
    url(r'^route_optimisation/(?P<ro_id>[0-9]+)/clustering/?$', ROClusteringView.as_view(), name='ro_clustering_admin'),
]
