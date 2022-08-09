import logging

import googlemaps.convert
from googlemaps.client import _DEFAULT_BASE_URL, urlencode_params

from routing.google.utils import MapsAPIClientFactory, empty

logger = logging.getLogger('routing.google')


class RadaroGoogleMapsClient(googlemaps.Client):
    def __init__(self, key=None, client_id=empty, client_secret=empty, *args, **kwargs):
        super(RadaroGoogleMapsClient, self).__init__(
            key=key, client_id=client_id, client_secret=client_secret, *args, **kwargs
        )
        self.client_id = None if client_id is empty else client_id
        self.client_secret = None if client_secret is empty else client_secret

    def _request(self, url, params, first_request_time=None, retry_counter=0,
                 base_url=_DEFAULT_BASE_URL, accepts_clientid=True,
                 extract_body=None, requests_kwargs=None, post_json=None, retry_transport_error_counter=0):
        try:
            return super()._request(url, params, first_request_time,
                                    retry_counter, base_url, accepts_clientid,
                                    extract_body, requests_kwargs, post_json)
        except googlemaps.exceptions.TransportError:
            if retry_transport_error_counter > 3:
                raise
            # Retry request.
            return self._request(url, params, first_request_time,
                                 retry_counter + 1, base_url, accepts_clientid,
                                 extract_body, requests_kwargs, post_json,
                                 retry_transport_error_counter=retry_transport_error_counter + 1)

    def _generate_auth_url(self, path, params, accepts_clientid):
        # Deterministic ordering through sorting by key.
        # Useful for tests, and in the future, any caching.
        extra_params = getattr(self, "_extra_params", None) or {}
        if type(params) is dict:
            params = sorted(dict(extra_params, **params).items())
        else:
            params = sorted(extra_params.items()) + params[:]  # Take a copy.

        if self.channel:
            params.append(("channel", self.channel))

        if self.key:
            params.append(("key", self.key))
            result = path + "?" + urlencode_params(params)
            logger.debug('[Channel] RadaroGoogleMapsClient.generate_auth_url %s' % result)
            return result

        raise ValueError("Must provide API key for this API. It does not accept "
                         "enterprise credentials.")


class GoogleMapsClientFactory(MapsAPIClientFactory):
    @staticmethod
    def create(google_api_key, timeout, channel, proxies=None, *args, **kwargs):
        client_kwargs = {}
        if proxies:
            client_kwargs['requests_kwargs'] = {'proxies': proxies}
        return RadaroGoogleMapsClient(google_api_key, timeout=timeout, channel=channel, **client_kwargs)
