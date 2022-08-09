from rest_framework import status
from rest_framework.test import APITestCase

from constance.test import override_config

from base.factories import ManagerFactory
from base.models.invitations import Invite
from base.models.members import Member
from driver.utils import WorkStatus


class DriverDriverInvitationTestCase(APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    @classmethod
    def setUpTestData(cls):
        cls.manager = ManagerFactory(
            merchant__countries=['AU', ],
            work_status=WorkStatus.WORKING,
        )

        cls.invite_user_info = {
            'phone': '+61499999990',
            'email': 'new_driver@gm.co',
            'first_name': 'Testdriver'
        }

    def create_default_invite(self):
        Invite.objects.create(initiator=self.manager, **self.invite_user_info)

    def create_pin_code(self):
        self.create_default_invite()
        resp = self.client.post('/api/mobile/invitations/v2/getcode/', {'phone': self.invite_user_info['phone']})
        return resp

    def create_pin_code_for_android(self):
        self.create_default_invite()
        resp = self.client.post(
            '/api/mobile/invitations/v2/getcode/',
            {
                'phone': self.invite_user_info['phone'],
                'app_type': 'android',
                'app_variant': 'radaro',
            }
        )
        return resp

    def create_pin_code_with_wrong_data(self):
        self.create_default_invite()
        resp = self.client.post(
            '/api/mobile/invitations/v2/getcode/',
            {
                'phone': self.invite_user_info['phone'],
                'app_type': 'bla',
                'app_variant': 'bla',
            }
        )
        return resp

    def send_validation(self):
        self.create_pin_code()
        phone = self.invite_user_info['phone']
        pin = Invite.objects.get(phone=phone).pin_code
        resp = self.client.post('/api/mobile/invitations/v2/validatecode/', {'phone': phone, 'pin_code': pin})
        return resp

    def send_password(self, password):
        phone = self.invite_user_info['phone']
        self.create_pin_code()

        pin = Invite.objects.get(phone=phone).pin_code

        resp = self.client.post('/api/mobile/invitations/v2/password/', {
            'phone': phone,
            'pin_code': pin,
            'password': password
        })
        return resp

    def test_correct_password(self):
        resp = self.send_password('Rdb12p0!zQf')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Member.objects.filter(email=resp.data['email']).exists())

    def test_send_pin(self):
        resp = self.create_pin_code()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(Invite.objects.get(email=self.invite_user_info['email']).pin_code is not None)

    def test_send_pin_for_android(self):
        resp = self.create_pin_code_for_android()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(Invite.objects.get(email=self.invite_user_info['email']).pin_code is not None)

    def test_send_pin_with_wrong_data(self):
        resp = self.create_pin_code_with_wrong_data()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_send_pin_without_prior_invitation(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.post('/api/mobile/invitations/v2/getcode/', {'email': 'any_email@gm.co'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_validate_pin(self):
        resp = self.send_validation()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @override_config(TOKEN_TIMEOUT_MIN=0)
    def test_validate_pin_timeout(self):
        resp = self.send_validation()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_common_password(self):
        resp = self.send_password('Password1')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        error = resp.data['errors'].get('password', [])
        self.assertTrue(error)
        self.assertIn('too common', error[0]['message'])

    def test_password_without_uppercase_letters(self):
        resp = self.send_password('1qwde34gt1')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        error = resp.data['errors'].get('password', [])
        self.assertTrue(error)
        self.assertIn('uppercase character', error[0]['message'])

    def test_password_without_lowercase_letters(self):
        resp = self.send_password('1RHFTP34LL1')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        error = resp.data['errors'].get('password', [])
        self.assertTrue(error)
        self.assertIn('lowercase character', error[0]['message'])

    def test_password_without_numbers(self):
        resp = self.send_password('THdfMPosdfW')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        error = resp.data['errors'].get('password', [])
        self.assertTrue(error)
        self.assertIn('number', error[0]['message'])

    def test_short_password(self):
        resp = self.send_password('1wQ')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        error = resp.data['errors'].get('password', [])
        self.assertTrue(error)
        self.assertIn('too short', error[0]['message'])
