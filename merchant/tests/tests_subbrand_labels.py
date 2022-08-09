from rest_framework.test import APITestCase

from base.factories import SubManagerFactory
from merchant.factories import LabelFactory, MerchantFactory
from merchant.models import Label


class MerchantLabelsTestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        super(MerchantLabelsTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory(enable_labels=True)
        cls.submanager = SubManagerFactory(merchant=cls.merchant)

    def setUp(self):
        self.label = LabelFactory(merchant=self.merchant, color=Label.DARK_RED, name="Test")
        self.another_label = LabelFactory(merchant=self.merchant, color=Label.BURGUNDY, name="Test")
        self.client.force_authenticate(self.submanager)

    def test_merchant_colors(self):
        resp = self.client.get('/api/web/subbrand/labels/')
        self.assertGreater(resp.data['count'], 0)
