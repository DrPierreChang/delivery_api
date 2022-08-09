from datetime import timedelta

from django.utils import timezone

from rest_framework import status

import mock

from driver.tests.base_test_cases import BaseDriverTestCase
from schedule.models import Schedule


class ScheduleCalendarTestCase(BaseDriverTestCase):
    default_schedule = {
        'constant': {
            'mon': {'start': '09:00', 'end': '17:00', 'day_off': False},
            'tue': {'start': '09:00', 'end': '17:00', 'day_off': False},
            'wed': {'start': '09:00', 'end': '17:00', 'day_off': False},
            'thu': {'start': '09:00', 'end': '17:00', 'day_off': False},
            'fri': {'start': '09:00', 'end': '17:00', 'day_off': False},
            'sat': {'start': '09:00', 'end': '17:00', 'day_off': False},
            'sun': {'start': '09:00', 'end': '17:00', 'day_off': False},
        },
        'one_time': {}
    }

    def test_get_new_schedule(self):
        self.client.force_authenticate(self.driver)

        resp = self.client.get('/api/mobile/schedules_calendar/v1/me/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, {'schedule': self.default_schedule, 'member_id': self.driver.id})

    def test_get_schedule(self):
        Schedule.objects.all().delete()
        Schedule.objects.create(member=self.driver)
        self.client.force_authenticate(self.driver)

        resp = self.client.get('/api/mobile/schedules_calendar/v1/me/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, {'schedule': self.default_schedule, 'member_id': self.driver.id})

    def test_one_time_change_schedule(self):
        self.client.force_authenticate(self.driver)

        friday = timezone.now().astimezone(self.driver.current_merchant.timezone)
        friday -= timedelta(days=friday.weekday()) + timedelta(days=3)
        with mock.patch('django.utils.timezone.now', return_value=friday):
            monday = str((friday + timedelta(days=4)).date())
            daily_schedule = {
                'start': '01:00',
                'end': '11:00',
                'day_off': False,
                'breaks': [{'start': '06:00', 'end': '07:00'}]
            }
            resp = self.client.patch('/api/mobile/schedules_calendar/v1/me/', {
                'schedule': {'one_time': {monday: daily_schedule}},
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            schedule = {
                'schedule': {
                    'constant': self.default_schedule['constant'],
                    'one_time': {
                        monday: daily_schedule
                    }
                }}
            self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

            # Remove temporary changes
            resp = self.client.patch('/api/mobile/schedules_calendar/v1/me/', {
                'schedule': {
                    'one_time': {
                        monday: {'day_off': False}
                    }
                }
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(resp.data, {'schedule': self.default_schedule, 'member_id': self.driver.id})

    def test_change_schedule(self):
        self.client.force_authenticate(self.driver)

        friday = timezone.now().astimezone(self.driver.current_merchant.timezone)
        friday -= timedelta(days=friday.weekday()) + timedelta(days=4)
        with mock.patch('django.utils.timezone.now', return_value=friday):
            resp = self.client.patch('/api/mobile/schedules_calendar/v1/{0}/'.format(self.driver.id), {
                'schedule': {
                    'constant': {
                        'mon': {'start': '11:00', 'end': '12:00', 'day_off': True}
                    }
                }
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

            schedule = {
                'schedule': {
                    'constant': {
                        **self.default_schedule['constant'],
                        'mon': {'start': '11:00', 'end': '12:00', 'day_off': True}
                    },
                    'one_time': {}
                }
            }
            self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

    def test_ont_time_schedule_with_passage_of_time(self):
        self.client.force_authenticate(self.driver)

        monday = timezone.now().astimezone(self.driver.current_merchant.timezone)
        monday -= timedelta(days=monday.weekday())

        with mock.patch('django.utils.timezone.now', return_value=monday):
            resp = self.client.patch('/api/mobile/schedules_calendar/v1/me/', {
                'schedule': {
                    'one_time': {
                        str(monday.date()): {'start': '10:00', 'end': '11:00', 'day_off': True}
                    }
                }
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

            schedule = {
                'schedule': {
                    'constant': self.default_schedule['constant'],
                    'one_time': {
                        str(monday.date()): {'start': '10:00', 'end': '11:00', 'day_off': True}
                    }
                }}
            self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

        with mock.patch('django.utils.timezone.now', return_value=monday + timedelta(days=1)):
            resp = self.client.patch('/api/mobile/schedules_calendar/v1/me/', {
                'schedule': {
                    'one_time': {
                        str((monday + timedelta(days=1)).date()): {}
                    }
                }
            })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(resp.data, {'schedule': self.default_schedule, 'member_id': self.driver.id})

    def test_manager_work_with_schedule(self):
        self.client.force_authenticate(self.manager)

        resp = self.client.get('/api/web/schedules_calendar/{0}/'.format(self.driver.id))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        schedule = {
            'schedule': {
                **self.default_schedule,
            }}
        self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

        resp = self.client.patch('/api/web/schedules_calendar/{0}/'.format(self.driver.id), {
            'schedule': {
                'constant': {
                    'mon': {'start': '11:00', 'end': '12:00', 'day_off': True}
                }
            }
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        schedule = {
            'schedule': {
                'constant': {
                    **self.default_schedule['constant'],
                    'mon': {'start': '11:00', 'end': '12:00', 'day_off': True}
                },
                'one_time': {}
            }}
        self.assertEqual(resp.data, {**schedule, 'member_id': self.driver.id})

        resp = self.client.get('/api/web/schedules_calendar/{0}/'.format(self.driver.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_get_all_schedules(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/web/schedules_calendar/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
