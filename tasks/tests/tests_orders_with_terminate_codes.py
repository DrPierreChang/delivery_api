from base64 import b64encode
from io import BytesIO

from django.conf import settings
from django.db.models import Q

from rest_framework import status
from rest_framework.test import APITestCase

from mock import patch
from PIL import Image

from base.factories import DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from merchant.models import Merchant
from notification.mixins import MessageTemplateStatus
from notification.models import TemplateEmailMessage
from tasks.api.legacy.serializers.terminate_code import ErrorCodeNumberSerializer
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
        self.order = OrderFactory(merchant=self.merchant, status=OrderStatus.IN_PROGRESS, driver=self.driver,
                                  manager=self.manager)

    def change_status_to(self, initiator, order, order_status=None, resp_status=status.HTTP_200_OK,
                         version='latest', **params):
        self.client.force_authenticate(initiator)
        update_method = self.client.put if initiator.is_driver else self.client.patch
        detail = '/status' if initiator.is_driver else ''
        if version != 'latest':
            _id = order.order_id if version < 2 else order.id
            version = 'v{number}'.format(number=version)
        else:
            _id = order.id
        url = '/api/{version}/orders/{id}{detail}'.format(version=version, id=_id, detail=detail)
        if order_status:
            params['status'] = order_status
        order_resp = update_method(url, dict(params))
        self.assertEqual(order_resp.status_code, resp_status)
        if resp_status == status.HTTP_200_OK:
            self.assertEqual(order_resp.data['status'], order_status)
        return order_resp


class TerminateOrderTestCase(InitializeTestCase):
    def test_failed_by_driver(self):
        self.change_status_to(self.driver, self.order, OrderStatus.FAILED)
        self.assertTrue(Order.objects.filter(id=self.order.id, status=OrderStatus.FAILED).exists())

    def test_failed_by_manager(self):
        self.change_status_to(self.manager, self.order, OrderStatus.FAILED)
        self.assertTrue(Order.objects.filter(id=self.order.id, status=OrderStatus.FAILED).exists())

    def test_delivered_by_driver(self):
        self.change_status_to(self.driver, self.order, OrderStatus.DELIVERED)
        self.assertTrue(Order.objects.filter(id=self.order.id, status=OrderStatus.DELIVERED).exists())

    def test_delivered_by_manager(self):
        self.change_status_to(self.manager, self.order, OrderStatus.DELIVERED)
        self.assertTrue(Order.objects.filter(id=self.order.id, status=OrderStatus.DELIVERED).exists())


class TerminateOrderWithCorrectCodeTestCase(InitializeTestCase):
    def test_failed_by_driver(self):
        self.change_status_to(self.driver, self.order, OrderStatus.FAILED,
                              terminate_code=self.error_codes['STARTING'])
        self.assertTrue(Order.objects.filter(id=self.order.id, status=OrderStatus.FAILED,
                                             terminate_codes__code=self.error_codes['STARTING'],
                                             terminate_codes__type=ERROR).exists())

    def test_failed_by_driver_with_multiple_codes(self):
        terminate_codes = [self.error_codes['STARTING'], self.error_codes['DEFAULT_CODES'][1]['code']]
        self.change_status_to(self.driver, self.order, OrderStatus.FAILED,
                              terminate_codes=terminate_codes)
        self.assertEqual(self.order.terminate_codes.count(), len(terminate_codes))

    def test_delivered_by_driver(self):
        self.change_status_to(self.driver, self.order, OrderStatus.DELIVERED,
                              terminate_code=self.success_codes['STARTING'])
        self.assertTrue(Order.objects.filter(id=self.order.id, status=OrderStatus.DELIVERED,
                                             terminate_codes__code=self.success_codes['STARTING'],
                                             terminate_codes__type=SUCCESS).exists())

    def test_delivered_by_driver_with_multiple_codes(self):
        terminate_codes = [self.success_codes['STARTING'], self.success_codes['DEFAULT_CODES'][1]['code']]
        self.change_status_to(self.driver, self.order, OrderStatus.DELIVERED,
                              terminate_codes=terminate_codes)
        self.assertEqual(self.order.terminate_codes.count(), len(terminate_codes))


