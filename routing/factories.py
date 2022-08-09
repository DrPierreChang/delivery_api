import factory
from factory import fuzzy

from base.utils import get_fuzzy_location


class LocationFactory(factory.django.DjangoModelFactory):
    class Meta:
        django_get_or_create = ('location',)

    location = get_fuzzy_location()
    address = fuzzy.FuzzyText(suffix=' at Minsk')
