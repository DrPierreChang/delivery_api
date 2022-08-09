from __future__ import absolute_import

from django.conf.urls import include, url
from django.contrib.auth import views as auth_views

from base.utils import DefaultRouter, NestedSimpleRouter
from custom_auth.models import ApplicationUser

from .api import AvailableMerchantsViewSet, UserAuthViewSet, UserViewSet
from .views import account_confirm

urlpatterns = \
    [
        url(r'^reset-password/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/?$',
            auth_views.PasswordResetConfirmView.as_view(), {'template_name': 'custom_auth/password_reset_form.html',
                                                'token_generator': ApplicationUser.reset_password_token_generator},
            name='password_reset_confirm'),
        url(r'^reset-password/done/?$', auth_views.PasswordResetCompleteView.as_view,
            {'template_name': 'custom_auth/password_reset.html'},
            name='password_reset_complete'),
        url(r'^confirm/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/?$',
            account_confirm, {'token_generator': ApplicationUser.confirm_account_token_generator},
            name='account_confirm'),

    ]


router = DefaultRouter()
router.register(r'auth', UserAuthViewSet, 'auth')
router.register(r'users', UserViewSet)

merchants_router = NestedSimpleRouter(router, r'users', lookup='users')
merchants_router.register(r'available-merchants', AvailableMerchantsViewSet, basename='available-merchants')

api_patterns = \
    [
        url(r'', include(router.urls)),
        url(r'', include(merchants_router.urls)),
    ]
