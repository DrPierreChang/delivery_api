import mock

from notification.tests.base_test_cases import BaseDataPushNotificationTestCase

from ..factories import HubFactory, SubBrandingFactory
from ..models import Hub, SubBranding


class MerchantEventNotificationTestCase(BaseDataPushNotificationTestCase):
    @classmethod
    def setUpTestData(cls):
        super(MerchantEventNotificationTestCase, cls).setUpTestData()

    def setUp(self):
        self.client.force_authenticate(self.manager)

    def test_background_notification_on_merchant_change(self):
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            data = {
                "description": "new_description"
            }
            self.client.patch('/api/merchant/my/', data=data)
            self.assertTrue(send_notification.called)
            _, kwargs = send_notification.call_args

            message = self.get_message(self.merchant)
            message['type'] = 'MERCHANT_CHANGED'
            
            self.assertDictEqual(kwargs['message'], message)
            self.assertEqual(kwargs['content_available'], True)


class HubEventNotificationTestCase(BaseDataPushNotificationTestCase):
    @classmethod
    def setUpTestData(cls):
        super(HubEventNotificationTestCase, cls).setUpTestData()

    def setUp(self):
        self.client.force_authenticate(self.manager)
        self.hub = HubFactory(merchant=self.merchant)
        self.message = self.get_message(self.hub)

    def test_background_notification_on_hub_creation(self):
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            data = {
                "name": "test_hub",
                "location": {
                    "location": "64.37014, -57.46077"
                }
            }
            self.client.post('/api/hubs/', data=data)
            self.assertTrue(send_notification.called)
            _, kwargs = send_notification.call_args
            new_hub = Hub.objects.get(name=data['name'])
            message = self.get_message(new_hub)
            message['type'] = 'NEW_HUB'
            self.assertDictEqual(kwargs['message'], message)
            self.assertEqual(kwargs['content_available'], True)

    def test_background_notification_on_hub_change(self):
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            data = {
                "phone": "12345678"
            }
            self.client.patch('/api/hubs/%s' % self.hub.id, data=data)
            _, kwargs = send_notification.call_args
            self.assertTrue(send_notification.called)
            self.message['type'] = 'HUB_CHANGED'
            self.assertDictEqual(kwargs['message'], self.message)
            self.assertEqual(kwargs['content_available'], True)

    def test_background_notification_on_hub_deletion(self):
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            self.client.delete('/api/hubs/%s' % self.hub.id)
            _, kwargs = send_notification.call_args
            self.assertTrue(send_notification.called)
            self.message['type'] = 'HUB_REMOVED'
            self.assertDictEqual(kwargs['message'], self.message)
            self.assertEqual(kwargs['content_available'], True)


class SubBrandEventNotificationTestCase(BaseDataPushNotificationTestCase):
    @classmethod
    def setUpTestData(cls):
        super(SubBrandEventNotificationTestCase, cls).setUpTestData()

    def setUp(self):
        self.client.force_authenticate(self.manager)
        self.sub_brand = SubBrandingFactory(merchant=self.merchant)
        self.message = self.get_message(self.sub_brand)

    def test_background_notification_on_subbrand_creation(self):
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            data = {
                "name": "test_subbrand"
            }
            self.client.post('/api/sub-branding/', data=data)
            self.assertTrue(send_notification.called)
            _, kwargs = send_notification.call_args
            new_sub_brand = SubBranding.objects.get(name=data['name'])
            message = self.get_message(new_sub_brand)
            message['type'] = 'NEW_SUBBRANDING'
            self.assertDictEqual(kwargs['message'], message)
            self.assertEqual(kwargs['content_available'], True)

    def test_background_notification_on_subbrand_change(self):
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            data = {
                "sms_sender": "new_sender"
            }
            self.client.patch('/api/sub-branding/%s' % self.sub_brand.id, data=data)
            _, kwargs = send_notification.call_args
            self.assertTrue(send_notification.called)
            self.message['type'] = 'SUBBRANDING_CHANGED'
            self.assertDictEqual(kwargs['message'], self.message)
            self.assertEqual(kwargs['content_available'], True)

    def test_background_notification_on_subbrand_deletion(self):
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            self.client.delete('/api/sub-branding/%s' % self.sub_brand.id)
            _, kwargs = send_notification.call_args
            self.assertTrue(send_notification.called)
            self.message['type'] = 'SUBBRANDING_REMOVED'
            self.assertDictEqual(kwargs['message'], self.message)
            self.assertEqual(kwargs['content_available'], True)   
