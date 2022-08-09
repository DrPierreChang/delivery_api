from base64 import b64encode
from io import BytesIO

from rest_framework import status
from rest_framework.test import APITestCase

import mock
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


class MerchantAPIKeySuccessTestCase(APITestCase):

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
            AnswerFactory(question=question, text=True, is_correct=True)
            AnswerFactory(question=question, text=False)

        cls.start_of_day_checklist = StartOfDayChecklistFactory()
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

        cls.merchant.checklist = cls.checklist
        cls.merchant.sod_checklist = cls.start_of_day_checklist
        cls.merchant.webhook_url = 'https://example.com/'
        cls.merchant.save(update_fields=['checklist', 'sod_checklist'])

        cls.order = OrderFactory(
            manager=cls.manager, driver=cls.driver, status=Order.IN_PROGRESS, merchant=cls.merchant
        )

    @staticmethod
    def get_photos():
        f = BytesIO()
        image = Image.new("RGBA", size=(50, 50))
        image.save(f, "png")
        f.seek(0)
        b64image = b64encode(f.read())
        return [{"image": b64image}]

    def answer_checklist_with_comment_and_photos(self, checklist_id):
        resp = self.client.get('/api/v2/driver-checklist/{}/'.format(checklist_id))
        photos = self.get_photos()

        answers = []
        for question in resp.data['checklist']['questions']:
            answer_data = {
                'question': question['id'],
                'choice': not question['correct_answer'],
                'comment': 'comment for %s' % question['id'],
                'photos': photos,
            }
            answers.append(answer_data)

        resp = self.client.post('/api/v2/driver-checklist/{}/answers/'.format(checklist_id), {'answers': answers})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @mock.patch('webhooks.celery_tasks.send_external_event')
    def test_sod_checklist(self, send_external_event):
        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/v2/driver-checklist/start-of-day/')
        checklist_id = resp.data['id']
        self.answer_checklist_with_comment_and_photos(checklist_id)

        external_data = send_external_event.call_args.args[1]
        self.assertIsNotNone(external_data)

    @mock.patch('webhooks.celery_tasks.send_external_event')
    def test_order_checklist(self, send_external_event):
        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/v2/orders/{}/'.format(self.order.id))
        checklist_id = resp.data['driver_checklist']['id']
        self.answer_checklist_with_comment_and_photos(checklist_id)

        external_data = send_external_event.call_args.args[1]
        self.assertIsNotNone(external_data)
