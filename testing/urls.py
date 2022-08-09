from django.conf.urls import url

from testing.analyze_drivers_locations.views import simulate_driver_path

urlpatterns = \
    [
        url(r'^simulate_driver_path/$', simulate_driver_path, name='simulate_driver_path'),
    ]
