from merchant.tests.tests import MerchantTestCase
from webhooks.factories import MerchantAPIKeyFactory


class APIKeyTestCase(MerchantTestCase):
    @classmethod
    def setUpTestData(cls):
        super(APIKeyTestCase, cls).setUpTestData()
        cls.apikey = MerchantAPIKeyFactory(creator=cls.manager, merchant=cls.merchant, available=True)
