from __future__ import unicode_literals

import copy
import json
from collections import namedtuple

from django.conf import settings

from rest_framework.status import HTTP_201_CREATED
from rest_framework.test import APITestCase

from mock import mock

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import MerchantFactory
from notification.factories import (
    APNSDeviceFactory,
    FCMDeviceFactory,
    FCMDeviceFactoryIOS,
    GCMDeviceFactory,
    PushNotificationsSettingsFactory,
)
from notification.models import Device, GCMDevice


class NotificationTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        super(NotificationTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.gcm_device = GCMDeviceFactory.build()
        cls.fcm_device__android = FCMDeviceFactory.build()
        cls.fcm_device__ios = FCMDeviceFactoryIOS.build()

        cls.apple_device = APNSDeviceFactory.build()

        cls.message = {
            'type': 'JOB_ASSIGNED',
            'data': {
                'order_id': 128327841,
                'text': u'Sean, you have received a new job: "8 Scottsdale St, Surrey Hills VIC 3127, Australia"'
            }
        }
        cls.real_google_message = {
            'data': {
                'data': cls.message
            },
            'registration_ids': [cls.gcm_device.registration_id],
            'collapse_key': cls.message['type'],
        }
        cls.real_fcm_message__android = copy.copy(cls.real_google_message)
        cls.real_fcm_message__ios = dict({
            'notification': {
                'body': cls.message['data']['text'],
                'sound': 'default'
            },
            'priority': 10
        }, **cls.real_fcm_message__android)

        cls.real_fcm_data_message__ios = dict({
            'content_available': True
        }, **cls.real_fcm_message__android)

    def setUp(self):
        self.driver = DriverFactory(merchant=self.merchant)
        self.client.force_authenticate(self.driver)
        self.maxDiff = None

    @classmethod
    def to_dict(cls, device_request):
        fields = ('device_id', 'registration_id')
        return {x: getattr(device_request, x) for x in fields}

    @staticmethod
    def get_param_for(x, param):
        return settings.PUSH_NOTIFICATIONS_SETTINGS['{}_{}'.format(x, param)]

    def create_and_check_device(self, url, device_request, device_type=None):
        request = self.to_dict(device_request)
        compare_dict = {}
        if device_type:
            for i in (request, compare_dict):
                i['device_type'] = device_type

        resp = self.client.post(url, data=request)
        self.assertEqual(resp.status_code, HTTP_201_CREATED)

        devices = Device.objects.filter(user=self.driver)
        device = devices[0].cast()
        compare_dict.update({'device_id': device.device_id, 'registration_id': device.registration_id})
        self.assertDictEqual(request, compare_dict)
        self.assertEqual(device.api_version, 1)
        return device, devices

    def test_gcm(self):
        device, devices = self.create_and_check_device('/api/register-device/gcm/', self.gcm_device)

        MockResponse = namedtuple('Response', 'content')
        mock_resp = MockResponse('{"TEST": "TEST"}')

        with mock.patch('requests.post', return_value=mock_resp) as mock_request:
            devices.send_message(self.message)
            args, kwargs = mock_request.call_args
            self.assertEqual('https://android.googleapis.com/gcm/send', args[0])
            self.assertDictEqual(json.loads(kwargs['data']), self.real_google_message)
            self.assertEqual(kwargs['timeout'], settings.PUSH_SERVICE_TIMEOUT)
            mock_request.assert_called_once()

    def internal_test_fcm(self, os_type, device_type=False):
        fcm_device = getattr(self, 'fcm_device__{}'.format(os_type))
        fcm_real_message = copy.copy(getattr(self, 'real_fcm_message__{}'.format(os_type)))

        device, devices = self.create_and_check_device('/api/register-device/fcm/',
                                                       fcm_device, os_type if device_type else None)

        MockResponse = namedtuple('Response', 'content')
        mock_resp = MockResponse('{"TEST": "TEST"}')

        with mock.patch('requests.post', return_value=mock_resp) as mock_request:
            devices.send_message(self.message)
            args, kwargs = mock_request.call_args
            self.assertEqual('https://fcm.googleapis.com/fcm/send', args[0])

            self.assertDictEqual(json.loads(kwargs['data']),
                                 dict(fcm_real_message, registration_ids=[fcm_device.registration_id]))
            self.assertEqual(kwargs['timeout'], settings.PUSH_SERVICE_TIMEOUT)
            mock_request.assert_called_once()
 
    def internal_test_fcm_ios_silent(self):
        fcm_device = getattr(self, 'fcm_device__{}'.format(GCMDevice.IOS))
        fcm_real_message = copy.copy(getattr(self, 'real_fcm_data_message__{}'.format(GCMDevice.IOS)))

        device, devices = self.create_and_check_device('/api/register-device/fcm/',
                                                       fcm_device, GCMDevice.IOS)

        MockResponse = namedtuple('Response', 'content')
        mock_resp = MockResponse('{"TEST": "TEST"}')

        with mock.patch('requests.post', return_value=mock_resp) as mock_request:
            devices.send_message(self.message, content_available=True)
            args, kwargs = mock_request.call_args
            self.assertEqual('https://fcm.googleapis.com/fcm/send', args[0])

            self.assertDictEqual(json.loads(kwargs['data']),
                                 dict(fcm_real_message, registration_ids=[str(fcm_device.registration_id)]))
            self.assertEqual(kwargs['timeout'], settings.PUSH_SERVICE_TIMEOUT)
            mock_request.assert_called_once()        

    def test_fcm_ios(self):
        self.internal_test_fcm(GCMDevice.IOS, device_type=True)

    def test_fcm_ios_silent(self):
        self.internal_test_fcm_ios_silent()

    def test_fcm_android(self):
        self.internal_test_fcm(GCMDevice.ANDROID)

    def test_fcm_with_different_settings(self):
        push_settings = PushNotificationsSettingsFactory()
        new_merchant = MerchantFactory(push_notifications_settings=push_settings)
        self.driver = DriverFactory(merchant=new_merchant)

        self.client.force_authenticate(self.driver)
        device, devices = self.create_and_check_device('/api/register-device/fcm/', self.fcm_device__android)

        MockResponse = namedtuple('Response', 'content')
        mock_resp = MockResponse('{"TEST": "TEST"}')

        with mock.patch('requests.post', return_value=mock_resp) as mock_request:
            devices.send_message(self.message)
            args, kwargs = mock_request.call_args
            self.assertEqual('https://fcm.googleapis.com/fcm/send', args[0])

            fcm_real_message = copy.copy(self.real_fcm_message__android)
            fcm_real_message.update({'registration_ids': [self.fcm_device__android.registration_id]})
            self.assertDictEqual(json.loads(kwargs['data']), fcm_real_message)
            self.assertEqual(kwargs['timeout'], settings.PUSH_SERVICE_TIMEOUT)
            mock_request.assert_called_once()
