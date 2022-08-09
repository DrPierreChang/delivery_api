from django.conf import settings
from django.test.utils import override_settings

from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import ManagerFactory
from merchant.factories import MerchantFactory
from merchant.models import Merchant
from tasks.models.terminate_code import SUCCESS_CODES_DISABLED_MSG, TerminateCode

TEST_TERMINATE_CODES = {
    'error': {
        'STARTING': 501,
        'OTHER': 505,
        'MAX_COUNT': 5,
        'DEFAULT_CODES': (
            {'code': 501, 'name': 'Test error #1'},
            {'code': 502, 'name': 'Test error #2'},
            {'code': 503, 'name': 'Test error #3'},
            {'code': 505, 'name': 'Other', 'is_comment_necessary': True}
        )
    },
    'success': {
        'STARTING': 201,
        'OTHER': 205,
        'MAX_COUNT': 5,
        'DEFAULT_CODES': (
            {'code': 201, 'name': 'Test success #1'},
            {'code': 202, 'name': 'Test success #2'},
            {'code': 203, 'name': 'Test success #3'},
            {'code': 205, 'name': 'Other', 'is_comment_necessary': True}
        )
    }
}


class TerminateCodesAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        super(TerminateCodesAPITestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory(advanced_completion=Merchant.ADVANCED_COMPLETION_DISABLED)
        cls.manager = ManagerFactory(merchant=cls.merchant)

    def setUp(self):
        self.client.force_authenticate(self.manager)

    def test_merchant_have_error_codes(self):
        resp = self.client.get('/api/terminate-codes/', {'type': TerminateCode.TYPE_ERROR})
        self.assertEqual(resp.json().get('count'), len(settings.TERMINATE_CODES['error']['DEFAULT_CODES']))

    def test_merchant_have_success_codes(self):
        resp = self.client.get('/api/terminate-codes/', {'type': TerminateCode.TYPE_SUCCESS})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(SUCCESS_CODES_DISABLED_MSG, resp.json().get('errors'))

        merchant_with_success_codes = MerchantFactory(advanced_completion=Merchant.ADVANCED_COMPLETION_OPTIONAL)
        manager = ManagerFactory(merchant=merchant_with_success_codes)
        self.client.force_authenticate(manager)
        resp = self.client.get('/api/terminate-codes/', {'type': TerminateCode.TYPE_SUCCESS})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json().get('count'), len(settings.TERMINATE_CODES['success']['DEFAULT_CODES']))

    @override_settings(TERMINATE_CODES=TEST_TERMINATE_CODES)
    def test_create_error_codes(self):
        resp = self.client.post('/api/terminate-codes/', {'name': 'Error code', 'type': TerminateCode.TYPE_ERROR})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(self.merchant.terminate_codes.filter(type=TerminateCode.TYPE_ERROR,
                                                             name='Error code', code=504).exists())
        resp = self.client.post('/api/terminate-codes/', {'name': 'One more error code'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(self.merchant.terminate_codes.filter(name='One more error code').exists())

    @override_settings(TERMINATE_CODES=TEST_TERMINATE_CODES)
    def test_create_success_codes(self):
        resp = self.client.post('/api/terminate-codes/', {'name': 'Success code', 'type': TerminateCode.TYPE_SUCCESS})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(SUCCESS_CODES_DISABLED_MSG, resp.json().get('errors'))

        merchant_with_success_codes = MerchantFactory(advanced_completion=Merchant.ADVANCED_COMPLETION_OPTIONAL)
        manager = ManagerFactory(merchant=merchant_with_success_codes)
        self.client.force_authenticate(manager)
        resp = self.client.post('/api/terminate-codes/', {'name': 'Success code', 'type': TerminateCode.TYPE_SUCCESS})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(merchant_with_success_codes.terminate_codes.filter(type=TerminateCode.TYPE_SUCCESS,
                                                                           name='Success code', code=204).exists())
        resp = self.client.post('/api/terminate-codes/', {'name': 'One more success code'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(merchant_with_success_codes.terminate_codes.filter(name='One more success code').exists())

    def test_code_deleting(self):
        error_code = self.merchant.terminate_codes.get(code=501)
        resp = self.client.delete('/api/terminate-codes/%s/' % error_code.id)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        error_other_code = self.merchant.terminate_codes.get(code=settings.TERMINATE_CODES['error']['OTHER'])
        resp = self.client.delete('/api/terminate-codes/%s/' % error_other_code.id)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_code_name_change(self):
        code = self.merchant.terminate_codes.get(code=502)
        resp = self.client.patch('/api/terminate-codes/%s/' % code.id, {'name': 'new name'})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(self.merchant.terminate_codes.filter(name='new name', code=502).exists())

        other_code = self.merchant.terminate_codes.get(code=settings.TERMINATE_CODES['error']['OTHER'])
        resp = self.client.patch('/api/terminate-codes/%s/' % other_code.id, {'name': 'test name'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
