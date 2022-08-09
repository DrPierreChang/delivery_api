from documents.tests.factories import TagFactory
from driver.tests.base_test_cases import BaseDriverTestCase


class TagTestCase(BaseDriverTestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.tags = TagFactory.create_batch(merchant=cls.merchant, size=3)

    def test_tag_api(self):
        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/mobile/tags/v1/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 3)
