from __future__ import absolute_import, unicode_literals

from rest_framework.status import HTTP_200_OK

from ..models import Member
from .base_test_cases import BaseChangeAvatarFieldTestCase


class ChangeAvatarTestCase(BaseChangeAvatarFieldTestCase):
    role = 'manager'

    def test_change_avatar(self):
        manager = Member.objects.get(id=self.manager.id)
        self.assertEqual( (manager.avatar.size, manager.thumb_avatar_100x100_field.size), (33645, 16375))

    def test_reset_avatar(self):
        resp = self.client.patch(self.base_url + 'users/me', data={'avatar': None})
        self.assertEqual(resp.status_code, HTTP_200_OK)
        manager = Member.objects.get(id=self.manager.id)
        self.assertEqual(manager.avatar._file, None)
        self.assertEqual(manager.avatar._file, manager.thumb_avatar_100x100_field._file)
