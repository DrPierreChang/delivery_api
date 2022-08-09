from datetime import date
from random import randint

from rest_framework import status
from rest_framework.test import APITestCase

from pinax.stripe.models import Card

from base.factories import AdminFactory
from merchant.factories import MerchantFactory


class MerchantsCardTestCase(APITestCase):
    VALID_CARD_NUMBERS = [
        '4000000360000006',
        '4000005540000008',
        '4000007020000003',
        '5555555555554444',
        '371449635398431'
    ]

    @classmethod
    def setUpTestData(cls):
        super(MerchantsCardTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory()
        cls.admin = AdminFactory(merchant=cls.merchant)

    @classmethod
    def create_card(cls, number, exp_month=None, exp_year=None, cvc=None):
        res = {
            'number': number,
            'exp_month': exp_month or randint(1, 12),
            'exp_year': exp_year or randint(2024, 2040),
            'cvc': cvc or "%03d" % randint(0, 999)
        }
        return res

    def setUp(self):
        self.client.force_authenticate(self.admin)

    def test_create_card(self):
        cur_date = date.today()
        exp_month, exp_year = cur_date.month, cur_date.year
        data = MerchantsCardTestCase.create_card(
            number=MerchantsCardTestCase.VALID_CARD_NUMBERS[0],
            exp_month=exp_month,
            exp_year=exp_year,
            cvc='434'
        )

        resp = self.client.post('/api/merchant/%s/cards/' % self.merchant.id, data=data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_list_cards(self):
        card_customer_id = None
        for i in range(5):
            card_info = MerchantsCardTestCase.create_card(MerchantsCardTestCase.VALID_CARD_NUMBERS[i])
            resp = self.client.post('/api/merchant/%s/cards/' % self.merchant.id, data=card_info)
            card_customer_id = card_customer_id or resp.data['customer']

        resp = self.client.get('/api/merchant/%s/cards/' % self.merchant.id)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotEqual(resp.data['count'], 0)
        self.assertEqual(resp.data['count'], Card.objects.filter(customer_id=card_customer_id).count())

    def test_card_detailed_info(self):
        card_info = MerchantsCardTestCase.create_card(MerchantsCardTestCase.VALID_CARD_NUMBERS[0])
        resp = self.client.post('/api/merchant/%s/cards/' % self.merchant.id, data=card_info)
        card_id = resp.data['id']

        resp = self.client.get('/api/merchant/%s/cards/%s/' % (self.merchant.id, card_id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_card_change(self):
        card_info = MerchantsCardTestCase.create_card(MerchantsCardTestCase.VALID_CARD_NUMBERS[0])
        resp = self.client.post('/api/merchant/%s/cards/' % self.merchant.id, data=card_info)
        old_card_id = resp.data['id']

        card_updated_info = card_info
        card_updated_info['exp_year'] = 2042
        resp = self.client.post('/api/merchant/%s/cards/%s/change/' % (self.merchant.id, old_card_id), data=card_updated_info)
        new_card_id = resp.data['id']

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(Card.objects.filter(id=old_card_id).exists())
        self.assertTrue(Card.objects.filter(id=new_card_id).exists())
        self.assertEqual(Card.objects.get(id=new_card_id).exp_year, card_updated_info['exp_year'])

    def test_card_charge(self):
        card_info = MerchantsCardTestCase.create_card(MerchantsCardTestCase.VALID_CARD_NUMBERS[0])
        resp = self.client.post('/api/merchant/%s/cards/' % self.merchant.id, data=card_info)
        card_id = resp.data['id']

        old_balance = self.merchant.balance

        charge_info = {'amount': 20.20, }
        resp = self.client.post('/api/merchant/%s/cards/%s/charge/' % (self.merchant.id, card_id), data=charge_info)
        self.merchant.refresh_from_db()
        new_balance = self.merchant.balance

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(float(new_balance-old_balance), charge_info['amount'])
