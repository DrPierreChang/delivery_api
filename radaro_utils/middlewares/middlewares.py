from __future__ import absolute_import, unicode_literals

import cProfile
import pstats

from django.conf import settings
from django.utils import timezone, translation
from django.utils.cache import add_never_cache_headers, get_max_age

from rest_framework.response import Response

from .. import versioning

try:
    from django.utils.deprecation import MiddlewareMixin
except ImportError:
    MiddlewareMixin = object


class AdminPageRequestVersionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        is_admin_site = request.path.strip('/').startswith('admin')
        if not hasattr(request, 'version') and is_admin_site:
            request.version = versioning.APIVersion(settings.LATEST_API_VERSION)
            request.versioning_scheme = versioning.CustomURLPathVersioning()


class CProfileBaseMiddleware(MiddlewareMixin):
    name_template = None

    def __init__(self, *args, **kwargs):
        self.pr = cProfile.Profile()
        super(CProfileBaseMiddleware, self).__init__(*args, **kwargs)

    def process_request(self, request):
        self.pr.enable()

    def generate_name(self, request):
        now_date = str(timezone.now())
        path = ':'.join(request.path.split('/'))
        return self.name_template.format(now_date, path).replace(' ', '_')


class CProfileTextMiddleware(CProfileBaseMiddleware):
    name_template = 'profiling/profiling_{}_{}.prof.txt'

    def process_response(self, request, response):
        self.pr.disable()
        with open(self.generate_name(request), 'wt') as s:
            sortby = 'cumulative'
            ps = pstats.Stats(self.pr, stream=s).sort_stats(sortby)
            ps.print_stats()
        return response


class CProfileMiddleware(CProfileBaseMiddleware):
    name_template = 'profiling/profiling_{}_{}.prof'

    def process_response(self, request, response):
        self.pr.disable()
        sortby = 'cumulative'
        ps = pstats.Stats(self.pr).sort_stats(sortby)
        ps.dump_stats(self.generate_name(request))
        return response


class LanguageMiddleware(MiddlewareMixin):
    def process_request(self, request):
        language = settings.LANGUAGE_CODE
        translation.activate(language)
        request.LANGUAGE_CODE = translation.get_language()

    def process_response(self, request, response):
        if request.META.get('HTTP_X_RETURN_LANGUAGE'):
            language = translation.get_language()
            if 'Content-Language' not in response:
                response['Content-Language'] = language
        return response


class DisableClientCacheMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        if isinstance(response, Response) and get_max_age(response) is None:
            add_never_cache_headers(response)
        return response
