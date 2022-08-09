from __future__ import absolute_import, unicode_literals

import os
import shutil

from django.conf import settings

from rest_framework.status import HTTP_200_OK

from base.models import Member
from base.tests.base_test_cases import BaseChangeAvatarFieldTestCase
from driver.tests.base_test_cases import BaseDriverTestCase
from merchant.factories import HubFactory


class DriverChangeAvatarTestCase(BaseChangeAvatarFieldTestCase):
    role = 'driver'
    static_folder = os.path.join(settings.BASE_DIR, 'static')

    def setUp(self):
        driver_icon = os.path.join(self.static_folder, settings.DEFAULT_DRIVER_ICON)
        if os.path.exists(self.static_folder) or os.path.exists(driver_icon):
            shutil.rmtree(self.static_folder)
        os.mkdir(self.static_folder)
        os.link(os.path.join(settings.BASE_DIR, 'base/static', settings.DEFAULT_DRIVER_ICON), driver_icon)
        super(DriverChangeAvatarTestCase, self).setUp()

    def test_reset_to_default_avatar(self):
        resp = self.client.patch(self.base_url + 'users/me', data={'avatar': None})
        self.assertEqual(resp.status_code, HTTP_200_OK)
        driver = Member.objects.get(id=self.driver.id)
        with open(os.path.join(self.static_folder, settings.DEFAULT_DRIVER_ICON), 'rb') as pic:
            with driver.avatar.open():
                self.assertEqual(pic.read(), driver.avatar.read())
                driver.avatar.seek(0)
                with driver.thumb_avatar_100x100_field.open():
                    self.assertEqual(driver.avatar.read(), driver.thumb_avatar_100x100_field.read())


class ManagerChangeDriverFieldsTestCase(BaseDriverTestCase):
    def setUp(self) -> None:
        self.client.force_authenticate(self.manager)
        self.hubs = HubFactory.create_batch(size=2, merchant=self.merchant)
        self.url = '/api/web/drivers/{}'.format(self.driver.id)

    def test_set_starting_hub(self):
        resp = self.client.patch(self.url, data={'starting_hub_id': self.hubs[0].id})
        self.assertEqual(resp.data['starting_hub']['id'], self.hubs[0].id)
        self.assertIsNone(resp.data['ending_hub'])

    def test_remove_ending_hub(self):
        resp = self.client.patch(self.url, data={'ending_hub_id': self.hubs[1].id})
        self.assertEqual(resp.data['ending_hub']['id'], self.hubs[1].id)
        self.assertIsNone(resp.data['starting_hub'])
        resp = self.client.patch(self.url, data={'ending_hub_id': None})
        self.assertIsNone(resp.data['ending_hub'])
