from django.conf import settings

from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from merchant.models import Merchant
from tasks.models.orders import Order, OrderStatus
from tasks.models.terminate_code import TerminateCodeConstants
from tasks.tests.factories import OrderFactory

ERROR = TerminateCodeConstants.TYPE_ERROR
SUCCESS = TerminateCodeConstants.TYPE_SUCCESS


class InitializeTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        super(InitializeTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory(advanced_completion=Merchant.ADVANCED_COMPLETION_OPTIONAL)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.error_codes = settings.TERMINATE_CODES[ERROR]
        cls.success_codes = settings.TERMINATE_CODES[SUCCESS]

    def setUp(self):
        self.order = OrderFactory(
            merchant=self.merchant, status=OrderStatus.IN_PROGRESS, driver=self.driver, manager=self.manager
        )

    def change_status_to(self, order, order_status=None, resp_status=status.HTTP_200_OK, **params):
        self.client.force_authenticate(self.manager)
        if order_status:
            params['status'] = order_status
        order_resp = self.client.patch(f'/api/web/dev/orders/{order.id}/', dict(params))
        self.assertEqual(order_resp.status_code, resp_status)
        if resp_status == status.HTTP_200_OK:
            self.assertEqual(order_resp.data['status'], order_status)
        return order_resp


class TerminateOrderTestCase(InitializeTestCase):
    def test_failed_by_manager(self):
        self.change_status_to(self.order, OrderStatus.FAILED)
        self.assertTrue(Order.objects.filter(id=self.order.id, status=OrderStatus.FAILED).exists())

    def test_delivered_by_manager(self):
        self.change_status_to(self.order, OrderStatus.DELIVERED)
        self.assertTrue(Order.objects.filter(id=self.order.id, status=OrderStatus.DELIVERED).exists())


class GetInfoAboutErrorCodeOfFailedOrder_ApiV1TestCase(InitializeTestCase):
    def setUp(self):
        super(GetInfoAboutErrorCodeOfFailedOrder_ApiV1TestCase, self).setUp()
        self.order.terminate_codes.add(self.merchant.terminate_codes.get(code=self.error_codes['OTHER']))
        self.order.terminate_comment = 'Test v1'
        self.order.save()

    def test_get_info_by_manager(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get(f'/api/web/dev/orders/{self.order.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['completion']['comment'], 'Test v1')
        self.assertEqual(resp.data['completion']['codes'][0]['code'], self.error_codes['OTHER'])


class TerminateCodesRepresentationTestCase(InitializeTestCase):
    def setUp(self):
        super(TerminateCodesRepresentationTestCase, self).setUp()
        self.order.terminate_codes.add(
            self.merchant.terminate_codes.get(code=self.error_codes['OTHER']),
            self.merchant.terminate_codes.get(code=self.error_codes['STARTING'])
        )
        self.order.terminate_comment = 'Test v1'
        self.order.save()

    def test_multiple_terminate_codes_represenation(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get(f'/api/web/dev/orders/{self.order.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [x['code'] for x in resp.data['completion']['codes']],
            list(self.order.terminate_codes.values_list('code', flat=True))
        )
