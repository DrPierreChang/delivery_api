import logging

from geopy import GoogleV3, Nominatim
from geopy.compat import urlencode

from routing.google.utils import MapsAPIClientFactory, empty

logger = logging.getLogger('routing.google')


class RadaroGoogleV3(GoogleV3):
    def __init__(self, api_key=None, client_id=empty, secret_key=empty, *args, **kwargs):
        super(RadaroGoogleV3, self).__init__(
            api_key=api_key, client_id=client_id, secret_key=secret_key, *args, **kwargs
        )
        self.client_id = None if client_id is empty else client_id
        self.secret_key = None if secret_key is empty else secret_key

    def _get_signed_url(self, params):
        """
        Returns a Premier account signed url only with channel key
        """
        if self.channel:
            params['channel'] = self.channel

        path = "?".join((self.api_path, urlencode(params)))
        result = '%s://%s%s' % (self.scheme, self.domain, path)
        logger.debug('[Channel] RadaroGoogleV3._get_signed_url %s' % result)
        return result


class NominatimClientFactory(MapsAPIClientFactory):
    @staticmethod
    def create(google_api_key, timeout, channel, proxies=None, *args, **kwargs):
        client_kwargs = {}
        if proxies:
            client_kwargs['proxies'] = proxies
        return Nominatim(user_agent='Radaro', **client_kwargs)


class GoogleV3ClientFactory(MapsAPIClientFactory):
    @staticmethod
    def create(google_api_key, timeout, channel, proxies=None, *args, **kwargs):
        client_kwargs = {}
        if proxies:
            client_kwargs['proxies'] = proxies
        return RadaroGoogleV3(api_key=google_api_key, timeout=timeout, channel=channel, **client_kwargs)
