# coding=utf-8

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from rest_framework.test import APITestCase

from base.factories import ManagerFactory
from merchant.admin.forms import MerchantForm
from merchant.factories import MerchantFactory
from merchant.models import Merchant
from radaro_utils import countries
from tasks.models.orders import Customer
from tasks.tests.factories import CustomerFactory, OrderFactory


class MerchantTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        super(MerchantTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)

    def test_get_customers_list(self):
        self.client.force_authenticate(self.manager)

        other_merchant = MerchantFactory()
        CustomerFactory(merchant=other_merchant)
        CustomerFactory.create_batch(15, merchant=self.merchant)

        resp = self.client.get('/api/merchant-customers/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], Customer.objects.filter(merchant=self.merchant).count())


class MerchantCMSTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(countries=[countries.AUSTRALIA, countries.BELARUS])
        cls.manager = ManagerFactory(merchant=cls.merchant)

    def test_remove_country(self):
        customer_by = CustomerFactory(merchant=self.merchant, phone="+375259000000")
        OrderFactory(merchant=self.merchant, customer=customer_by)
        self.merchant.countries = [countries.AUSTRALIA, ]
        with self.assertRaises(ValidationError) as context:
            self.merchant.full_clean()
        self.assertDictEqual({'countries': ["You can\'t disable country (Belarus), because you have phones from it."]},
                             context.exception.message_dict)

    def test_default_distance(self):
        form = MerchantForm()
        self.assertEqual(form.fields['distance_show_in'].initial(), Merchant.KM)

    @override_settings(DEFAULT_DISTANCE_SHOW_IN='mi')
    def test_changed_default_distance(self):
        form = MerchantForm()
        self.assertEqual(form.fields['distance_show_in'].initial(), Merchant.MILES)


@override_settings(CLUSTER_NAME='test')
class MerchantIdentifierGenerationTestCase(TestCase):
    def test_generate_identifier_on_create(self):
        merchant = MerchantFactory()
        self.assertEqual(merchant.merchant_identifier, '%s-test' % merchant.name.lower())

    def test_generate_identical_merchants_names(self):
        merchant = MerchantFactory(name='Name')
        self.assertEqual(merchant.merchant_identifier, 'name-test')
        merchant = MerchantFactory(name='Name')
        self.assertEqual(merchant.merchant_identifier, 'name-1-test')
        merchant = MerchantFactory(name='Name')
        self.assertEqual(merchant.merchant_identifier, 'name-2-test')

    def test_long_names(self):
        merchant = MerchantFactory(name='Long name of merchant longer than 30 symbols')
        self.assertEqual(merchant.merchant_identifier, '%s-test' % 'longnameofmerchantlongerthan30')
        merchant = MerchantFactory(name='long_name_of_merchant_longer_than_30_symbols')
        self.assertEqual(merchant.merchant_identifier, '%s-test' % merchant.name[:30])

    def test_ignore_wrong_symbols(self):
        merchant = MerchantFactory(name=u'Name_with_unicode_象形')
        self.assertEqual(merchant.merchant_identifier, '%s-test' % 'name_with_unicode_')
        merchant = MerchantFactory(name=u'Name*:;_|with_\\/brackets_()')
        self.assertEqual(merchant.merchant_identifier, '%s-test' % 'name_with_brackets_')

    def test_generate_postfix(self):
        test_cluster_names = (
            ('test', 'test'),
            ('Radaro S1', 'radaro_s1'),
            ('Radaro S2', 'radaro_s2'),
            ('Radaro S1 (Staging)', 'radaro_s1_staging'),
            ('Radaro S1(Staging)', 'radaro_s1staging'),
        )
        for name, identifier_postfix in test_cluster_names:
            with override_settings(CLUSTER_NAME=name):
                self.assertEqual(Merchant.generate_identifier('Mer'), 'mer-%s' % identifier_postfix)
