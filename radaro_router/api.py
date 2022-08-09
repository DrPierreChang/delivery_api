from django.conf import settings

import requests

from radaro_router.exceptions import RadaroRouterClientException


class RadaroRouterApi(object):

    def __init__(self, token):
        self._token = token
        self.host = settings.RADARO_ROUTER_URL

    @staticmethod
    def _parse_response(response):
        if not response.ok:
            raise RadaroRouterClientException(response.status_code, response.json())
        return response.json() if response.content else None

    def make_call(self, http_method, method_name, query_params={}, **kwargs):
        params = {'key': self._token}
        params.update(query_params)
        kwargs.update({'params': params})
        url = '{}/{}'.format(self.host, method_name)
        response = requests.request(http_method, url, **kwargs)
        return self._parse_response(response)
