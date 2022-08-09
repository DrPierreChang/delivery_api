from django.db.models import Q

from rest_framework import status
from rest_framework.test import APITestCase

from mock import patch

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import MerchantFactory, SkillSetFactory
from merchant.models import SkillSet
from notification.factories import FCMDeviceFactory


class SkillSetsTestCase(APITestCase):

    @classmethod
    def setUpTestData(cls):
        super(SkillSetsTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory(enable_skill_sets=True)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant)

    def setUp(self):
        self.skill_set = SkillSetFactory(merchant=self.merchant)
        self.another_skill_set = SkillSetFactory(merchant=self.merchant, is_secret=True)

    def test_unauthenticated_user_access(self):
        resp = self.client.get('/api/merchant/my/skill-sets')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_manager_get_skill_sets_list(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/merchant/my/skill-sets')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        merchant_jobs_count = SkillSet.objects.filter(merchant_id=self.merchant.id).count()
        self.assertEqual(resp.json()['count'], merchant_jobs_count)

    def test_driver_get_skill_sets_list(self):
        self.client.force_authenticate(self.driver)
        url = '/api/merchant/my/skill-sets?{}'
        driver_skill_sets = self.driver.skill_sets.values_list('id', flat=True)

        resp = self.client.get(url.format(''))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        merchant_jobs_count = SkillSet.objects.filter(
            merchant_id=self.merchant.id,
        ).exclude(
            ~Q(id__in=driver_skill_sets) & Q(is_secret=True)
        ).count()
        self.assertEqual(resp.json()['count'], merchant_jobs_count)

        resp = self.client.get(url.format('assigned=true'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['count'], self.driver.skill_sets.count())

        resp = self.client.get(url.format('assigned=false'))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        merchant_jobs_count = SkillSet.objects.filter(
            merchant_id=self.merchant.id,
        ).exclude(
            Q(id__in=driver_skill_sets) |
            Q(is_secret=True)
        ).count()
        self.assertEqual(resp.json()['count'], merchant_jobs_count)

    def test_manager_create_skill_set(self):
        self.client.force_authenticate(self.manager)

        skill_set_data = {
            "name": "New Job Type",
            "color": SkillSet.ROYAL_BLUE,
            "service_time": 4,
        }

        # simple job type creation
        resp = self.client.post('/api/merchant/my/skill-sets', skill_set_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        skill_set_id = resp.json()['id']
        skill = SkillSet.objects.get(id=skill_set_id)
        self.assertEqual(skill.service_time, 4)

        # duplicated job type data
        resp = self.client.post('/api/merchant/my/skill-sets', skill_set_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_driver_create_skill_set(self):
        self.client.force_authenticate(self.driver)

        skill_set_data = {
            "name": "New Driver Job Type",
            "color": SkillSet.ROYAL_BLUE
        }

        resp = self.client.post('/api/merchant/my/skill-sets', skill_set_data)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_get_certain_skill_set(self):
        self.client.force_authenticate(self.manager)
        url = '/api/merchant/my/skill-sets/{}'

        resp = self.client.get(url.format(self.skill_set.id))
        self.assertTrue(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['id'], self.skill_set.id)

        # get secret job type
        resp = self.client.get(url.format(self.another_skill_set.id))
        self.assertTrue(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['id'], self.another_skill_set.id)

    def test_driver_get_certain_skill_set(self):
        self.client.force_authenticate(self.driver)
        url = '/api/merchant/my/skill-sets/{}'

        resp = self.client.get(url.format(self.skill_set.id))
        self.assertTrue(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['id'], self.skill_set.id)

        # get secret job type
        resp = self.client.get(url.format(self.another_skill_set.id))
        self.assertTrue(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_manager_update_certain_skill_set(self):
        self.client.force_authenticate(self.manager)
        url = '/api/merchant/my/skill-sets/{}'

        update_data = {
            "name": "New name",
            "color": SkillSet.ATLANTIS,
            "service_time": 0,
        }

        self.assertIsNone(self.skill_set.service_time)
        resp = self.client.put(url.format(self.skill_set.id), update_data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.skill_set.refresh_from_db()
        self.assertEqual(self.skill_set.name, update_data["name"])
        self.assertEqual(self.skill_set.color, update_data["color"])
        self.assertEqual(self.skill_set.service_time, 0)

        # update another object with the same data
        resp = self.client.put(url.format(self.another_skill_set.id), update_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_driver_update_certain_skill_set(self):
        self.client.force_authenticate(self.driver)
        url = '/api/merchant/my/skill-sets/{}'

        update_data = {
            "name": "New name",
            "color": SkillSet.ATLANTIS
        }

        resp = self.client.put(url.format(self.skill_set.id), update_data)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_get_certain_skill_set_drivers(self):
        self.client.force_authenticate(self.manager)
        url = '/api/merchant/my/skill-sets/{}/drivers'
        self.skill_set.drivers.add(self.driver)

        resp = self.client.get(url.format(self.skill_set.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()['results']), self.skill_set.drivers.count())

    @patch('notification.celery_tasks.send_device_notification.delay')
    def test_manager_add_drivers_to_secret_skill_set(self, send_notification):
        self.client.force_authenticate(self.manager)
        self.another_driver = DriverFactory(merchant=self.merchant)
        FCMDeviceFactory(user=self.driver)
        FCMDeviceFactory(user=self.another_driver)
        url = '/api/merchant/my/skill-sets/{}/drivers'

        update_data = {
            "drivers": [self.driver.member_id, self.another_driver.member_id]
        }
        resp = self.client.post(url.format(self.another_skill_set.id), update_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(resp.json()), len(update_data["drivers"]))

        send_notification.assert_called()

    @patch('notification.celery_tasks.send_device_notification.delay')
    def test_manager_remove_drivers_from_secret_skill_set(self, send_notification):
        self.client.force_authenticate(self.manager)
        self.another_driver = DriverFactory(merchant=self.merchant)
        FCMDeviceFactory(user=self.driver)
        FCMDeviceFactory(user=self.another_driver)
        url = '/api/merchant/my/skill-sets/{}/drivers'

        update_data = {
            "drivers": [self.another_driver.member_id, ]
        }
        resp = self.client.delete(url.format(self.another_skill_set.id), update_data)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

        send_notification.assert_called()

    def test_driver_add_drivers_to_secret_skill_set(self):
        self.client.force_authenticate(self.driver)
        self.another_driver = DriverFactory(merchant=self.merchant)
        url = '/api/merchant/my/skill-sets/{}/drivers'

        update_data = {
            "drivers": [self.driver.member_id, self.another_driver.member_id]
        }
        resp = self.client.post(url.format(self.another_skill_set.id), update_data)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_driver_remove_drivers_from_secret_skill_set(self):
        self.client.force_authenticate(self.driver)
        self.another_driver = DriverFactory(merchant=self.merchant)
        url = '/api/merchant/my/skill-sets/{}/drivers'

        update_data = {
            "drivers": [self.driver.member_id, self.another_driver.member_id]
        }
        resp = self.client.delete(url.format(self.another_skill_set.id), update_data)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
