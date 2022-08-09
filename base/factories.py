import factory

from base.models.members import Member
from merchant.factories import MerchantFactory, SubBrandingFactory
from routing.factories import LocationFactory


class DriverLocationFactory(LocationFactory):
    class Meta:
        model = 'driver.DriverLocation'
        django_get_or_create = ('location',)


class CarFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'base.Car'


class SampleFileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'base.SampleFile'


class MemberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'base.Member'

    merchant = factory.SubFactory(MerchantFactory)
    email = factory.Sequence(lambda n: 'member%d@gm.co' % n)
    phone = factory.Sequence(lambda n: '+61499902%03d' % n)


class DriverFactory(MemberFactory):
    # last_location = DriverLocationFactory()
    role = Member.DRIVER


class ManagerFactory(MemberFactory):
    role = Member.MANAGER


class SubManagerFactory(MemberFactory):
    role = Member.SUB_MANAGER
    sub_branding = factory.SubFactory(SubBrandingFactory)


class AdminFactory(MemberFactory):
    role = Member.ADMIN


class ObserverFactory(MemberFactory):
    role = Member.OBSERVER


class InviteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'base.Invite'

    initiator = factory.SubFactory(MemberFactory)
    phone = factory.Sequence(lambda n: '+61499901%03d' % n)
    email = factory.Sequence(lambda n: 'invited%03d@gm.co' % n)
