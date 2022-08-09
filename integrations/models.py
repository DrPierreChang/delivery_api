from __future__ import unicode_literals

from django.core import validators
from django.db import models

from integrations.systems.revel.connection import Api
from tasks.models.external import ExternalSource


class SalesSystem(ExternalSource, models.Model):
    _revel_domain = 'https://%s.revelup.com'

    subdomain = models.CharField(max_length=100, validators=[validators.RegexValidator(r"[\w-]+")])

    api_key = models.CharField(max_length=50)
    api_secret = models.CharField(max_length=100)

    importing = models.BooleanField(default=False)

    class Meta:
        abstract = True

    def _get_orders(self):
        raise NotImplementedError

    def _get_pack_orders(self):
        raise NotImplementedError

    @property
    def orders(self):
        return self._get_orders()

    @property
    def orders_pack(self):
        return self._get_pack_orders()

    @property
    def host(self):
        return self._revel_domain % self.subdomain

    @property
    def auth(self):
        return "%s:%s" % (self.api_key, self.api_secret)

    @property
    def api(self):
        if not hasattr(self, '_api'):
            self._api = Api(self.host, self.auth)
        return self._api

    @property
    def pack_api(self):
        if not hasattr(self, '_api_pack'):
            self._api_pack = Api(self.host, self.auth, True)
        return self._api_pack


class RevelSystem(SalesSystem):
    def _get_orders(self):
        return self.api.orders

    def _get_customers(self):
        return self.api.customers

    def _get_pack_orders(self):
        return self.pack_api.orders

    def _get_pack_customers(self):
        return self.pack_api.customers
