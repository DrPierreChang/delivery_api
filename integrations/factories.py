import string

import factory

from base.factories import DriverFactory
from merchant.factories import MerchantFactory


class SalesSystemFactory(factory.django.DjangoModelFactory):
    merchant = factory.SubFactory(MerchantFactory)
    api_key = factory.fuzzy.FuzzyText()
    api_secret = factory.fuzzy.FuzzyText()
    subdomain = factory.fuzzy.FuzzyText(chars=string.ascii_letters + '-_0123456789')
    creator = factory.SubFactory(DriverFactory)


class RevelSystemFactory(SalesSystemFactory):
    class Meta:
        model = 'integrations.RevelSystem'
