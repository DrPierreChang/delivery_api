from rest_framework import status

from base.factories import DriverFactory, DriverLocationFactory
from driver.tests.base_test_cases import BaseDriverTestCase
from driver.utils import WorkStatus
from merchant.factories import HubFactory, SkillSetFactory
from merchant.models import DriverHub
from reporting.models import Event


class WebDriverTestCase(BaseDriverTestCase):
    driver_url = '/api/web/dev/drivers/{}/'
    drivers_url = '/api/web/dev/drivers/'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.merchant.enable_skill_sets = True
        cls.merchant.use_hubs = True
        cls.merchant.save()

        cls.skill_set = SkillSetFactory(merchant=cls.merchant)
        cls.skill_set_2 = SkillSetFactory(merchant=cls.merchant)
        cls.secret_skill_set = SkillSetFactory(merchant=cls.merchant, is_secret=True)

        cls.driver.work_status = WorkStatus.WORKING
        cls.driver.save()

        cls.hubs = HubFactory.create_batch(size=10, merchant=cls.merchant)
        DriverHub.objects.create(driver=cls.driver, hub=cls.hubs[0])

    def assertDictSubsetEqual(self, d1, d2):
        # Checks to see if dict d2 is a subset of dict d1. Can handle nested dict
        for key, value in d2.items():
            if isinstance(value, dict):
                self.assertDictSubsetEqual(d1[key], value)
            else:
                self.assertEqual(d1[key], value)

    def test_get_drivers(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get(self.drivers_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_get_driver(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get(self.driver_url.format(self.driver.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_driver_hubs_workflow(self):
        self.client.force_authenticate(self.manager)

        resp = self.client.patch(self.driver_url.format(self.driver.id), {'default_order_values': {
            'starting_hub_id': self.hubs[2].id,
            'ending_hub_id': self.hubs[3].id,
        }})
        self.assertEqual(resp.data['default_order_values']['starting_hub']['id'], self.hubs[2].id)
        self.assertEqual(resp.data['default_order_values']['ending_hub']['id'], self.hubs[3].id)

        resp = self.client.patch(self.driver_url.format(self.driver.id), {'default_order_values': {
            'starting_hub_id': None,
            'ending_hub_id': None,
        }})
        self.assertEqual(resp.data['default_order_values']['starting_hub'], None)
        self.assertEqual(resp.data['default_order_values']['ending_hub'], None)

    def test_statistics(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get(self.driver_url.format(self.driver.id) + 'statistics/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_locations_in_change_status_events(self):
        driver = DriverFactory(
                merchant=self.merchant,
                work_status=WorkStatus.WORKING
            )
        loc = DriverLocationFactory(member=driver)
        driver.last_location = loc
        driver.save()
        self.client.force_authenticate(self.manager)

        self.client.patch(self.driver_url.format(driver.id), {
            'work_status': WorkStatus.ON_BREAK,
        })

        events = driver.events.all().filter(event=Event.CHANGED, field='work_status')
        events = list(events)

        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].obj_dump and 'last_location' in events[0].obj_dump)
