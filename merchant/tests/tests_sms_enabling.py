from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import ManagerFactory
from merchant.factories import MerchantFactory
from notification.models import MerchantMessageTemplate

SMS_ENABLED_REQUIRED_MSG = 'SMS notifications should be enabled.'


class MerchantSMSEnablingSettingsTestCase(APITestCase):
    def setUp(self):
        self.merchant = MerchantFactory(sms_enable=False)
        self.manager = ManagerFactory(merchant=self.merchant)
        self.client.force_authenticate(self.manager)

    def update_merchant(self, sms_enable, job_termination_sms_enable, status_code=status.HTTP_200_OK):
        self.merchant.sms_enable = sms_enable
        self.merchant.save()

        termination_template = self.merchant.templates.get(template_type=MerchantMessageTemplate.CUSTOMER_JOB_TERMINATED)

        request_data = [{
            'enabled': job_termination_sms_enable,
            'id': termination_template.id
        }]
        resp = self.client.patch('/api/message-templates/', data=request_data)
        self.assertEqual(resp.status_code, status_code)
        if status_code != status.HTTP_200_OK:
            self.assertIn(SMS_ENABLED_REQUIRED_MSG, resp.json()['errors'][0]['enabled'])

    def test_sms_not_enabled_and_job_termination_sms_not_enabled(self):
        self.update_merchant(sms_enable=False,
                             job_termination_sms_enable=False)

    def test_sms_not_enabled_and_job_termination_sms_enabled(self):
        self.update_merchant(sms_enable=False,
                             job_termination_sms_enable=True,
                             status_code=status.HTTP_400_BAD_REQUEST)

    def test_sms_enabled_and_job_termination_sms_not_enabled(self):
        self.update_merchant(sms_enable=True,
                             job_termination_sms_enable=False)

    def test_sms_enabled_and_job_termination_sms_enabled(self):
        self.update_merchant(sms_enable=True,
                             job_termination_sms_enable=True)
