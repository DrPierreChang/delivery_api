from rest_framework.test import APITestCase

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import MerchantFactory
from notification.factories import FCMDeviceFactory


class BaseDataPushNotificationTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        super(BaseDataPushNotificationTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant)
        cls.device = FCMDeviceFactory(user=cls.driver, api_version=1)

    def get_message(self, obj):
        msg = {
            'data': {
                'id': obj.id,
                'model': obj.__class__.__name__
            }
        }
        return msg
        
    def update_field_value(self, obj, name, new_value):
        setattr(obj, name, new_value)
        obj.save()