class TerminateOrderWithNonExistedCodeTestCase(InitializeTestCase):
    def test_failed_by_driver(self):
        self.change_status_to(self.driver, self.order, OrderStatus.FAILED, resp_status=status.HTTP_400_BAD_REQUEST,
                              terminate_code=504)
        order_from_db = Order.objects.filter(id=self.order.id, status=OrderStatus.FAILED, terminate_codes__code=504)
        self.assertFalse(order_from_db.exists())

    def test_delivered_by_driver(self):
        self.change_status_to(self.driver, self.order, OrderStatus.DELIVERED, resp_status=status.HTTP_400_BAD_REQUEST,
                              terminate_code=204)
        order_from_db = Order.objects.filter(id=self.order.id, status=OrderStatus.DELIVERED, terminate_codes__code=204)
        self.assertFalse(order_from_db.exists())


class TerminateOrderWithOtherCodeTestCase(InitializeTestCase):
    def test_failed_by_driver_without_comment(self):
        self.change_status_to(self.driver, self.order, OrderStatus.FAILED, resp_status=status.HTTP_400_BAD_REQUEST,
                              terminate_code=self.error_codes['OTHER'])
        order_from_db = Order.objects.filter(id=self.order.id, status=OrderStatus.FAILED,
                                             terminate_codes__code=self.error_codes['OTHER'])
        self.assertFalse(order_from_db.exists())

    def test_failed_by_driver_with_comment(self):
        self.change_status_to(self.driver, self.order, OrderStatus.FAILED, terminate_comment='Test',
                              terminate_code=self.error_codes['OTHER'])
        order_from_db = Order.objects.filter(id=self.order.id, status=OrderStatus.FAILED,
                                             terminate_codes__code=self.error_codes['OTHER'])
        self.assertTrue(order_from_db.exists())

    def test_delivered_by_driver_without_comment(self):
        self.change_status_to(self.driver, self.order, OrderStatus.DELIVERED, resp_status=status.HTTP_400_BAD_REQUEST,
                              terminate_code=self.success_codes['OTHER'])
        order_from_db = Order.objects.filter(id=self.order.id, status=OrderStatus.DELIVERED,
                                             terminate_codes__code=self.success_codes['OTHER'])
        self.assertFalse(order_from_db.exists())

    def test_delivered_by_driver_with_comment(self):
        self.change_status_to(self.driver, self.order, OrderStatus.DELIVERED, terminate_comment='Test',
                              terminate_code=self.success_codes['OTHER'])
        order_from_db = Order.objects.filter(id=self.order.id, status=OrderStatus.DELIVERED,
                                             terminate_codes__code=self.success_codes['OTHER'])
        self.assertTrue(order_from_db.exists())

    def test_delivered_by_driver_without_change_status(self):
        self.change_status_to(self.driver, self.order, resp_status=status.HTTP_400_BAD_REQUEST,
                              terminate_code=self.success_codes['OTHER'])
        order_from_db = Order.objects.filter(id=self.order.id, status=OrderStatus.IN_PROGRESS,
                                             terminate_codes__code=self.success_codes['OTHER'])
        self.assertFalse(order_from_db.exists())


