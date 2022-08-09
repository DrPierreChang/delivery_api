"""django_19_test URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.9/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Add an import:  from blog import urls as blog_urls
    2. Import the include() function: from django.conf.urls import url, include
    3. Add a URL to urlpatterns:  url(r'^blog/', include(blog_urls))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from djangosaml2.views import MetadataView

from base.api.urls import base_api_patterns
from custom_auth.api.urls import api_patterns as custom_auth_api
from custom_auth.saml2.views import RadaroACSView
from driver.api.urls import driver_api_patterns
from integrations.urls import sales_systems_api_patterns
from merchant.api.urls import merchant_api_patterns
from merchant_extension.api.urls import merchant_extension_api_patterns
from notification.api.urls import notifications_api_patterns
from reporting.api.urls import reporting_api_patterns
from route_optimisation.api.legacy.urls import urlpatterns as route_optimisation_api_patterns
from tasks.api.urls import tasks_api_patterns
from webhooks.urls import webhooks_api_patterns

saml2_api = [
    path('metadata/', MetadataView.as_view()),
    path('acs/', RadaroACSView.as_view()),
    path('success/', TemplateView.as_view(template_name='custom_auth/saml2/login_success.html'))
]

mobile_api = ([
    path('', include('tasks.api.mobile.urls')),
    path('', include('driver.api.mobile.urls')),
    path('', include('merchant.api.mobile.urls')),
    path('', include('merchant_extension.api.mobile.urls')),
    path('', include('base.api.mobile.urls')),
    path('', include('custom_auth.api.mobile.urls')),
    path('', include('documents.api.mobile.urls')),
    path('', include('notification.api.mobile.urls')),
    path('', include('route_optimisation.api.mobile.urls')),
    path('', include('schedule.api.mobile.urls')),
], 'mobile')

web_api = [
    path('', include('custom_auth.api.web.urls')),
    path('', include('base.api.web.urls')),
    path('', include('merchant.api.web.urls')),
    path('', include('driver.api.web.urls')),
    path('', include('tasks.api.web.urls')),
    path('', include('reporting.api.web.urls')),
    path('', include('notification.api.web.urls')),
    path('', include('merchant_extension.api.web.urls')),
    path('', include('route_optimisation.api.web.urls')),
    path('', include('webhooks.urls')),
    path('', include('schedule.api.web.urls')),
]

external_api = [
    path('', include('webhooks.api.urls')),
]

api_patterns = [] + \
               custom_auth_api + \
               base_api_patterns + \
               merchant_api_patterns + \
               driver_api_patterns + \
               tasks_api_patterns + \
               reporting_api_patterns + \
               webhooks_api_patterns + \
               notifications_api_patterns + \
               sales_systems_api_patterns + \
               merchant_extension_api_patterns + \
               route_optimisation_api_patterns

admin_patterns = [
    path('grappelli/', include('grappelli.urls')),
    path('markdown/', include('django_markdown.urls')),
    path('logs/', include('logtailer.urls')),
    path('nested_admin/', include('nested_admin.urls')),
    path('', include('tasks.admin.urls')),
    path('', include('route_optimisation.admin.urls')),
]

admin.autodiscover()

urlpatterns = [
    path('api/', include(api_patterns)),
    re_path(r'^api/(?P<api_version>(v[0-9]+|latest))/', include(api_patterns)),
    path('api/mobile/', include(mobile_api)),
    path('api/web/', include(web_api)),
    path('api/webhooks/', include(external_api)),
    path('auth/', include('custom_auth.api.urls')),
    path('invite/', include('base.api.urls')),
    path('admin/', admin.site.urls),
    path('admin/', include(admin_patterns)),
    path('', include('availability_monitor.urls')),
    path('saml2/', include(saml2_api))
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns += [
        path('__debug__/', include(debug_toolbar.urls)),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += [
        path('testing/', include('testing.urls')),
    ]

# if settings.UPTIME_BOT_ACTIVE:
urlpatterns.append(path('uptime-bot/', include('uptime_bot.urls')))

handler400 = 'base.utils.exceptions.views.custom_bad_request'
handler500 = 'base.utils.exceptions.views.custom_server_error'
