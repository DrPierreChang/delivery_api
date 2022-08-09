import mock

from notification.factories import FCMDeviceFactory
from tasks.tests.base_test_cases import BaseOrderTestCase


class LocalizedOrderPushNotificationTestCase(BaseOrderTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.driver.first_name = 'David'
        cls.driver.language = 'fr-ca'
        cls.driver.save()
        cls.device = FCMDeviceFactory(user=cls.driver, api_version=3)

    def setUp(self):
        self.order = self.create_default_order_with_status()
        self.client.force_authenticate(self.manager)

    @mock.patch('django.utils.translation.override')
    @mock.patch('notification.celery_tasks.send_device_notification.delay')
    def test_order_status_change_notification(self, push_mock, translation_mock):
        patch_url = f'/api/web/dev/orders/{self.order.id}'
        self.client.patch(patch_url, data={'status': 'in_progress'})
        push_mock.assert_called()
        translation_mock.assert_called()
        self.assertEqual(translation_mock.call_args[0][0], self.driver.language)
