import base64
import os

from rest_framework.status import HTTP_200_OK

from driver.tests.base_test_cases import BaseDriverTestCase

base_dir = os.path.dirname(__file__)


class BaseChangeAvatarFieldTestCase(BaseDriverTestCase):
    base_url = '/api/v2/'
    image_file = os.path.join(base_dir, 'polkovnik.jpg')
    role = None

    def setUp(self):
        self.client.force_authenticate(getattr(self, self.role))
        with open(self.image_file, 'rb') as pic:
            resp = self.client.patch(self.base_url + 'users/me', data={'avatar': base64.b64encode(pic.read())})
        self.assertEqual(resp.status_code, HTTP_200_OK)
