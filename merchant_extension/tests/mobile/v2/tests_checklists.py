import io
from datetime import datetime

from rest_framework import status
from rest_framework.test import APITestCase

import mock
import pytz
from PIL import Image

from base.factories import DriverFactory, DriverLocationFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from merchant_extension.factories import (
    AnswerFactory,
    ChecklistFactory,
    EndOfDayChecklistFactory,
    QuestionFactory,
    SectionFactory,
    StartOfDayChecklistFactory,
)
from merchant_extension.models import Question
from tasks.models import Order
from tasks.tests.factories import OrderFactory


class MobileChecklistTestCase(APITestCase):

    def _generate_image(self):
        file = io.BytesIO()
        image = Image.new('RGBA', size=(100, 100), color=(155, 0, 0))
        image.save(file, 'png')
        file.name = 'test.png'
        file.seek(0)
        return file

    def answer_checklist(self, checklist_id, choice=True, use_image=True, resp_status=status.HTTP_201_CREATED):
        resp = self.client.get(f'/api/mobile/checklists/v2/{checklist_id}/')

        for question in resp.data['checklist']['questions']:
            answer = {
                'question': question['id'],
                'choice': choice,
                'comment': 'comment for %s' % question['id'],
            }
            if use_image:
                answer['answer_photos'] = self._generate_image()

            resp = self.client.post(
                f'/api/mobile/checklists/v2/{checklist_id}/answer/', data=answer, format='multipart',
            )
            self.assertEqual(resp.status_code, resp_status)

        if resp_status == status.HTTP_201_CREATED:
            resp = self.client.put(f'/api/mobile/checklists/v2/{checklist_id}/confirm/')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @classmethod
    def setUpTestData(cls):
        cls.checklist = ChecklistFactory()
        cls.checklist_section = SectionFactory(checklist=cls.checklist)
        cls.questions = QuestionFactory.create_batch(
            section=cls.checklist_section,
            category=Question.DICHOTOMOUS,
            size=2
        )
        for question in cls.questions:
            AnswerFactory(question=question, text=True, is_correct=True, photos_required=True)
            AnswerFactory(question=question, text=False)

        cls.sod_checklist = StartOfDayChecklistFactory()
        cls.sod_checklist_section = SectionFactory(checklist=cls.sod_checklist)
        cls.sod_questions = QuestionFactory.create_batch(
            section=cls.sod_checklist_section,
            category=Question.DICHOTOMOUS,
            size=2
        )
        for sod_question in cls.sod_questions:
            AnswerFactory(question=sod_question, text=True, is_correct=True, photos_required=True)
            AnswerFactory(question=sod_question, text=False)

        cls.eod_checklist = EndOfDayChecklistFactory()
        cls.eod_checklist_section = SectionFactory(checklist=cls.eod_checklist)
        cls.eod_questions = QuestionFactory.create_batch(
            section=cls.eod_checklist_section,
            category=Question.DICHOTOMOUS,
            size=2
        )
        for eod_question in cls.eod_questions:
            AnswerFactory(question=eod_question, text=True, is_correct=True, photos_required=True)
            AnswerFactory(question=eod_question, text=False)

        cls.merchant = MerchantFactory(enable_delivery_pre_confirmation=True)
        cls.merchant.checklist = cls.checklist
        cls.merchant.sod_checklist = cls.sod_checklist
        cls.merchant.sod_checklist_email = 'http://www.example.com/'
        cls.merchant.eod_checklist = cls.eod_checklist
        cls.merchant.eod_checklist_email = 'http://www.example.com/'
        cls.merchant.save(
            update_fields=['checklist', 'sod_checklist', 'sod_checklist_email', 'eod_checklist', 'eod_checklist_email']
        )

        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)
        cls.order = OrderFactory(
            manager=cls.manager, driver=cls.driver, status=Order.IN_PROGRESS, merchant=cls.merchant
        )

        cls.driver.last_location = DriverLocationFactory(member=cls.driver)
        cls.driver.save()

        cls.minsk_merchant = MerchantFactory(sod_checklist=cls.sod_checklist, timezone=pytz.timezone('Europe/Minsk'))
        cls.minsk_driver = DriverFactory(merchant=cls.minsk_merchant, work_status=WorkStatus.WORKING)

    def setUp(self):
        self.client.force_authenticate(self.driver)

    def test_job_checklist_true_with_photos(self):
        resp = self.client.get(f'/api/mobile/orders/v1/{self.order.id}/')
        checklist_id = resp.data['checklist']['id']
        self.answer_checklist(checklist_id, choice=True, use_image=True, resp_status=status.HTTP_201_CREATED)

    def test_job_checklist_true_without_photos(self):
        resp = self.client.get(f'/api/mobile/orders/v1/{self.order.id}/')
        checklist_id = resp.data['checklist']['id']
        self.answer_checklist(checklist_id, choice=True, use_image=False, resp_status=status.HTTP_400_BAD_REQUEST)

    def test_job_checklist_false_with_photos(self):
        resp = self.client.get(f'/api/mobile/orders/v1/{self.order.id}/')
        checklist_id = resp.data['checklist']['id']
        self.answer_checklist(checklist_id, choice=False, use_image=True, resp_status=status.HTTP_201_CREATED)

    def test_job_checklist_false_without_photos(self):
        resp = self.client.get(f'/api/mobile/orders/v1/{self.order.id}/')
        checklist_id = resp.data['checklist']['id']
        self.answer_checklist(checklist_id, choice=False, use_image=False, resp_status=status.HTTP_201_CREATED)

    @mock.patch('webhooks.celery_tasks.send_external_event')
    def test_external_event_job_checklist(self, external_event):
        resp = self.client.get('/api/mobile/orders/v1/{}/'.format(self.order.id))
        self.assertFalse(resp.data['checklist']['checklist_passed'])
        self.answer_checklist(resp.data['checklist']['id'])
        self.assertTrue(external_event.called)

    @mock.patch('webhooks.celery_tasks.send_external_event')
    def test_external_event_sod_checklist(self, external_event):
        resp = self.client.get('/api/mobile/checklists/v2/start-of-day/')
        self.answer_checklist(resp.data['id'])
        self.assertTrue(external_event.called)

    @mock.patch('webhooks.celery_tasks.send_external_event')
    def test_external_event_eod_checklist(self, external_event):
        resp = self.client.get('/api/mobile/checklists/v2/end-of-day/')
        self.answer_checklist(resp.data['id'])
        self.assertTrue(external_event.called)

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
                resp = self.client.get('/api/mobile/checklists/v2/start-of-day/')
                assert_func = self.assertNotEqual if sod_checklist_setting['is_new_for_melbourne'] else self.assertEqual
                assert_func(prev_melbourne_checklist_id, resp.data['id'])
                prev_melbourne_checklist_id = resp.data['id']

                self.client.force_authenticate(self.minsk_driver)
                resp = self.client.get('/api/mobile/checklists/v2/start-of-day/')
                assert_func = self.assertNotEqual if sod_checklist_setting['is_new_for_minsk'] else self.assertEqual
                assert_func(prev_minsk_checklist_id, resp.data['id'])
                prev_minsk_checklist_id = resp.data['id']

    def test_answer_start_of_day_checklist(self):
        resp = self.client.get('/api/mobile/merchant/v1/')
        self.assertTrue(resp.data['enable_sod_checklist'])
        resp = self.client.get('/api/mobile/checklists/v2/start-of-day/')
        checklist_id = resp.data['id']
        self.answer_checklist(checklist_id)

    def test_answer_end_of_day_checklist(self):
        resp = self.client.get('/api/mobile/merchant/v1/')
        self.assertTrue(resp.data['enable_eod_checklist'])
        resp = self.client.get('/api/mobile/checklists/v2/end-of-day/')
        checklist_id = resp.data['id']
        self.answer_checklist(checklist_id)

    @mock.patch('merchant_extension.celery_tasks.handle_wrong_answers_sod_checklist.delay')
    def test_start_of_day_checklist_with_wrong_answer(self, patch_task):
        resp = self.client.get('/api/mobile/checklists/v2/start-of-day/')
        checklist_id = resp.data['id']
        self.answer_checklist(checklist_id, choice=False)
        self.assertTrue(patch_task.called)

    @mock.patch('merchant_extension.celery_tasks.handle_wrong_answers_eod_checklist.delay')
    def test_end_of_day_checklist_with_wrong_answer(self, patch_task):
        resp = self.client.get('/api/mobile/checklists/v2/end-of-day/')
        checklist_id = resp.data['id']
        self.answer_checklist(checklist_id, choice=False)
        self.assertTrue(patch_task.called)
