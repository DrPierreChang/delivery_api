from datetime import timedelta

from django.utils import timezone

from rest_framework import status

import mock

from driver.tests.base_test_cases import BaseDriverTestCase
from schedule.models import Schedule


class WeekScheduleTestCase(BaseDriverTestCase):
    default_schedule = {
        'mon': {'start': '09:00', 'end': '17:00', 'day_off': False, 'one_time': False, 'breaks': []},
        'tue': {'start': '09:00', 'end': '17:00', 'day_off': False, 'one_time': False, 'breaks': []},
        'wed': {'start': '09:00', 'end': '17:00', 'day_off': False, 'one_time': False, 'breaks': []},
        'thu': {'start': '09:00', 'end': '17:00', 'day_off': False, 'one_time': False, 'breaks': []},
        'fri': {'start': '09:00', 'end': '17:00', 'day_off': False, 'one_time': False, 'breaks': []},
        'sat': {'start': '09:00', 'end': '17:00', 'day_off': False, 'one_time': False, 'breaks': []},
        'sun': {'start': '09:00', 'end': '17:00', 'day_off': False, 'one_time': False, 'breaks': []},
    }

    def test_get_new_schedule(self):
        self.client.force_authenticate(self.driver)

        resp = self.client.get('/api/mobile/schedules/v1/me/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        schedule = {
            'week_schedule': {
                **self.default_schedule,
            }}
        self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

    def test_get_schedule(self):
        Schedule.objects.all().delete()
        Schedule.objects.create(member=self.driver)
        self.client.force_authenticate(self.driver)

        resp = self.client.get('/api/mobile/schedules/v1/me/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        schedule = {
            'week_schedule': {
                **self.default_schedule,
            }}
        self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

    def test_one_time_change_schedule(self):
        self.client.force_authenticate(self.driver)

        friday = timezone.now().astimezone(self.driver.current_merchant.timezone)
        friday -= timedelta(days=friday.weekday()) + timedelta(days=4)
        with mock.patch('django.utils.timezone.now', return_value=friday):
            daily_schedule = {
                'start': '01:00',
                'end': '11:00',
                'day_off': False,
                'one_time': True,
                'breaks': [{'start': '06:00', 'end': '07:00'}]
            }

            resp = self.client.patch('/api/mobile/schedules/v1/me/', {
                'week_schedule': {
                    'mon': daily_schedule,
                },
            })

            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            schedule = {
                'week_schedule': {
                    **self.default_schedule,
                    'mon': daily_schedule,
                }}
            self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

            # Remove temporary changes
            resp = self.client.patch('/api/mobile/schedules/v1/me/', {
                'week_schedule': {
                    'mon': {'one_time': False},
                },
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

            schedule = {
                'week_schedule': {
                    **self.default_schedule,
                }}
            self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

    def test_one_time_change_schedule_with_only_time_off(self):
        self.client.force_authenticate(self.driver)

        friday = timezone.now().astimezone(self.driver.current_merchant.timezone)
        friday -= timedelta(days=friday.weekday()) + timedelta(days=4)
        with mock.patch('django.utils.timezone.now', return_value=friday):
            # Send an empty request marked as temporary.
            resp = self.client.patch('/api/mobile/schedules/v1/me/', {
                'week_schedule': {
                    'mon': {'one_time': True},
                },
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

            schedule = {
                'week_schedule': {
                    **self.default_schedule,
                }}
            self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

            # Temporarily make the day a weekend.
            resp = self.client.patch('/api/mobile/schedules/v1/me/', {
                'week_schedule': {
                    'mon': {'one_time': True, 'day_off': True},
                },
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

            schedule = {
                'week_schedule': {
                    **self.default_schedule,
                    'mon': {**self.default_schedule['mon'], 'one_time': True, 'day_off': True},
                }}
            self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

            # Remove temporary changes
            resp = self.client.patch('/api/mobile/schedules/v1/me/', {
                'week_schedule': {
                    'mon': {'one_time': False},
                },
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

            schedule = {
                'week_schedule': {
                    **self.default_schedule,
                }}
            self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

    def test_change_schedule(self):
        self.client.force_authenticate(self.driver)

        friday = timezone.now().astimezone(self.driver.current_merchant.timezone)
        friday -= timedelta(days=friday.weekday()) + timedelta(days=4)
        with mock.patch('django.utils.timezone.now', return_value=friday):
            resp = self.client.patch('/api/mobile/schedules/v1/{0}/'.format(self.driver.id), {
                'week_schedule': {
                    'mon': {'start': '11:00'},
                },
            })
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

            resp = self.client.patch('/api/mobile/schedules/v1/{0}/'.format(self.driver.id), {
                'week_schedule': {
                    'mon': {'start': '11:00', 'end': '12:00', 'day_off': True, 'one_time': False},
                },
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

            schedule = {
                'week_schedule': {
                    **self.default_schedule,
                    'mon': {'start': '11:00', 'end': '12:00', 'day_off': True, 'one_time': False, 'breaks': []},
                }}
            self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

    def test_ont_time_schedule_with_passage_of_time(self):
        self.client.force_authenticate(self.driver)

        monday = timezone.now().astimezone(self.driver.current_merchant.timezone)
        monday -= timedelta(days=monday.weekday())

        with mock.patch('django.utils.timezone.now', return_value=monday):
            resp = self.client.patch('/api/mobile/schedules/v1/me/', {
                'week_schedule': {
                    'tue': {'start': '10:00', 'end': '11:00', 'day_off': True, 'one_time': True},
                },
            })

            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            schedule = {
                'week_schedule': {
                    **self.default_schedule,
                    'tue': {'start': '10:00', 'end': '11:00', 'day_off': True, 'one_time': True, 'breaks': []},
                }}
            self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

        with mock.patch('django.utils.timezone.now', return_value=monday + timedelta(days=1)):
            resp = self.client.get('/api/mobile/schedules/v1/me/')

            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            schedule = {
                'week_schedule': {
                    **self.default_schedule,
                    'tue': {'start': '10:00', 'end': '11:00', 'day_off': True, 'one_time': True, 'breaks': []},
                }}
            self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

        with mock.patch('django.utils.timezone.now', return_value=monday + timedelta(days=2)):
            resp = self.client.get('/api/mobile/schedules/v1/me/')

            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            schedule = {
                'week_schedule': {
                    **self.default_schedule,
                }}
            self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

    def test_sending_one_time_schedule_for_current_day(self):
        self.client.force_authenticate(self.driver)

        monday = timezone.now().astimezone(self.driver.current_merchant.timezone)
        monday -= timedelta(days=monday.weekday())

        with mock.patch('django.utils.timezone.now', return_value=monday):
            resp = self.client.patch('/api/mobile/schedules/v1/me/', {
                'week_schedule': {
                    'mon': {'start': '10:00', 'end': '11:00', 'day_off': True, 'one_time': True},
                },
            })

            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            schedule = {
                'week_schedule': {
                    **self.default_schedule,
                }}
            self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

        with mock.patch('django.utils.timezone.now', return_value=monday + timedelta(days=1)):
            resp = self.client.get('/api/mobile/schedules/v1/me/')

            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            schedule = {
                'week_schedule': {
                    **self.default_schedule,
                    'mon': {'start': '10:00', 'end': '11:00', 'day_off': True, 'one_time': True, 'breaks': []},
                }}
            self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

    def test_manager_work_with_schedule(self):
        self.client.force_authenticate(self.manager)

        resp = self.client.get('/api/web/schedules/{0}/'.format(self.driver.id))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        schedule = {
            'week_schedule': {
                **self.default_schedule,
            }}
        self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

        resp = self.client.patch('/api/web/schedules/{0}/'.format(self.driver.id), {
            'week_schedule': {
                'mon': {'start': '11:00', 'end': '12:00', 'day_off': True, 'one_time': False},
            },
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        schedule = {
            'week_schedule': {
                **self.default_schedule,
                'mon': {'start': '11:00', 'end': '12:00', 'day_off': True, 'one_time': False, 'breaks': []},
            }}
        self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

    def test_get_all_schedules(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/web/schedules/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
