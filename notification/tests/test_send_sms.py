# coding=utf-8
from django.test import TestCase

from notification.models import MerchantMessageTemplate, TemplateSMSMessage


class SendSMSTestCase(TestCase):

    def setUp(self):
        self.test_template = MerchantMessageTemplate.objects.get(template_type=MerchantMessageTemplate.ANOTHER)

    def test_send_non_ascii_letters(self):
        msg = TemplateSMSMessage(text='Тест', template=self.test_template, phone='0000000000')
        msg.save()

        msg.send()
        msg.refresh_from_db()
        self.assertTrue(msg.is_sent)

    def test_send_ascii_letters(self):
        msg = TemplateSMSMessage(text='Test', template=self.test_template, phone='0000000000')
        msg.save()

        msg.send()
        msg.refresh_from_db()
        self.assertTrue(msg.is_sent)
