#! /usr/bin/python
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

import requests

from integrations.systems.interfaces import ItemIterator
from integrations.systems.revel.objects import Customer, Order


class ApiRequest(object):
    def __init__(self, model, host, auth, by_pack=False):
        self._url = model.url
        self._model = model
        self._payload = dict()
        self._auth = auth
        self._host = host
        self._by_pack = by_pack

    @property
    def url(self):
        url = self._host + self._url + '?' + urllib.parse.urlencode(self._payload, doseq=True)
        logging.info(url)
        return url

    def all(self):
        return self.__iter__()

    def filter(self, **kwargs):
        formatted_dict = dict()
        for key, value in kwargs.items():
            if isinstance(value, list):
                new_value = ','.join([str(x) for x in value])
                formatted_dict[key] = new_value
            else:
                formatted_dict[key] = value

        self._payload.update(formatted_dict)

        return self

    def expand(self, **kwargs):
        formatted_dict = dict()

        for key, values in kwargs.items():
            if values:
                formatted_dict[key] = 1
            else:
                formatted_dict[key] = 0

        self._payload['expand'] = json.dumps(formatted_dict)

        return self

    def __iter__(self):
        return ItemIterator(make_call, self._host, self.url, self._auth, self._model.build_from_dict, pack=self._by_pack)


class Api(object):
    def __init__(self, host, auth, get_by_pack=False):
        self._auth = auth
        self._host = host
        self._pack = get_by_pack

    @property
    def orders(self):
        return ApiRequest(Order, self._host, self._auth, self._pack)

    @property
    def customers(self):
        return ApiRequest(Customer, self._host, self._auth, self._pack)


def make_call(url, api_auth):
    headers = {
        'API-AUTHENTICATION': api_auth
    }

    logging.info(url)

    response = requests.get(url, headers=headers)

    response.raise_for_status()

    return response


if __name__ == '__main__':
    # This is a test credentials, in future we may remove it from here.
    api_key = '1a293e4973e64cbe9f63f1e1b311563d'
    api_secret = 'b4a2734774474ee9b330c50b8e17ad34b6eca71629f14011bbbb6cdf39f2ca36'

    host = 'https://testradaro.revelup.com'

    api_authentication = "%s:%s" % (api_key, api_secret)

    api = Api(host=host, auth=api_authentication, get_by_pack=True)

    logging.basicConfig(level=logging.INFO)

    for p in api.orders.filter(customer__isnull=False).expand(customer=True):
        print(p)
