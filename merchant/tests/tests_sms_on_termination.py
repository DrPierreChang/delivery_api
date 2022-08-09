from rest_framework import status
from rest_framework.test import APITestCase

from mock import mock

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import MerchantFactory
from notification.models import MerchantMessageTemplate
from tasks.models import OrderStatus
from tasks.tests.factories import CustomerFactory


class NotifyOnTerminationTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        super(NotifyOnTerminationTestCase, cls).setUpTestData()

        cls.merchant = MerchantFactory(sms_sender='TestSndr')
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant)

    def setUp(self):
        from tasks.tests.factories import OrderFactory
        self.order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.IN_PROGRESS,
            driver=self.driver,
            sub_branding=None,
            customer=CustomerFactory(merchant=self.merchant, phone="+61491570110", email="fake@mail.co")
        )
        self.client.force_authenticate(self.manager)

    def change_status_to(self, order_status):
        order_resp = self.client.patch('/api/orders/%s/' % self.order.order_id, {
            'status': order_status,
        })
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(order_resp.data['status'], order_status)

    def check_sms_and_email(self, sms_enable, job_termination_sms_enable, sms_sended, email_sended):
        self.merchant.sms_enable = sms_enable
        self.merchant.templates.filter(template_type=MerchantMessageTemplate.CUSTOMER_JOB_TERMINATED)\
            .update(enabled=job_termination_sms_enable)
        self.merchant.save()
        calls_number = int(sms_sended) + int(email_sended)
        with mock.patch('notification.celery_tasks.send_template_notification.apply_async') as mock_notification:
            self.change_status_to(OrderStatus.FAILED)
            self.assertEqual(calls_number, mock_notification.call_count)

    def test_sms_not_enabled_and_job_termination_sms_not_enabled(self):
        self.check_sms_and_email(sms_enable=False,
                                 job_termination_sms_enable=False,
                                 sms_sended=False,
                                 email_sended=False)

    def test_sms_not_enabled_and_job_termination_sms_enabled(self):
        self.check_sms_and_email(sms_enable=False,
                                 job_termination_sms_enable=True,
                                 sms_sended=False,
                                 email_sended=True)

    def test_sms_enabled_and_job_termination_sms_not_enabled(self):
        self.check_sms_and_email(sms_enable=True,
                                 job_termination_sms_enable=False,
                                 sms_sended=False,
                                 email_sended=False)

    def test_sms_enabled_and_job_termination_sms_enabled(self):
        self.check_sms_and_email(sms_enable=True,
                                 job_termination_sms_enable=True,
                                 sms_sended=True,
                                 email_sended=True)
