from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

import factory
from factory import fuzzy

from base.factories import DriverFactory, ManagerFactory, MerchantFactory
from merchant.factories import SubBrandingFactory
from routing.factories import LocationFactory


class OrderLocationFactory(LocationFactory):
    class Meta:
        model = 'tasks.OrderLocation'
        django_get_or_create = ('location',)


class CustomerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'tasks.Customer'

    email = fuzzy.FuzzyText(suffix='@gm.com')
    merchant = factory.SubFactory(MerchantFactory)
    last_address = factory.SubFactory(OrderLocationFactory)
    name = fuzzy.FuzzyText()
    phone = ''


class PickupFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'tasks.Pickup'

    email = fuzzy.FuzzyText(suffix='@gm.com')
    merchant = factory.SubFactory(MerchantFactory)
    name = fuzzy.FuzzyText()
    phone = ''


class ExternalJobFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'tasks.ExternalJob'

    source_id = fuzzy.FuzzyInteger(1, 50)
    source_type = factory.LazyAttribute(lambda _: ContentType.objects.get(model='merchantapikey'))
    external_id = factory.Sequence(lambda n: "external-job-%03d" % n)


today = timezone.now()


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'tasks.Order'

    external_job = factory.SubFactory(ExternalJobFactory)
    driver = factory.SubFactory(DriverFactory)
    manager = factory.SubFactory(ManagerFactory)
    merchant = factory.SubFactory(MerchantFactory)
    sub_branding = factory.SubFactory(SubBrandingFactory)
    pickup_address = factory.SubFactory(OrderLocationFactory)
    deliver_address = factory.SubFactory(OrderLocationFactory)
    starting_point = factory.SubFactory(OrderLocationFactory)
    customer = factory.SubFactory(CustomerFactory)
    deliver_before = fuzzy.FuzzyDateTime(today + timedelta(days=1), today + timedelta(weeks=100))

    @factory.post_generation
    def labels(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            for label in extracted:
                self.labels.add(label)


class BarcodesFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'tasks.Barcode'

    order = factory.SubFactory(OrderFactory)
    code_data = fuzzy.FuzzyText()


class TerminateCodeFactory(factory.DjangoModelFactory):
    class Meta:
        model = 'tasks.TerminateCode'

    merchant = factory.SubFactory(MerchantFactory)


class SkidFactory(factory.DjangoModelFactory):
    class Meta:
        model = 'tasks.SKID'

    name = fuzzy.FuzzyText()
    weight = fuzzy.FuzzyFloat(low=0, high=100)
    width = fuzzy.FuzzyFloat(low=0, high=100)
    height = fuzzy.FuzzyFloat(low=0, high=100)
    length = fuzzy.FuzzyFloat(low=0, high=100)
