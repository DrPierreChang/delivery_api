import os
from datetime import time

from django.utils import timezone

from rest_framework import status

from six.moves import cStringIO

from base.factories import DriverFactory
from base.models import DriverScheduleUpload
from driver.tests.base_test_cases import BaseDriverTestCase

DIR_PATH = os.path.dirname(os.path.abspath(__file__))


class DriverScheduleUploadTestCase(BaseDriverTestCase):
    url = '/api/web/dev/drivers/schedule_upload/'

    default_headers = 'driver_id,shift_start,shift_end,day_off,capacity'
    item_template = '{driver_id},{shift_start},{shift_end},{day_off},{capacity}\n'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.merchant.enable_job_capacity = True
        cls.merchant.save()

    @classmethod
    def create_csv_text(cls, data_list, headers=None):
        first_string = headers if headers else cls.default_headers + '\n'
        res = first_string
        for data in data_list:
            prepared_data = {
                'shift_start': '',
                'shift_end': '',
                'day_off': '',
                'capacity': '',
                **data
            }
            res += cls.item_template.format(**prepared_data)
        return res

    def send_opened_file(self, csv_text, date, status_code=status.HTTP_200_OK):
        _file = cStringIO(csv_text)
        _file.name = 'driver_schedule.csv'
        data = {
            'date': date,
            'file': _file,
        }
        resp = self.client.post(self.url, format='multipart', data=data)
        self.assertEqual(resp.status_code, status_code)
        return resp

    def setUp(self):
        self.client.force_authenticate(self.manager)

    def test_upload(self):
        drivers = DriverFactory.create_batch(size=5, merchant=self.merchant)
        date = timezone.now().date() + timezone.timedelta(days=3)
        data_list = [{
            'driver_id': drivers[0].id,
            'shift_start': '05:00',
            'shift_end': '21:00',
            'day_off': False,
            'capacity': 20,
        }, {
            'driver_id': drivers[1].id,
            'capacity': 20,
        }, {
            'driver_id': drivers[2].id,
            'shift_start': '05:00',
            'shift_end': '21:00',
        }, {
            'driver_id': drivers[3].id,
            'day_off': True,
        }]
        csv_text = self.create_csv_text(data_list)
        resp = self.send_opened_file(csv_text, date)
        self.assertEqual(resp.data['status'], DriverScheduleUpload.COMPLETED)
        for driver in drivers:
            driver.refresh_from_db()

        self.assertEqual(drivers[0].car.get_capacity(date), 20)
        self.assertEqual(
            drivers[0].schedule.get_day_schedule(date),
            {'start': time(hour=5), 'end': time(hour=21), 'day_off': False},
        )

        self.assertEqual(drivers[1].car.get_capacity(date), 20)

        self.assertEqual(
            drivers[2].schedule.get_day_schedule(date),
            {'start': time(hour=5), 'end': time(hour=21), 'day_off': False},
        )

        self.assertTrue(drivers[3].schedule.get_day_schedule(date)['day_off'])

    def test_wrong_time_upload(self):
        driver = DriverFactory(merchant=self.merchant)
        date = timezone.now().date() + timezone.timedelta(days=3)

        data_list = [{
            'driver_id': driver.id,
            'shift_end': '21:00',
        }]
        csv_text = self.create_csv_text(data_list)
        resp = self.send_opened_file(csv_text, date)
        self.assertEqual(resp.data['status'], DriverScheduleUpload.FAILED)

        data_list = [{
            'driver_id': driver.id,
            'shift_start': '05:00',
        }]
        csv_text = self.create_csv_text(data_list)
        resp = self.send_opened_file(csv_text, date)
        self.assertEqual(resp.data['status'], DriverScheduleUpload.FAILED)

        data_list = [{
            'driver_id': driver.id,
            'shift_start': '23:00',
            'shift_end': '21:00',
        }]
        csv_text = self.create_csv_text(data_list)
        resp = self.send_opened_file(csv_text, date)
        self.assertEqual(resp.data['status'], DriverScheduleUpload.FAILED)

    def test_wrong_date_upload(self):
        driver = DriverFactory(merchant=self.merchant)
        date = timezone.now().date() - timezone.timedelta(days=3)
        data_list = [{
            'driver_id': driver.id,
            'shift_end': '21:00',
        }]
        csv_text = self.create_csv_text(data_list)
        resp = self.send_opened_file(csv_text, date, status.HTTP_400_BAD_REQUEST)
