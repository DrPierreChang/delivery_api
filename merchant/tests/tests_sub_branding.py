from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import ManagerFactory
from merchant.factories import MerchantFactory, SubBrandingFactory
from merchant.models import SubBranding
from merchant_extension.factories import SurveyFactory, SurveyResultFactory


class SubBrandingTestCase(APITestCase):

    @classmethod
    def setUpClass(cls):
        super(SubBrandingTestCase, cls).setUpClass()
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)

    def setUp(self):
        self.client.force_authenticate(user=self.manager)
        self.sub_brand = SubBrandingFactory(merchant=self.merchant)

    def test_create_sub_brand(self):
        response = self.client.post(
            path='/api/sub-branding/',
            data={"name": "Test Subbrand"}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_get_sub_brand_by_id(self):
        response = self.client.get(path='/api/sub-branding/{id}'.format(id=self.sub_brand.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_sub_brand_list(self):
        response = self.client.get(path='/api/sub-branding/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(isinstance(response.json()["results"], list))

    def test_update_sub_brand(self):
        update_data = {
                "name": "Subbrand New Name",
                "sms_sender": "Subbrand",
                "store_url": "http://test.com"
            }
        response = self.client.put(
            path='/api/sub-branding/{id}'.format(id=self.sub_brand.id),
            data=update_data
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.sub_brand.refresh_from_db()
        self.assertEqual(self.sub_brand.name, update_data["name"])
        self.assertEqual(self.sub_brand.sms_sender, update_data["sms_sender"])
        self.assertEqual(self.sub_brand.store_url, update_data["store_url"])

    def test_update_sub_brand_sms_sender(self):
        long_name = "Sms sender name more than 11 symbols"
        response = self.client.patch(
            path='/api/sub-branding/{id}'.format(id=self.sub_brand.id),
            data={"sms_sender": long_name}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        short_name = "Sms sender"
        response = self.client.patch(
            path='/api/sub-branding/{id}'.format(id=self.sub_brand.id),
            data={"sms_sender": short_name}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.sub_brand.refresh_from_db()
        self.assertEqual(self.sub_brand.sms_sender, short_name)

    def test_update_sub_brand_phone(self):
        incorrect_phone = "123456abc"
        response = self.client.patch(
            path='/api/sub-branding/{id}'.format(id=self.sub_brand.id),
            data={"phone": incorrect_phone}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        incorrect_region_phone = "375295071495"
        response = self.client.patch(
            path='/api/sub-branding/{id}'.format(id=self.sub_brand.id),
            data={"phone": incorrect_region_phone}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        correct_phone = "+61499902103"
        response = self.client.patch(
            path='/api/sub-branding/{id}'.format(id=self.sub_brand.id),
            data={"phone": correct_phone}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete_sub_brand(self):
        response = self.client.delete(path='/api/sub-branding/{id}'.format(id=self.sub_brand.id))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SubBranding.objects.filter(id=self.sub_brand.id).exists())

    def test_filter_sub_brand_list_by_survey(self):
        survey = SurveyFactory()
        SurveyResultFactory(checklist=survey)
        SubBrandingFactory(merchant=self.merchant)
        self.sub_brand.customer_survey = survey
        self.sub_brand.save()
        response = self.client.get(path='/api/sub-branding/?customer_survey={}'.format(survey.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['count'], 1)
