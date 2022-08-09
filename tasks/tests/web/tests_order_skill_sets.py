from datetime import timedelta

from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import MerchantFactory, SkillSetFactory
from tasks.models import Order
from tasks.tests.factories import OrderFactory


class OrderSkillSetsTestCase(APITestCase):
    orders_url = '/api/web/dev/orders/'

    @classmethod
    def setUpTestData(cls):
        super(OrderSkillSetsTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory(
            in_app_jobs_assignment=True,
            enable_skill_sets=True
        )
        cls.skill = SkillSetFactory(merchant=cls.merchant)
        cls.secret_skill = SkillSetFactory(merchant=cls.merchant, is_secret=True)

        cls.manager = ManagerFactory(merchant=cls.merchant)

        cls.driver = DriverFactory(merchant=cls.merchant)
        cls.driver.skill_sets.add(cls.skill)

        cls.driver_2 = DriverFactory(merchant=cls.merchant)
        cls.driver_2.skill_sets.add(cls.skill)
        cls.driver_2.skill_sets.add(cls.secret_skill)

        cls.order = OrderFactory(
            merchant=cls.merchant, 
            manager=cls.manager,
            driver=None,
            deliver_before=timezone.now() + timedelta(hours=5)
        )
        cls.order_with_secret_skill = OrderFactory(
            merchant=cls.merchant,
            manager=cls.manager,
            driver=None,
            deliver_before=timezone.now() + timedelta(hours=5)
        )
        cls.order_without_skill = OrderFactory(
            merchant=cls.merchant,
            manager=cls.manager,
            driver=None,
            deliver_before=timezone.now() + timedelta(hours=5)
        )
        cls.order.skill_sets.add(cls.skill)
        cls.order_with_secret_skill.skill_sets.add(cls.skill, cls.secret_skill)

    def test_get_jobs_with_skillsets_by_manager(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get(self.orders_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_json = response.json()
        expected_jobs_number = Order.objects.filter(merchant=self.merchant).count()
        self.assertEqual(expected_jobs_number, response_json['count'])
        jobs = response_json['results']
        jobs_ids = [job['order_id'] for job in jobs]
        self.assertTrue(self.order_with_secret_skill.order_id in jobs_ids)

    def test_update_job_add_skill_sets(self):
        self.order.driver = self.driver
        self.order.status = Order.ASSIGNED
        self.order.save()

        self.client.force_authenticate(self.manager)
        url = self.orders_url + '{id}/'.format(id=self.order.id)

        update_data = {'skill_set_ids': [self.secret_skill.id, ]}
        resp = self.client.patch(url, data=update_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_job_remove_driver(self):
        self.order.driver = self.driver
        self.order.status = Order.ASSIGNED
        self.order.save()
        self.driver.skill_sets.clear()

        self.client.force_authenticate(self.manager)
        url = self.orders_url + '{id}/'.format(id=self.order.id)

        # Invalid driver by skill sets
        update_data = {'driver_id': None, 'status': Order.NOT_ASSIGNED}
        resp = self.client.patch(url, data=update_data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_update_job_skill_sets_assign_driver(self):
        self.client.force_authenticate(self.manager)
        url = self.orders_url + '{id}/'.format(id=self.order_with_secret_skill.id)

        update_data = {'driver_id': self.driver.id, 'status': Order.ASSIGNED}
        resp = self.client.patch(url, data=update_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        self.driver.skill_sets.add(self.secret_skill)
        resp = self.client.patch(url, data=update_data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
