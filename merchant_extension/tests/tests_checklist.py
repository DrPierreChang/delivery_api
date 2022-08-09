from base64 import b64encode
from datetime import datetime, timedelta
from io import BytesIO

from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

import mock
import pytz
from PIL import Image

from base.factories import DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from merchant_extension.factories import (
    AnswerFactory,
    ChecklistFactory,
    QuestionFactory,
    SectionFactory,
    StartOfDayChecklistFactory,
)
from merchant_extension.models import Question
from tasks.models import Order
from tasks.tests.factories import OrderFactory


def get_confirmation_data():
    f = BytesIO()
    image = Image.new("RGBA", size=(50, 50))
    image.save(f, "png")
    f.seek(0)
    signature = b64encode(f.read())
    photos = [{"image": signature, }]
    comment = "Test comment"

    return {"confirmation_signature": signature,
            "confirmation_photos": photos,
            "confirmation_comment": comment}


class ChecklistTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.checklist = ChecklistFactory()
        cls.start_of_day_checklist = StartOfDayChecklistFactory()
        cls.checklist_section = SectionFactory(checklist=cls.checklist)
        cls.questions = QuestionFactory.create_batch(
            section=cls.checklist_section,
            category=Question.DICHOTOMOUS,
            size=2
        )
        for question in cls.questions:
            AnswerFactory(question=question, text=True, is_correct=True)
            AnswerFactory(question=question, text=False)
        cls.start_of_day_checklist_section = SectionFactory(checklist=cls.start_of_day_checklist)
        cls.sod_questions = QuestionFactory.create_batch(
            section=cls.start_of_day_checklist_section,
            category=Question.DICHOTOMOUS,
            size=2
        )
        for sod_question in cls.sod_questions:
            AnswerFactory(question=sod_question, text=True, is_correct=True)
            AnswerFactory(question=sod_question, text=False)
        cls.merchant = MerchantFactory(enable_delivery_pre_confirmation=True)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)
        cls.minsk_merchant = MerchantFactory(sod_checklist=cls.start_of_day_checklist,
                                             timezone=pytz.timezone('Europe/Minsk'))
        cls.minsk_driver = DriverFactory(merchant=cls.minsk_merchant, work_status=WorkStatus.WORKING)
        cls.merchant.checklist = cls.checklist
        cls.merchant.sod_checklist = cls.start_of_day_checklist
        cls.merchant.save(update_fields=['checklist', 'sod_checklist'])
        cls.order = OrderFactory(
            manager=cls.manager, driver=cls.driver, status=Order.IN_PROGRESS, merchant=cls.merchant
        )
        cls.not_assigned_order = OrderFactory(
            manager=cls.manager, driver=None, status=Order.NOT_ASSIGNED, merchant=cls.merchant,
            deliver_before=(timezone.now() + timedelta(days=1))
        )

    def setUp(self):
        self.merchant.checklist = self.checklist
        self.merchant.sod_checklist = self.start_of_day_checklist
        self.merchant.save(update_fields=['checklist', 'sod_checklist'])
        self.client.force_authenticate(self.driver)

    def test_answer_job_checklist(self):
        resp = self.client.get('/api/v2/orders/{}/'.format(self.order.id))
        self.assertFalse(resp.data['driver_checklist']['checklist_passed'])
        self.answer_checklist(resp.data['driver_checklist']['id'])

    def test_fetch_checklist_from_not_assigned_job(self):
        self.merchant.in_app_jobs_assignment = True
        self.merchant.save(update_fields=['in_app_jobs_assignment'])
        resp = self.client.get('/api/v2/orders/?status=not_assigned')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)
        checklist = resp.data['results'][0]['driver_checklist']
        self.assertIsNotNone(checklist)
        resp = self.client.get('/api/v2/driver-checklist/{}/'.format(checklist['id']))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.post('/api/v2/driver-checklist/{}/answers'.format(checklist['id']))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.merchant.in_app_jobs_assignment = False
        self.merchant.save(update_fields=['in_app_jobs_assignment'])

    @mock.patch('merchant_extension.celery_tasks.handle_wrong_answers_sod_checklist.delay')
    def test_wrong_answer_job_checklist(self, patch_task):
        resp = self.client.get('/api/v2/orders/{}/'.format(self.order.id))
        self.assertFalse(resp.data['driver_checklist']['checklist_passed'])
        self.answer_checklist(resp.data['driver_checklist']['id'], should_be_correct=False)
        self.assertFalse(patch_task.called)

    def answer_checklist(self, checklist_id, should_be_correct=True):
        resp = self.client.get('/api/v2/driver-checklist/{}/'.format(checklist_id))
        answers = []
        for question in resp.data['checklist']['questions']:
            choice = question['correct_answer']
            answers.append({'question': question['id'], 'choice': choice if should_be_correct else not choice})
        resp = self.client.post('/api/v2/driver-checklist/{}/answers/'.format(checklist_id), {'answers': answers})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['checklist_passed'])
        self.assertEqual(resp.data['is_correct'], should_be_correct)

    def test_confirm_checklist(self):
        resp = self.client.get('/api/v2/orders/{}/'.format(self.order.id))
        self.assertFalse(resp.data['driver_checklist']['checklist_passed'])
        checklist_id = resp.data['driver_checklist']['id']
        self.answer_checklist(checklist_id)
        confirmation_data = get_confirmation_data()
        resp = self.client.patch('/api/v2/driver-checklist/{}/confirmation/'.format(checklist_id), confirmation_data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['confirmation_comment'], confirmation_data['confirmation_comment'])
        self.assertIsNotNone(resp.data['confirmation_signature'])
        self.assertEqual(len(resp.data['confirmation_photos']), 1)
        self.assertTrue(resp.data['checklist_confirmed'])

    def test_preconfirmation_and_checklist(self):
        resp = self.client.get('/api/v2/orders/{}/'.format(self.order.id))
        self.assertFalse(resp.data['driver_checklist']['checklist_passed'])
        checklist_id = resp.data['driver_checklist']['id']
        self.answer_checklist(checklist_id)

        pre_confirmation_data = get_confirmation_data()
        pre_confirmation_data = {('pre_%s' % k): v for k, v in pre_confirmation_data.items()}
        resp = self.client.put('/api/v2/orders/{}/confirmation/'.format(self.order.id), pre_confirmation_data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.get('/api/v2/driver-checklist/{}/'.format(checklist_id))
        self.assertEqual(resp.data['confirmation_comment'], pre_confirmation_data['pre_confirmation_comment'])
        self.assertIsNotNone(resp.data['confirmation_signature'])
        self.assertEqual(len(resp.data['confirmation_photos']), 1)
        self.assertTrue(resp.data['checklist_confirmed'])

    def test_sod_checklist_disabled(self):
        self.merchant.sod_checklist = None
        self.merchant.save(update_fields=['sod_checklist'])
        resp = self.client.get('/api/v2/users/me/')
        self.assertFalse(resp.data['merchant']['sod_checklist_enabled'])

    def test_get_start_of_day_checklist_daily(self):
        hours_settings = [
            {'utc_hour_request': 10, 'is_new_for_minsk': True, 'is_new_for_melbourne': True},
            {'utc_hour_request': 20, 'is_new_for_minsk': False, 'is_new_for_melbourne': True},
            {'utc_hour_request': 23, 'is_new_for_minsk': True, 'is_new_for_melbourne': False},
        ]
        prev_minsk_checklist_id, prev_melbourne_checklist_id = None, None
        with mock.patch('django.utils.timezone.now') as time_mock:
            for sod_checklist_setting in hours_settings:
                utc_time = pytz.UTC.localize(datetime(2018, 12, 1, sod_checklist_setting['utc_hour_request']))
                time_mock.return_value = utc_time

                self.client.force_authenticate(self.driver)
                resp = self.client.get('/api/v2/driver-checklist/start-of-day/')
                assert_func = self.assertNotEqual if sod_checklist_setting['is_new_for_melbourne'] else self.assertEqual
                assert_func(prev_melbourne_checklist_id, resp.data['id'])
                prev_melbourne_checklist_id = resp.data['id']

                self.client.force_authenticate(self.minsk_driver)
                resp = self.client.get('/api/v2/driver-checklist/start-of-day/')
                assert_func = self.assertNotEqual if sod_checklist_setting['is_new_for_minsk'] else self.assertEqual
                assert_func(prev_minsk_checklist_id, resp.data['id'])
                prev_minsk_checklist_id = resp.data['id']

    def test_answer_start_of_day_checklist(self):
        resp = self.client.get('/api/v2/users/me/')
        self.assertTrue(resp.data['merchant']['sod_checklist_enabled'])
        resp = self.client.get('/api/v2/driver-checklist/start-of-day/')
        checklist_id = resp.data['id']
        self.answer_checklist(checklist_id)

    @mock.patch('merchant_extension.celery_tasks.handle_wrong_answers_sod_checklist.delay')
    def test_start_of_day_checklist_with_comment_and_photos(self, patch_task):
        resp = self.client.get('/api/v2/users/me/')
        self.assertTrue(resp.data['merchant']['sod_checklist_enabled'])
        resp = self.client.get('/api/v2/driver-checklist/start-of-day/')
        checklist_id = resp.data['id']
        self.answer_checklist_with_comment_and_photos(checklist_id)
        self.assertTrue(patch_task.called)

    def answer_checklist_with_comment_and_photos(self, checklist_id):
        resp = self.client.get('/api/v2/driver-checklist/{}/'.format(checklist_id))
        answers = []
        for question in resp.data['checklist']['questions']:
            answer_data = {
                'question': question['id'],
                'choice': not question['correct_answer'],
                'comment': 'comment for %s' % question['id'],
                'photos': get_confirmation_data()['confirmation_photos'],
            }
            answers.append(answer_data)
        resp = self.client.post('/api/v2/driver-checklist/{}/answers/'.format(checklist_id), {'answers': answers})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        for answer in resp.data['answers']:
            self.assertEqual(answer['comment'], 'comment for %s' % answer['question'])
            self.assertEqual(len(answer['photos']), 1)

        self.assertTrue(resp.data['checklist_passed'])
        self.assertFalse(resp.data['is_correct'])

    def test_get_checklist_by_manager(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/v2/orders/{}/'.format(self.order.id))
        checklist_id = resp.data['driver_checklist']
        resp = self.client.get('/api/v2/driver-checklist/{}/'.format(checklist_id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_get_drivers_list_with_sod_checklist_flag(self):
        self.client.force_authenticate(self.manager)
        drivers_resp = self.client.get('/api/v2/drivers/?id={}'.format(self.driver.id))
        driver = drivers_resp.data['results'][0]
        self.assertFalse(driver['sod_checklist_failed'])

        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/v2/driver-checklist/start-of-day/')
        checklist_id = resp.data['id']
        self.answer_checklist_with_comment_and_photos(checklist_id)

        self.client.force_authenticate(self.manager)
        drivers_resp = self.client.get('/api/v2/drivers/?id={}'.format(self.driver.id))
        driver = drivers_resp.data['results'][0]
        self.assertTrue(driver['sod_checklist_failed'])

    def test_get_start_of_day_checklist_by_manager(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/v2/driver-checklist/start-of-day/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        resp = self.client.get('/api/v2/driver-checklist/start-of-day/?driver={}'.format(self.driver.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
