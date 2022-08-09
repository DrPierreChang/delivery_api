from django.conf.urls import include, url

from base.utils import DefaultRouter

from .api import CarViewSet, InviteViewSet, ListCars, ManagerViewSet, MobileAppVersionView, SampleFileViewSet, TimeView
from .views import InviteView, invite_done

router = DefaultRouter()
router.register(r'managers', ManagerViewSet)
router.register(r'invitations', InviteViewSet)
router.register(r'samples', SampleFileViewSet)

base_api_patterns = \
    [
        url(r'', include(router.urls)),
        url(r'^cars/?$', ListCars.as_view(), name='list-cars'),
        url(r'^users/me/car/?$', CarViewSet.as_view(CarViewSet.URL_MAPPING), name='member-car'),
        url(r'^time/(?P<time>[0-9.0-9]*[Ee]?[0-9]*)/?$', TimeView.as_view(), name='time-view'),
        url(r'^mobile-app-version/(?P<app_type>\w+)/?$', MobileAppVersionView.as_view(),
            name='mobile-app-version-view'),
    ]

urlpatterns = \
    [
        url(r'^(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z\-]+)/?$',
            InviteView.as_view(), name='invite_confirm'),
        url(r'^done/?$', invite_done, {'template_name': 'invitations/invite_done.html'},
            name='invite_done')
    ]
