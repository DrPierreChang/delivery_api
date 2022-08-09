from rest_framework import status
from rest_framework.test import APITestCase

from constance.test import override_config
from drf_secure_token.models import Token

from base.factories import ManagerFactory
from base.models.invitations import Invite
from base.models.members import Member
from driver.utils import WorkStatus


class DriverInvitationTestCase(APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    @classmethod
    def setUpTestData(cls):
        cls.manager = ManagerFactory(
            merchant__countries=["AU", ],
            work_status=WorkStatus.WORKING,
        )

        cls.invite_user_info = {
            "phone": "+61499999990",
            "email": "new_driver@gm.co",
            "first_name": "Testdriver"
        }

    def logout_manager(self):
        key = Token.objects.create(user=self.manager).key
        headers = {'HTTP_AUTHORIZATION': 'Token {}'.format(key)}
        self.client.delete('/api/auth/logout/', {}, **headers)

    def create_default_invite(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.post('/api/invitations/', self.invite_user_info)
        return resp

    def create_pin_code(self):
        self.create_default_invite()
        self.logout_manager()
        resp = self.client.post('/api/invitations/getcode/', {'phone': self.invite_user_info['phone']})
        return resp

    def send_validation(self):
        self.create_pin_code()
        phone = self.invite_user_info['phone']
        pin = Invite.objects.get(phone=phone).pin_code
        resp = self.client.post('/api/invitations/validatecode/', {'phone': phone, 'pin_code': pin})
        return resp

    def send_password(self, password):
        phone = self.invite_user_info['phone']
        self.create_pin_code()

        pin = Invite.objects.get(phone=phone).pin_code

        resp = self.client.post('/api/invitations/password/', {
            "phone": phone,
            "pin_code": pin,
            "password": password
        })
        return resp

    def test_send_invitation(self):
        resp = self.create_default_invite()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Invite.objects.filter(pk=resp.data['id']).exists())

    def test_send_invitation_with_incorrect_phone_for_region(self):
        invite_info = {
            "phone": "+375440000001",
            "email": "test1@gm.co",
            "first_name": "Testdriver"
        }
        self.client.force_authenticate(self.manager)
        resp = self.client.post('/api/invitations/', invite_info)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(resp.data['errors'].get('phone', ''))

    def test_send_invitation_with_non_unique_data(self):
        self.create_default_invite()
        non_unique_email = {
            "phone": "+61499999989",
            "email": self.invite_user_info['email'],
            "first_name": "Johny"
        }
        resp = self.client.post('/api/invitations/', non_unique_email)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(resp.data['errors'].get('email', ''))

        non_unique_phone = {
            "phone": self.invite_user_info['phone'],
            "email": "other_new_driver@gm.co",
            "first_name": "Johny"
        }
        resp = self.client.post('/api/invitations/', non_unique_phone)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Invite.objects.count(), 1)

    def test_send_pin(self):
        resp = self.create_pin_code()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(Invite.objects.get(email=self.invite_user_info['email']).pin_code is not None)

    def test_send_pin_for_android(self):
        self.create_default_invite()
        self.logout_manager()
        resp = self.client.post('/api/invitations/getcode/', {
            'phone': self.invite_user_info['phone'],
            'app_type': 'android',
            'app_variant': 'radaro',
        })

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(Invite.objects.get(email=self.invite_user_info['email']).pin_code is not None)

    def test_send_pin_without_prior_invitation(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.post('/api/invitations/getcode/', {'email': "any_email@gm.co"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_validate_pin(self):
        resp = self.send_validation()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @override_config(TOKEN_TIMEOUT_MIN=0)
    def test_validate_pin_timeout(self):
        resp = self.send_validation()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_correct_password(self):
        resp = self.send_password('Rdb12p0!zQf')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Member.objects.filter(email=resp.data['email']).exists())

    def test_common_password(self):
        resp = self.send_password('Password1')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        error = resp.data['errors'].get('password', [])
        self.assertTrue(error)
        self.assertIn('too common', error[0])

    def test_password_without_uppercase_letters(self):
        resp = self.send_password('1qwde34gt1')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        error = resp.data['errors'].get('password', [])
        self.assertTrue(error)
        self.assertIn('uppercase character', error[0])

    def test_password_without_lowercase_letters(self):
        resp = self.send_password('1RHFTP34LL1')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        error = resp.data['errors'].get('password', [])
        self.assertTrue(error)
        self.assertIn('lowercase character', error[0])

    def test_password_without_numbers(self):
        resp = self.send_password('THdfMPosdfW')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        error = resp.data['errors'].get('password', [])
        self.assertTrue(error)
        self.assertIn('number', error[0])

    def test_short_password(self):
        resp = self.send_password('1wQ')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        error = resp.data['errors'].get('password', [])
        self.assertTrue(error)
        self.assertIn('too short', error[0])
