from django.conf.urls import include, url

from base.utils import BulkRouter

from . import views

router = BulkRouter()
router.register(r'message-templates', views.MerchantMessageTemplatesViewSet)

notifications_api_patterns = [
    url(r'', include(router.urls)),
    url(r'^register-device/gcm/$', views.RegisterGCMDevice.as_view()),
    url(r'^register-device/fcm/$', views.RegisterFCMDevice.as_view()),
    url(r'^register-device/apns/$', views.RegisterAPNSDevice.as_view()),
    url(r'^unregister-device/(?P<device_type>\w+)/$', views.UnregisterDevice.as_view()),
]
