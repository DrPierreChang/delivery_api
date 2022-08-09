from datetime import timedelta

from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory, SubBrandingFactory
from merchant_extension.factories import (
    AnswerFactory,
    QuestionFactory,
    SectionFactory,
    SurveyFactory,
    SurveyResultFactory,
)
from tasks.models import Order
from tasks.tests.factories import CustomerFactory, OrderFactory


class CustomerSurveyTestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.customer_survey = SurveyFactory()
        cls.subbrand_customer_survey = SurveyFactory()
        cls.survey_section = SectionFactory(checklist=cls.customer_survey)
        cls.survey_questions = QuestionFactory.create_batch(
            section=cls.survey_section,
            size=2
        )
        for question in cls.survey_questions:
            AnswerFactory(question=question, text=True, is_correct=True)
            AnswerFactory(question=question, text=False)

        cls.merchant = MerchantFactory(
            customer_survey=cls.customer_survey
        )
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(work_status=WorkStatus.WORKING, merchant=cls.merchant)
        cls.customer = CustomerFactory(merchant=cls.merchant)
        cls.customer_uidb64 = urlsafe_base64_encode(force_bytes(cls.customer.pk))
        cls.order = OrderFactory(
            merchant=cls.merchant,
            manager=cls.manager,
            driver=cls.driver,
            status=Order.IN_PROGRESS,
            customer=cls.customer,
            sub_branding=None
        )
        cls.sub_brand = SubBrandingFactory(
            merchant=cls.merchant
        )

        cls.order_with_subbrand_survey = OrderFactory(
            merchant=cls.merchant,
            manager=cls.manager,
            driver=cls.driver,
            status=Order.IN_PROGRESS,
            customer=cls.customer,
            sub_branding=cls.sub_brand
        )
        cls.base_customer_url = '/api/customers/{uid}/orders/{order_token}/{path}'

    def test_can_not_create_customer_survey(self):
        self.merchant.customer_survey = None
        self.merchant.save()

        url = self.base_customer_url.format(
            uid=self.customer_uidb64,
            order_token=self.order.order_token,
            path='surveys'
        )
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.merchant.customer_survey = self.customer_survey
        self.merchant.save()

    def test_create_customer_survey(self):
        url = self.base_customer_url.format(
            uid=self.customer_uidb64,
            order_token=self.order.order_token,
            path='surveys'
        )
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        json_resp = resp.data
        order_customer_survey_id = json_resp['id']
        self.order.refresh_from_db()
        self.assertEqual(self.order.customer_survey_id, order_customer_survey_id)

    def test_create_customer_survey_with_subbrand_without_survey(self):
        url = self.base_customer_url.format(
            uid=self.customer_uidb64,
            order_token=self.order_with_subbrand_survey.order_token,
            path='surveys'
        )
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_customer_survey_with_subbrand_with_survey(self):
        self.sub_brand.customer_survey = self.subbrand_customer_survey
        self.sub_brand.save()
        url = self.base_customer_url.format(
            uid=self.customer_uidb64,
            order_token=self.order_with_subbrand_survey.order_token,
            path='surveys'
        )
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        json_resp = resp.data
        order_customer_survey_id = json_resp['id']
        self.order_with_subbrand_survey.refresh_from_db()
        self.assertEqual(
            self.order_with_subbrand_survey.customer_survey_id,
            order_customer_survey_id
        )
        self.assertEqual(
            self.order_with_subbrand_survey.customer_survey.checklist_id,
            self.sub_brand.customer_survey_id
        )

    def test_send_survey_answers(self):
        url = self.base_customer_url.format(
            uid=self.customer_uidb64,
            order_token=self.order.order_token,
            path='surveys'
        )
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        json_resp = resp.data
        order_customer_survey_id = json_resp['id']
        survey_questions = json_resp['survey']['sections'][0]['questions']
        result_answers = []
        for question_data in survey_questions:
            question_id = question_data["id"]
            for answer_data in question_data["answers"]:
                result_answers.append({"question": question_id, "answer": answer_data["id"]})

        survey_url = self.base_customer_url.format(
            uid=self.customer_uidb64,
            order_token=self.order.order_token,
            path='surveys/{}/results'.format(order_customer_survey_id)
        )
        request_data = {
            'result_answers': result_answers
        }

        resp = self.client.post(survey_url, data=request_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_get_count_surveys_result(self):
        self.client.force_authenticate(self.manager)
        survey = SurveyFactory(merchant=self.merchant)
        survey_result = SurveyResultFactory(checklist=survey)
        self.order_with_subbrand_survey.customer_survey = survey_result
        self.order_with_subbrand_survey.save()
        today = timezone.now().astimezone(self.merchant.timezone).date()
        data = {
            'date_from': '%sT00:00:00' % (today - timedelta(days=3)),
            'date_to': '%sT23:59:59' % today,
            'survey': survey.id,
            'sub_branding_id': self.sub_brand.id
        }
        resp = self.client.get('/api/surveys-merchant/count-surveys-result/', data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['count'], 1)

    def test_get_all_related_surveys(self):
        self.client.force_authenticate(self.manager)
        self.merchant.use_subbranding = True
        self.merchant.save()
        survey = SurveyFactory(merchant=self.merchant)
        self.sub_brand.customer_survey = survey
        self.sub_brand.save()

        resp = self.client.get('/api/surveys-merchant/related-surveys/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()), 2)

    def test_get_all_related_surveys_without_subbrandings(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/surveys-merchant/related-surveys/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()), 1)

    def test_get_all_related_surveys_with_order_surveys(self):
        self.client.force_authenticate(self.manager)
        self.merchant.use_subbranding = True
        self.merchant.save()
        survey = SurveyFactory(merchant=self.merchant)
        self.sub_brand.customer_survey = survey
        self.sub_brand.save()
        survey_for_order = SurveyFactory(merchant=self.merchant)
        OrderFactory(merchant=self.merchant, sub_branding=self.sub_brand,
                     customer_survey=SurveyResultFactory(checklist=survey_for_order))
        resp = self.client.get('/api/surveys-merchant/related-surveys/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()), 3)
