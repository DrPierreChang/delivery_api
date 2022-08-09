# coding=utf-8
from django.test import testcases

from notification.utils import get_sms_info


class SmsSegmentsCountTestCase(testcases.TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.EN_SHORT_MSG = ('Test msg', 1)
        cls.EN_LONG_MSG = ('Test msg' + 'q'*160, 2)
        cls.RU_SHORT_MSG = ('Тест', 1)
        cls.RU_LONG_MSG = ('Тест' + ' ' * 160, 3)
        cls.ZH_SHORT_MSG = ('測試', 1)
        cls.ZH_LONG_MSG = ('測試' + ' ' * 160, 3)
        cls.AR_SHORT_MSG = ('اختبار', 1)
        cls.AR_LONG_MSG = ('اختبار' + ' ' * 160, 3)

    def test_short_en_message(self):
        test_data = self.EN_SHORT_MSG
        sms_info = get_sms_info(test_data[0])
        self.assertEqual(sms_info['segment_count'], test_data[1])

    def test_long_en_message(self):
        test_data = self.EN_SHORT_MSG
        sms_info = get_sms_info(test_data[0])
        self.assertEqual(sms_info['segment_count'], test_data[1])

    def test_ru_short_message(self):
        test_data = self.RU_SHORT_MSG
        sms_info = get_sms_info(test_data[0])
        self.assertEqual(sms_info['segment_count'], test_data[1])

    def test_ru_long_message(self):
        test_data = self.RU_LONG_MSG
        sms_info = get_sms_info(test_data[0])
        self.assertEqual(sms_info['segment_count'], test_data[1])

    def test_zh_short_message(self):
        test_data = self.ZH_SHORT_MSG
        sms_info = get_sms_info(test_data[0])
        self.assertEqual(sms_info['segment_count'], test_data[1])

    def test_zh_long_message(self):
        test_data = self.ZH_LONG_MSG
        sms_info = get_sms_info(test_data[0])
        self.assertEqual(sms_info['segment_count'], test_data[1])

    def test_ar_short_message(self):
        test_data = self.AR_SHORT_MSG
        sms_info = get_sms_info(test_data[0])
        self.assertEqual(sms_info['segment_count'], test_data[1])

    def test_ar_long_message(self):
        test_data = self.AR_LONG_MSG
        sms_info = get_sms_info(test_data[0])
        self.assertEqual(sms_info['segment_count'], test_data[1])
