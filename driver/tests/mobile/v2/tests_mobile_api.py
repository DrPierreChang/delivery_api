import io

from rest_framework import status

from PIL import Image

from base.factories import DriverFactory
from driver.tests.base_test_cases import BaseDriverTestCase
from driver.utils import WorkStatus
from merchant.factories import HubFactory, SkillSetFactory
from merchant.models import DriverHub


class DriverTestCase(BaseDriverTestCase):
    @classmethod
    def setUpTestData(cls):
        super(DriverTestCase, cls).setUpTestData()
        cls.merchant.enable_skill_sets = True
        cls.merchant.use_hubs = True
        cls.merchant.save(update_fields=['enable_skill_sets', 'use_hubs'])

        cls.skill_set = SkillSetFactory(merchant=cls.merchant)
        cls.skill_set_2 = SkillSetFactory(merchant=cls.merchant)
        cls.secret_skill_set = SkillSetFactory(merchant=cls.merchant, is_secret=True)
        cls.driver.work_status = WorkStatus.WORKING
        cls.driver.save()

        cls.driver_2 = DriverFactory(merchant=cls.merchant, first_name='Driver')
        cls.driver_2.skill_sets.set([cls.skill_set, cls.skill_set_2])

        cls.hubs = HubFactory.create_batch(size=10, merchant=cls.merchant)
        DriverHub.objects.create(driver=cls.driver, hub=cls.hubs[0])

    def test_driver_skill_sets_workflow(self):
        self.client.force_authenticate(self.driver)

        resp = self.client.patch('/api/mobile/drivers/v2/me/', {'skill_set_ids': [self.skill_set.id]})
        self.assertEqual(len(resp.data['skill_set_ids']), 1)
        self.assertEqual(resp.data['skill_set_ids'][0], self.skill_set.id)

        resp = self.client.patch('/api/mobile/drivers/v2/me/', {'skill_set_ids': [self.skill_set_2.id]})
        self.assertEqual(len(resp.data['skill_set_ids']), 1)
        self.assertEqual(resp.data['skill_set_ids'][0], self.skill_set_2.id)

        resp = self.client.patch('/api/mobile/drivers/v2/me/', {})
        self.assertEqual(len(resp.data['skill_set_ids']), 1)
        self.assertEqual(resp.data['skill_set_ids'][0], self.skill_set_2.id)

        resp = self.client.patch('/api/mobile/drivers/v2/me/', {'skill_set_ids': []})
        self.assertEqual(resp.data['skill_set_ids'], None)

        self.driver.skill_sets.add(self.secret_skill_set)
        resp = self.client.patch('/api/mobile/drivers/v2/me/', {'skill_set_ids': []})
        self.assertEqual(len(resp.data['skill_set_ids']), 1)

    def assertDictSubsetEqual(self, d1, d2):
        # Checks to see if dict d2 is a subset of dict d1. Can handle nested dict
        for key, value in d2.items():
            if isinstance(value, dict):
                self.assertDictSubsetEqual(d1[key], value)
            else:
                self.assertEqual(d1[key], value)

    def test_driver_hubs_workflow(self):
        self.client.force_authenticate(self.driver)

        resp = self.client.patch('/api/mobile/drivers/v2/me/', {'default_order_values': {'wayback_hub_ids': []}})
        self.assertEqual(resp.data['default_order_values']['wayback_hub_ids'], None)
        self.assertEqual(resp.data['default_order_values']['starting_hub_id'], None)
        self.assertEqual(resp.data['default_order_values']['ending_hub_id'], None)

        resp = self.client.patch(
            '/api/mobile/drivers/v2/me/',
            {'default_order_values': {'wayback_hub_ids': [self.hubs[1].id]}},
        )
        self.assertEqual(len(resp.data['default_order_values']['wayback_hub_ids']), 1)
        self.assertEqual(resp.data['default_order_values']['wayback_hub_ids'][0], self.hubs[1].id)

        resp = self.client.patch('/api/mobile/drivers/v2/me/', {'default_order_values': {
            'starting_hub_id': self.hubs[2].id,
            'ending_hub_id': self.hubs[3].id,
        }})
        self.assertEqual(resp.data['default_order_values']['starting_hub_id'], self.hubs[2].id)
        self.assertEqual(resp.data['default_order_values']['ending_hub_id'], self.hubs[3].id)

        resp = self.client.patch('/api/mobile/drivers/v2/me/', {'default_order_values': {
            'starting_hub_id': None,
            'ending_hub_id': None,
        }})
        self.assertEqual(resp.data['default_order_values']['starting_hub_id'], None)
        self.assertEqual(resp.data['default_order_values']['ending_hub_id'], None)

    def test_driver_profile(self):
        self.client.force_authenticate(self.driver)

        resp = self.client.get('/api/mobile/drivers/v2/me/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.get('/api/mobile/drivers/v2/vehicle_types/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        data = {
            'email': 'jojo@example.com',
            'first_name': 'Jojo1',
            'last_name': 'Jojo2',
            'vehicle': {
                'type': 2,
                'capacity': 123.3
            },
            'phone_number': '+61 499 902 103',
            'skill_set_ids': [self.skill_set.id],
            'default_order_values': {
                'wayback_hub_ids': [self.hubs[5].id, self.hubs[6].id],
                'starting_hub_id': self.hubs[7].id,
                'ending_hub_id': self.hubs[8].id,
            },
        }

        resp = self.client.patch('/api/mobile/drivers/v2/me/', data)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertDictSubsetEqual(resp.data, data)
        self.assertTrue(isinstance(resp.data['vehicle']['capacity'], float))

    def _generate_image(self):
        file = io.BytesIO()

        image = Image.new('RGBA', size=(100, 100), color=(155, 0, 0))
        image.save(file, 'png')
        file.name = 'test.png'
        file.seek(0)

        return file

    def test_upload_image(self):
        self.client.force_authenticate(self.driver)

        image = self._generate_image()
        resp = self.client.patch(
            '/api/mobile/drivers/v2/me/upload_images/',
            data={'avatar': image},
            format='multipart',
        )
        self.driver.refresh_from_db()

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data['avatar'])

    def test_statistics(self):
        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/mobile/drivers/v2/me/statistics/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_reset_charfield(self):
        self.client.force_authenticate(self.driver_2)
        resp = self.client.patch('/api/mobile/drivers/v2/me/', {'first_name': None})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.driver_2.refresh_from_db()
        self.assertEqual(self.driver_2.first_name, '')
        self.assertEqual(resp.data['first_name'], None)

    def test_reset_many_related_field(self):
        self.client.force_authenticate(self.driver_2)
        resp = self.client.patch('/api/mobile/drivers/v2/me/', {'skill_set_ids': None})
        self.driver_2.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(self.driver_2.skill_sets.all()), 0)
        self.assertEqual(resp.data['skill_set_ids'], None)

    def test_empty_object_response(self):
        self.manager.merchant = None
        self.manager.save()
        self.client.force_authenticate(self.driver_2)
        resp = self.client.get('/api/mobile/drivers/v2/me/')
        for _, value in resp.data['manager'].items():
            self.assertEqual(value, None)
