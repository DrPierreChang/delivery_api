import random

import factory
from factory.fuzzy import FuzzyText

from base.utils import get_fuzzy_location
from merchant.models import Label, SkillSet
from routing.factories import LocationFactory


class MerchantFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'merchant.Merchant'

    location = get_fuzzy_location()
    sms_sender = FuzzyText(prefix='sms_', length=4)
    name = FuzzyText(prefix='Merchant_', length=4)


class MerchantGroupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'merchant.MerchantGroup'

    core_merchant = factory.SubFactory(MerchantFactory)


class SubBrandingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'merchant.SubBranding'

    merchant = factory.SubFactory(MerchantFactory)


class HubLocationFactory(LocationFactory):
    class Meta:
        model = 'merchant.HubLocation'
        django_get_or_create = ('location', )


class HubFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'merchant.Hub'

    location = factory.SubFactory(HubLocationFactory)
    phone = factory.Sequence(lambda n: '+61499903%03d' % n)
    name = factory.Sequence(lambda n: 'Hub#%03d' % n)
    merchant = factory.SubFactory(MerchantFactory)


def get_random_color(colors_list):
    lt_choices = [x[0] for x in colors_list]
    return random.choice(lt_choices)


class LabelFactory(factory.django.DjangoModelFactory):
    merchant = factory.SubFactory(MerchantFactory)
    name = factory.Sequence(lambda n: 'Label#%03d' % n)
    color = factory.LazyFunction(lambda: get_random_color(Label.color_choices))

    class Meta:
        model = 'merchant.Label'


class SkillSetFactory(factory.django.DjangoModelFactory):
    merchant = factory.SubFactory(MerchantFactory)
    name = factory.Sequence(lambda n: 'SkillSet#%03d' % n)
    color = factory.LazyFunction(lambda: get_random_color(SkillSet.color_choices))

    class Meta:
        model = 'merchant.SkillSet'