class TerminateOrderWithCodeAndConfirmationPhotosTestCase(InitializeTestCase):
    @classmethod
    def setUpTestData(cls):
        super(TerminateOrderWithCodeAndConfirmationPhotosTestCase, cls).setUpTestData()
        cls.merchant.enable_delivery_confirmation = True
        cls.merchant.save()

        f = BytesIO()
        image = Image.new("RGBA", size=(50, 50))
        image.save(f, "png")
        f.seek(0)
        image_encoded = b64encode(f.read())
        cls.photos = [{"image": image_encoded, }]

    def test_delivered_by_driver(self):
        self.change_status_to(self.driver, self.order, OrderStatus.DELIVERED, order_confirmation_photos=self.photos,
                              terminate_code=self.success_codes['STARTING'])
        order_from_db = Order.objects.filter(id=self.order.id, status=OrderStatus.DELIVERED,
                                             terminate_codes__code=self.success_codes['STARTING'])
        self.assertTrue(order_from_db.exists())
        self.assertEqual(order_from_db.first().order_confirmation_photos.count(), len(self.photos))

    def test_failed_by_driver(self):
        self.change_status_to(self.driver, self.order, OrderStatus.FAILED, order_confirmation_photos=self.photos,
                              terminate_code=self.error_codes['STARTING'])
        order_from_db = Order.objects.filter(id=self.order.id, status=OrderStatus.FAILED,
                                             terminate_codes__code=self.error_codes['STARTING'])
        self.assertTrue(order_from_db.exists())
        self.assertEqual(order_from_db.first().order_confirmation_photos.count(), len(self.photos))

    def test_failed_by_driver_api_v1(self):
        self.change_status_to(self.driver, self.order, OrderStatus.FAILED, version=1,
                              order_confirmation_photos=self.photos,
                              error_code=self.error_codes['STARTING'])
        order_from_db = Order.objects.filter(id=self.order.id, status=OrderStatus.FAILED,
                                             terminate_codes__code=self.error_codes['STARTING'])
        self.assertTrue(order_from_db.exists())
        self.assertEqual(order_from_db.first().order_confirmation_photos.count(), len(self.photos))


class TerminateOrderWithErrorCode_ApiV1TestCase(InitializeTestCase):
    def test_failed_by_driver(self):
        self.change_status_to(self.driver, self.order, OrderStatus.FAILED, version=1,
                              error_code=self.error_codes['STARTING'])
        order_from_db = Order.objects.filter(id=self.order.id, status=OrderStatus.FAILED,
                                             terminate_codes__code=self.error_codes['STARTING'])
        self.assertTrue(order_from_db.exists())

    def test_delivered_by_driver(self):
        resp = self.change_status_to(self.driver, self.order, OrderStatus.DELIVERED, version=1,
                                     resp_status=status.HTTP_400_BAD_REQUEST,
                                     error_code=self.success_codes['STARTING'])
        order_from_db = Order.objects.filter(id=self.order.id, status=OrderStatus.DELIVERED,
                                             terminate_codes__code=self.success_codes['STARTING'])
        self.assertFalse(order_from_db.exists())
        self.assertIn(ErrorCodeNumberSerializer.INVALID_TYPE_MSG, resp.data['errors']['error_code'][0])


class FailOrderWithNonExistedCode_ApiV1TestCase(InitializeTestCase):
    def test_failed_by_driver(self):
        self.change_status_to(self.driver, self.order, OrderStatus.FAILED, version=1,
                              resp_status=status.HTTP_400_BAD_REQUEST, error_code=504)
        order_from_db = Order.objects.filter(id=self.order.id, status=OrderStatus.FAILED, terminate_codes__code=504)
        self.assertFalse(order_from_db.exists())


class FailOrderWithOtherErrorCode_ApiV1TestCase(InitializeTestCase):
    def test_failed_by_driver_without_comment(self):
        self.change_status_to(self.driver, self.order, OrderStatus.FAILED, version=1,
                              resp_status=status.HTTP_400_BAD_REQUEST,
                              error_code=self.error_codes['OTHER'])
        order_from_db = Order.objects.filter(id=self.order.id, status=OrderStatus.FAILED,
                                             terminate_codes__code=self.error_codes['OTHER'])
        self.assertFalse(order_from_db.exists())

    def test_failed_by_driver_with_comment(self):
        self.change_status_to(self.driver, self.order, OrderStatus.FAILED, version=1, terminate_comment='Test',
                              error_code=self.error_codes['OTHER'])
        order_from_db = Order.objects.filter(id=self.order.id, status=OrderStatus.FAILED,
                                             terminate_codes__code=self.error_codes['OTHER'])
        self.assertTrue(order_from_db.exists())


