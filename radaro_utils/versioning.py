from django.conf import settings

from rest_framework import versioning
from rest_framework.exceptions import APIException
from rest_framework.settings import api_settings


class CustomURLPathVersioning(versioning.URLPathVersioning):
    default_version = api_settings.DEFAULT_VERSION

    def determine_version(self, request, *args, **kwargs):
        # replicates the functionality of NamespaceVersioning.
        if hasattr(request, 'resolver_match') and request.resolver_match.namespace == 'mobile':
            version = settings.MOBILE_API_VERSION
        else:
            version = super(CustomURLPathVersioning, self).determine_version(request, *args, **kwargs)
            if version == 'latest':
                version = settings.LATEST_API_VERSION
            if isinstance(version, str):
                version = int(version[1:])
            if version > settings.LATEST_API_VERSION:
                raise APIException('Latest API version is %d' % settings.LATEST_API_VERSION)

        version = APIVersion(version)

        # `request` is object of DRF's Request, it'll have version and versioning_scheme attributes.
        # But request._request is object of standard Django's Request. And it won't have version attribute.
        # So we allow to get version from it, cause in some cases we have only standard Django Request object.
        request._request.version, request._request.versioning_scheme = version, self
        return version


class APIVersion(int):
    def __new__(cls, version=settings.LATEST_API_VERSION):
        if version == 'mobile':
            version = settings.MOBILE_API_VERSION
        return super().__new__(cls, version)

    def __str__(self):
        if self == settings.MOBILE_API_VERSION:
            return 'mobile'
        return 'v%d' % self
