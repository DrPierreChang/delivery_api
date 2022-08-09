import factory

from merchant.factories import MerchantFactory


class TagFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'documents.Tag'

    merchant = factory.SubFactory(MerchantFactory)
    name = factory.Sequence(lambda n: 'Tag#%03d' % n)
