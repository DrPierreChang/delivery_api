import uuid

import factory

from base.factories import ManagerFactory
from merchant.factories import MerchantFactory


class MerchantAPIKeyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'webhooks.MerchantAPIKey'

    key = factory.LazyAttribute(lambda _: uuid.uuid4())
    merchant = factory.SubFactory(MerchantFactory)
    creator = factory.SubFactory(ManagerFactory)
