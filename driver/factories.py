import factory

from base.factories import DriverFactory
from routing.factories import LocationFactory


class DriverLocationFactory(LocationFactory):
    class Meta:
        model = 'driver.DriverLocation'
        django_get_or_create = ('location',)

    member = factory.SubFactory(DriverFactory)
