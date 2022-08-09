from datetime import timedelta

from django.utils import timezone

from rest_framework import status

from base.factories import DriverFactory, DriverLocationFactory
from driver.tests.base_test_cases import BaseDriverTestCase
from driver.utils import WorkStatus
from reporting.models import Event


class DriverTestCase(BaseDriverTestCase):
    @classmethod
    def setUpTestData(cls):
        super(DriverTestCase, cls).setUpTestData()
        cls.driver.work_status = WorkStatus.WORKING
        cls.driver.save()

    def test_locations_in_change_status_events(self):
        driver = DriverFactory(
                merchant=self.merchant,
                work_status=WorkStatus.WORKING
            )
        loc = DriverLocationFactory(member=driver)
        driver.last_location = loc
        driver.save()
        self.client.force_authenticate(driver)

        self.client.patch('/api/mobile/drivers/v1/me/status/', {
            'work_status': WorkStatus.ON_BREAK,
        })
        self.client.patch('/api/mobile/drivers/v1/me/status/', {
            'offline_history': [
                {
                    'offline_happened_at': timezone.now().timestamp(),
                    'work_status': WorkStatus.WORKING,
                    'location': {'location': {'lat': 53.907600, 'lng': 27.515333}}
                }
            ]
        })
        self.client.patch('/api/mobile/drivers/v1/me/status/', {
            'offline_history': [
                {
                    'offline_happened_at': timezone.now().timestamp(),
                    'work_status': WorkStatus.NOT_WORKING,
                }
            ]
        })

        events = driver.events.all().filter(event=Event.CHANGED, field='work_status')
        events = list(events.order_by('happened_at'))

        self.assertEqual(len(events), 3)
        self.assertTrue(events[0].obj_dump and 'last_location' in events[0].obj_dump)
        self.assertTrue(events[1].obj_dump and 'last_location' in events[1].obj_dump)
        self.assertTrue(events[2].obj_dump is None)

        resp = self.client.patch('/api/mobile/drivers/v1/me/status/', {
            'offline_history': [
                {
                    'offline_happened_at': (timezone.now() - timedelta(days=1)).timestamp(),
                    'work_status': WorkStatus.NOT_WORKING,
                }
            ]
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_locations_in_change_status_events(self):
        driver = DriverFactory(
                merchant=self.merchant,
                work_status=WorkStatus.WORKING
            )
        self.client.force_authenticate(driver)

        resp = self.client.patch('/api/mobile/drivers/v1/me/status/', {
            'offline_history': [
                {
                    'offline_happened_at': (timezone.now() - timedelta(days=1)).timestamp(),
                    'work_status': WorkStatus.NOT_WORKING,
                    'location': None
                }
            ]
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.patch('/api/mobile/drivers/v1/me/status/', {
            'work_status': WorkStatus.ON_BREAK,
            'location': None
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_bulk_change_status(self):
        driver = DriverFactory(
            merchant=self.merchant,
            work_status=WorkStatus.WORKING
        )
        driver.work_status = WorkStatus.WORKING
        driver.has_internet_connection = False
        driver.save()
        self.client.force_authenticate(driver)
        timestamp = timezone.now().timestamp()
        self.client.patch(
            '/api/mobile/drivers/v1/me/status/',
            {
                'offline_history': [
                    {
                        'offline_happened_at': timestamp - 100,
                        'work_status': WorkStatus.ON_BREAK,
                        'location': {
                            'location': {
                                'lat': 53.907600,
                                'lng': 27.515333,
                            }
                        }
                    }, {
                        'offline_happened_at': timestamp - 90,
                        'work_status': WorkStatus.NOT_WORKING,
                        'location': {
                            'location': {
                                'lat': 53.907600,
                                'lng': 27.515333,
                            }
                        }
                    }, {
                        'offline_happened_at': timestamp - 80,
                        'work_status': WorkStatus.WORKING,
                        'location': {
                            'location': {
                                'lat': 53.907600,
                                'lng': 27.515333,
                            }
                        }
                    }, {
                        'offline_happened_at': timestamp - 50,
                        'work_status': WorkStatus.NOT_WORKING,
                    }, {
                        'offline_happened_at': timestamp,
                        'work_status': WorkStatus.WORKING,
                    }
                ]
            }
        )
        events = driver.events.all().filter(event=Event.CHANGED, field='work_status')
        events = list(events.order_by('happened_at'))

        self.assertEqual(len(events), 5)
        self.assertTrue(events[0].obj_dump and 'last_location' in events[0].obj_dump)
        self.assertEqual(events[0].new_value, WorkStatus.ON_BREAK)
        self.assertEqual(events[0].happened_at.timestamp(), timestamp - 100)

        self.assertTrue(events[1].obj_dump and 'last_location' in events[1].obj_dump)
        self.assertEqual(events[1].new_value, WorkStatus.NOT_WORKING)
        self.assertEqual(events[1].happened_at.timestamp(), timestamp - 90)

        self.assertTrue(events[2].obj_dump and 'last_location' in events[2].obj_dump)
        self.assertEqual(events[2].new_value, WorkStatus.WORKING)
        self.assertEqual(events[2].happened_at.timestamp(), timestamp - 80)

        self.assertTrue(events[3].obj_dump is None)
        self.assertEqual(events[3].new_value, WorkStatus.NOT_WORKING)
        self.assertEqual(events[3].happened_at.timestamp(), timestamp - 50)

        self.assertTrue(events[4].obj_dump is None)
        self.assertEqual(events[4].new_value, WorkStatus.WORKING)
        self.assertEqual(events[4].happened_at.timestamp(), timestamp)
