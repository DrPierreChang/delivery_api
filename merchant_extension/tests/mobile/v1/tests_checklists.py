import io

from rest_framework import status
from rest_framework.test import APITestCase

from PIL import Image

from base.factories import DriverFactory, DriverLocationFactory, ManagerFactory
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


class MobileChecklistTestCase(APITestCase):

    def _generate_image(self):
        file = io.BytesIO()
        image = Image.new('RGBA', size=(100, 100), color=(155, 0, 0))
        image.save(file, 'png')
        file.name = 'test.png'
        file.seek(0)
        return file

    def answer_checklist(self, checklist_id, choice=True, use_image=True, resp_status=status.HTTP_201_CREATED):
        resp = self.client.get(f'/api/mobile/checklists/v1/{checklist_id}/')

        for question in resp.data['checklist']['questions']:
            answer = {
                'question': question['id'],
                'choice': choice,
                'comment': 'comment for %s' % question['id'],
            }
            if use_image:
                answer['answer_photos'] = self._generate_image()

            resp = self.client.post(
                f'/api/mobile/checklists/v1/{checklist_id}/answer/', data=answer, format='multipart',
            )
            self.assertEqual(resp.status_code, resp_status)

        if resp_status == status.HTTP_201_CREATED:
            resp = self.client.put(f'/api/mobile/checklists/v1/{checklist_id}/confirm/')
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

        cls.merchant = MerchantFactory(enable_delivery_pre_confirmation=True)
        cls.merchant.checklist = cls.checklist
        cls.merchant.sod_checklist = cls.sod_checklist
        cls.merchant.save(update_fields=['checklist', 'sod_checklist'])

        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant, work_status=WorkStatus.WORKING)
        cls.order = OrderFactory(
            manager=cls.manager, driver=cls.driver, status=Order.IN_PROGRESS, merchant=cls.merchant
        )

        cls.driver.last_location = DriverLocationFactory(member=cls.driver)
        cls.driver.save()

    def setUp(self):
        self.client.force_authenticate(self.driver)

    def test_job_checklist_true_with_photos(self):
        resp = self.client.get(f'/api/mobile/orders/v1/{self.order.id}/')
        checklist_id = resp.data['checklist']['id']
        self.answer_checklist(checklist_id, choice=True, use_image=True, resp_status=status.HTTP_201_CREATED)

    def test_job_checklist_true_without_photos(self):
        # Although the photos_required option is enabled in this case, this version of the api does not use it.
        resp = self.client.get(f'/api/mobile/orders/v1/{self.order.id}/')
        checklist_id = resp.data['checklist']['id']
        self.answer_checklist(checklist_id, choice=True, use_image=False, resp_status=status.HTTP_201_CREATED)

    def test_job_checklist_false_with_photos(self):
        resp = self.client.get(f'/api/mobile/orders/v1/{self.order.id}/')
        checklist_id = resp.data['checklist']['id']
        self.answer_checklist(checklist_id, choice=False, use_image=True, resp_status=status.HTTP_201_CREATED)

    def test_job_checklist_false_without_photos(self):
        resp = self.client.get(f'/api/mobile/orders/v1/{self.order.id}/')
        checklist_id = resp.data['checklist']['id']
        self.answer_checklist(checklist_id, choice=False, use_image=False, resp_status=status.HTTP_201_CREATED)
