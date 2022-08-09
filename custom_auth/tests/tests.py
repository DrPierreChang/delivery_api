import random
import tempfile
from base64 import b64encode

from rest_framework import status
from rest_framework.test import APITestCase

import mock
from drf_secure_token.models import Token
from PIL import Image

from base.factories import (
    AdminFactory,
    DriverFactory,
    ManagerFactory,
    MemberFactory,
    ObserverFactory,
    SubManagerFactory,
)
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from notification.factories import FCMDeviceFactory, FCMDeviceFactoryIOS


class LoginTestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        super(LoginTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory()
        cls.user_data = {'email': 'user@test.com',
                         'phone': '+619999999999',
                         'merchant': cls.merchant}
        cls.user_password = '123qweASD'

    def login_new_driver(self):
        random_str = lambda: ''.join(map(chr, [random.randint(1, 100) for i in range(10)]))

        driver = DriverFactory(**self.user_data)
        driver.set_password(self.user_password)
        driver.save()

        resp = self.client.post('/api/auth/login-driver/', {'username': self.user_data['email'],
                                                            'password': self.user_password})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        token = Token.objects.filter(user=driver, key=resp.get('X-Token')).first()
        self.assertIsNotNone(token)

        self.client.force_authenticate(driver)
        resp = self.client.post('/api/register-device/fcm/', data={'device_id': random_str(),
                                                                   'registration_id': random_str()})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        return driver

    def test_success_admin_login(self):
        admin = AdminFactory(**self.user_data)
        admin.set_password(self.user_password)
        admin.save()

        resp = self.client.post('/api/auth/login-merchant/', {'username': self.user_data['email'],
                                                              'password': self.user_password})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        token = Token.objects.get(key=resp.get('X-Token', None))
        self.assertEqual(token.user, admin)
        self.assertEqual(resp.json()['id'], admin.id)

    def test_success_manager_login(self):
        manager = ManagerFactory(**self.user_data)
        manager.set_password(self.user_password)
        manager.save()

        resp = self.client.post('/api/auth/login-merchant/', {'username': self.user_data['email'],
                                                              'password': self.user_password})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        token = Token.objects.get(key=resp.get('X-Token', None))
        self.assertEqual(token.user, manager)
        self.assertEqual(resp.json()['id'], manager.id)

    def test_success_submanager_login(self):
        submanager = SubManagerFactory(**self.user_data)
        submanager.set_password(self.user_password)
        submanager.save()

        resp = self.client.post('/api/auth/login-merchant/', {'username': self.user_data['email'],
                                                              'password': self.user_password})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        token = Token.objects.get(key=resp.get('X-Token', None))
        self.assertEqual(token.user, submanager)
        self.assertEqual(resp.json()['id'], submanager.id)

    def test_success_driver_login(self):
        driver = DriverFactory(**self.user_data)
        driver.set_password(self.user_password)
        driver.save()

        resp = self.client.post('/api/auth/login-driver/', {'username': self.user_data['email'],
                                                            'password': self.user_password})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        token = Token.objects.get(key=resp.get('X-Token', None))
        self.assertEqual(token.user, driver)
        self.assertEqual(resp.json()['id'], driver.id)

    def test_fail_inactive_driver_login(self):
        driver = DriverFactory(**self.user_data)
        driver.set_password(self.user_password)
        driver.is_active = False
        driver.save()

        resp = self.client.post('/api/auth/login-driver/', {'username': self.user_data['email'],
                                                            'password': self.user_password})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_success_driver_force_login(self):
        driver = self.login_new_driver()
        resp = self.client.post('/api/auth/login-driver/', {'username': self.user_data['email'],
                                                            'password': self.user_password})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        devices = [FCMDeviceFactory(user=driver), FCMDeviceFactoryIOS(user=driver)]
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            resp = self.client.post('/api/auth/login-driver/?force=True&device_id={}'.format(devices[0].device_id),
                                    {'username': self.user_data['email'], 'password': self.user_password})
            self.assertDictEqual(send_notification.call_args[1]['message'], {
                "data": {
                    u"text": u"{}, you logged in on another device.".format(driver.first_name)
                },
                "type": u"FORCE_LOGOUT"
            })
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        token = Token.objects.get(key=resp.get('X-Token', None))
        self.assertEqual(token.user, driver)

        self.assertEqual(resp.json()['id'], driver.id)

    def test_fail_inactive_driver_force_login(self):
        driver = self.login_new_driver()

        resp = self.client.post('/api/auth/login-driver/', {'username': self.user_data['email'],
                                                            'password': self.user_password})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        driver.is_active = False
        driver.save()
        resp = self.client.post('/api/auth/login-driver/?force=True', {'username': self.user_data['email'],
                                                                       'password': self.user_password})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class LogoutTestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        super(LogoutTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory()
        cls.member = MemberFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)

    def test_success_logout(self):
        key = Token.objects.create(user=self.member).key
        headers = {'HTTP_AUTHORIZATION': 'Token {}'.format(key)}
        resp = self.client.delete('/api/auth/logout/', {}, **headers)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIs(Token.objects.filter(key=key, user=self.member).exists(), False)


def get_temporary_image(temp_file, size, color):
    img = Image.new('RGB', size, color)
    img.save(temp_file, 'jpeg')
    return temp_file


class UserAPITestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        super(UserAPITestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.manager.radaro_router_manager.create(extra={'remote_id': 1, 'synced': True})
        cls.submanager = SubManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant)

    def test_getting_manager_info(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/users/me/')
        resp_json_data = resp.json()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_json_data['id'], self.manager.id)

    def test_getting_submanager_info(self):
        self.client.force_authenticate(self.submanager)
        resp = self.client.get('/api/users/me/')
        resp_json_data = resp.json()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue('sub_branding' in resp_json_data.keys())

    def test_getting_driver_info(self):
        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/users/me/')
        resp_json_data = resp.json()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_json_data['member_id'], self.driver.member_id)

    def test_update_manager_info(self):
        self.client.force_authenticate(self.manager)
        temp_file = tempfile.NamedTemporaryFile()
        temp_img = get_temporary_image(temp_file, (512, 512), 'red')
        with open(temp_img.name, 'rb') as f:
            encoded_temp_img = b64encode(f.read())
        body = {"first_name": "New first name",
                "last_name": "New last name",
                "phone": "+61411111111",
                "email": "new_test@test.com",
                "avatar": encoded_temp_img, }
        resp = self.client.patch('/api/users/me/', data=body)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_update_submanager_info(self):
        self.client.force_authenticate(self.submanager)
        body = {"first_name": "New first name"}
        resp = self.client.patch('/api/users/me/', data=body)

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_manager_info_to_blank(self):
        self.client.force_authenticate(self.manager)
        temp_file = tempfile.NamedTemporaryFile()
        temp_img = get_temporary_image(temp_file, (512, 512), 'red')
        with open(temp_img.name, 'rb') as f:
            encoded_temp_img = b64encode(f.read())
        body = {"first_name": "New first name",
                "last_name": "New last name",
                "phone": "",
                "email": "new_test@test.com",
                "avatar": encoded_temp_img, }
        resp = self.client.patch('/api/users/me/', data=body)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_manager_info_to_null(self):
        self.client.force_authenticate(self.manager)
        temp_file = tempfile.NamedTemporaryFile()
        temp_img = get_temporary_image(temp_file, (512, 512), 'red')
        with open(temp_img.name, 'rb') as f:
            encoded_temp_img = b64encode(f.read())
        body = {"first_name": "New first name",
                "last_name": "New last name",
                "phone": None,
                "email": "new_test@test.com",
                "avatar": encoded_temp_img, }
        resp = self.client.patch('/api/users/me/', data=body)

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_getting_merchant_language(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/users/me/')
        self.assertFalse(resp.has_header('Content-Language'))

        resp = self.client.get('/api/users/me/', HTTP_X_RETURN_LANGUAGE=True)
        self.assertTrue(resp.has_header('Content-Language'))

    def test_get_merchants_list(self):
        merchants = MerchantFactory.create_batch(size=3)

        members = [
            ManagerFactory(merchant=self.merchant),
            AdminFactory(merchant=self.merchant),
            ObserverFactory(merchant=self.merchant),
        ]
        for member in members:
            member.merchants.add(*merchants)

            self.client.force_authenticate(member)
            resp = self.client.get('/api/users/me/available-merchants/')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertIsNotNone(resp.data)

    def test_change_merchant(self):
        merchants = MerchantFactory.create_batch(size=3)

        members = [
            ManagerFactory(merchant=self.merchant),
            AdminFactory(merchant=self.merchant),
            ObserverFactory(merchant=self.merchant),
        ]
        for member in members:
            member.merchants.add(self.merchant, *merchants)

            old_merchant_id = member.current_merchant_id

            self.client.force_authenticate(member)
            resp = self.client.patch('/api/users/me/', data={'merchant_id': merchants[0].id})
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

            member.refresh_from_db()
            self.assertNotEqual(old_merchant_id, resp.data['merchant']['id'])


class PasswordRecoveryAPITestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        super(PasswordRecoveryAPITestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory()
        cls.user_data = {'email': 'driver@test.com',
                         'merchant': cls.merchant}
        cls.user_password = '123qweASD'

    def setUp(self):
        super(PasswordRecoveryAPITestCase, self).setUp()
        self.user = DriverFactory(**self.user_data)
        self.user.set_password(self.user_password)
        self.user.save()
        login_resp = self.client.post('/api/auth/login-driver/?force=True', {'username': self.user_data['email'],
                                                                             'password': self.user_password})
        self.token = 'Token {}'.format(Token.objects.get(key=login_resp.get('X-Token', None)).key)
        self.headers = {'HTTP_AUTHORIZATION': self.token}

    def tearDown(self):
        super(PasswordRecoveryAPITestCase, self).tearDown()
        self.client.post('/api/auth/logout', {}, **self.headers)
        self.user.delete()

    def test_correct_old_password_and_correct_new_password(self):
        resp = self.client.patch('/api/users/me', {'old_password': self.user_password, 'password': 'new123qweASD'},
                                 **self.headers)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_non_correct_old_password(self):
        resp = self.client.patch('/api/users/me', {'old_password': 'not123qweASD', 'password': 'new123qweASD'},
                                 **self.headers)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Old password is not valid.', resp.data['errors']['password'])

    def test_old_password_empty(self):
        resp = self.client.patch('/api/users/me', {'password': 'new123qweASD'}, **self.headers)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('You should provide your old password.', resp.data['errors']['password'])