class GetInfoAboutErrorCodeOfFailedOrder_ApiV1TestCase(InitializeTestCase):
    def setUp(self):
        super(GetInfoAboutErrorCodeOfFailedOrder_ApiV1TestCase, self).setUp()
        self.order.terminate_codes.add(self.merchant.terminate_codes.get(code=self.error_codes['OTHER']))
        self.order.terminate_comment = 'Test v1'
        self.order.save()

    def test_get_info_by_driver(self):
        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/v1/orders/{id}'.format(id=self.order.order_id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['error_comment'], 'Test v1')
        self.assertEqual(resp.data['error_code']['code'], self.error_codes['OTHER'])

    def test_get_info_by_manager(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/v1/orders/{id}'.format(id=self.order.order_id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['error_comment'], 'Test v1')
        self.assertEqual(resp.data['error_code']['code'], self.error_codes['OTHER'])


class TerminateCodesRepresentationTestCase(InitializeTestCase):
    def setUp(self):
        super(TerminateCodesRepresentationTestCase, self).setUp()
        self.order.terminate_codes.add(
            self.merchant.terminate_codes.get(code=self.error_codes['OTHER']),
            self.merchant.terminate_codes.get(code=self.error_codes['STARTING'])
        )
        self.order.terminate_comment = 'Test v1'
        self.order.save()

    def test_terminate_code_represenation(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/v1/orders/{id}'.format(id=self.order.order_id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsInstance(resp.data['terminate_code'], dict)
        self.assertEqual(resp.data['terminate_code']['code'], self.order.terminate_codes.first().code)

    def test_multiple_terminate_codes_represenation(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/v1/orders/{id}'.format(id=self.order.order_id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsInstance(resp.data['terminate_codes'], list)
        self.assertEqual(
            [x['code'] for x in resp.data['terminate_codes']],
            list(self.order.terminate_codes.values_list('code', flat=True))
        )


class TerminateOrderWithCodeAndEmailNotification(InitializeTestCase):

    @classmethod
    def setUpTestData(cls):
        super(TerminateOrderWithCodeAndEmailNotification, cls).setUpTestData()
        cls.email_message_recipient = 'manager@testemail.com'
        cls.merchant.templates.filter(template_type=MessageTemplateStatus.ADVANCED_COMPLETION).update(enabled=True)
        cls.advanced_completion_template = cls.merchant.templates.get(
            template_type=MessageTemplateStatus.ADVANCED_COMPLETION
        )
        cls.merchant.terminate_codes.filter(
            Q(code=settings.TERMINATE_CODES[ERROR]['STARTING'])
            | Q(code=settings.TERMINATE_CODES[SUCCESS]['STARTING'])
        ).update(email_notification_recipient=cls.email_message_recipient)

    def finish_order(self, order_status, terminate_code, terminate_comment, email_subject, send_email_mock):
        self.change_status_to(
            initiator=self.driver,
            order=self.order,
            order_status=order_status,
            terminate_code=terminate_code,
            terminate_comment=terminate_comment
        )
        self.assertTrue(send_email_mock.called)
        email_message_id = send_email_mock.call_args_list[0][0][0][-1]
        email_message = TemplateEmailMessage.objects.get(id=email_message_id)
        self.assertEqual(email_message.template_id, self.advanced_completion_template.id)
        self.assertEqual(email_message.email, self.email_message_recipient)
        self.assertEqual(email_message.subject, email_subject)
        self.assertTrue(str(self.order.order_id) in email_message.html_text)
        self.assertTrue(self.order.driver.full_name in email_message.html_text)
        self.assertTrue(terminate_comment in email_message.html_text)

    @patch('notification.celery_tasks.send_template_notification.apply_async')
    def test_order_failed(self, send_email_mock):
        terminate_comment = 'Order failed comment'
        email_subject = 'Termination Notification'
        self.finish_order(
            order_status=Order.FAILED,
            terminate_code=settings.TERMINATE_CODES[ERROR]['STARTING'],
            terminate_comment=terminate_comment,
            email_subject=email_subject,
            send_email_mock=send_email_mock
        )

    @patch('notification.celery_tasks.send_template_notification.apply_async')
    def test_order_failed(self, send_email_mock):
        terminate_comment = 'Order delivered comment'
        email_subject = 'Completion Notification'
        self.finish_order(
            order_status=Order.DELIVERED,
            terminate_code=settings.TERMINATE_CODES[SUCCESS]['STARTING'],
            terminate_comment=terminate_comment,
            email_subject=email_subject,
            send_email_mock=send_email_mock
        )
