from __future__ import absolute_import

from django.conf.urls import url

from .views import AvailabilityTestView

urlpatterns = [
    url(r'^availability-test/?$', AvailabilityTestView.as_view(), name='availability-test'),
]
