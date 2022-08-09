from django.urls import path

from notification.api.mobile.devices.v1.views import RegisterDeviceView

urlpatterns = [
    path('register-device/', RegisterDeviceView.as_view())
]
