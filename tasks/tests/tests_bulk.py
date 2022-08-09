from __future__ import absolute_import, unicode_literals

import os
from collections import namedtuple
from datetime import datetime, time, timedelta
from io import BytesIO

from django.conf import settings
from django.db import transaction
from django.test import override_settings, tag
from django.utils import timezone

from rest_framework import status

import pytz
from dateutil import parser
from jinja2 import Template
from six.moves import cStringIO, xrange

from base.factories import DriverFactory
from merchant.factories import LabelFactory, SkillSetFactory
from merchant.models import Merchant
from radaro_utils import countries
from radaro_utils.tests.utils import PerformanceMeasure
from tasks.mixins.order_status import OrderStatus
from tasks.models import BulkDelayedUpload, Customer, Order
from tasks.models.bulk import CSVOrdersFile, OrderPrototype
from tasks.models.orders import order_deadline
from tasks.tests.factories import CustomerFactory, OrderFactory

from .base_test_cases import BaseOrderTestCase
from .utils import CreateJobsForReportMixin, CreateOrderCSVTextMixin

DIR_PATH = os.path.dirname(os.path.abspath(__file__))


class BaseBulkUploadTestCase(CreateOrderCSVTextMixin, BaseOrderTestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    SIZE = 3
    url = '/api/bulk/'
    orders_batch_size = 25

    @classmethod
    def setUpTestData(cls):
        super(BaseBulkUploadTestCase, cls).setUpTestData()
        cls.merchant.date_format = Merchant.LITTLE_ENDIAN
        cls.merchant.save()
        cls.customer = CustomerFactory(
            phone='+61499912001',
            email='customer@gm.co',
            name='My customer'
        )
        cls.create_orders()

    @classmethod
    def create_orders(cls):
        cls.orders_list = cls.order_batch_without_save(size=cls.orders_batch_size, customer=cls.customer)

    def send_opened_file(self, csv_text, status_code=status.HTTP_200_OK):
        _file = cStringIO(csv_text)
        data = {
            'file': _file
        }
        resp = self.client.post(self.url, format='multipart', data=data)
        self.assertEqual(resp.status_code, status_code)
        return resp

    def setUp(self):
        self.client.force_authenticate(self.manager)

    def tearDown(self):
        files = CSVOrdersFile.objects.all()
        for f in files.only('file'):
            f.file.delete()

    def process_order_list(self, orders):
        resp = self.post_orders_in_csv(orders)
        task_id = resp.data['task']['id']
        self.client.post('/api/bulk/%d/process' % (task_id,))
        resp = self.client.post('/api/bulk/%d/confirm' % (task_id,))
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        return task_id

    def post_orders_in_csv(self, orders, status_code=status.HTTP_200_OK):
        csv_text = self.create_csv_text(orders, self.merchant.date_format)
        resp = self.send_opened_file(csv_text, status_code)
        return resp


class BulkUploadTestCase(BaseBulkUploadTestCase):
    def _assert_state_params(self, resp):
        self.assertDictEqual({
            'processed': 4,
            'successful': 4,
            'encoding': 'ascii',
            'errors_found': 0,
            'lines': len(self.orders_list) + 1,
            'saved': 0
        }, resp.data['task']['state_params'])

    def _assert_task_data(self, resp, dict_to_cmp):
        self.assertDictEqual({k: resp.data['task'][k] for k in dict_to_cmp}, dict_to_cmp)

    @classmethod
    def setUpTestData(cls):
        super(BulkUploadTestCase, cls).setUpTestData()
        cls.merchant.balance = 1000
        cls.merchant.date_format = Merchant.BIG_ENDIAN
        cls.merchant.enable_labels = cls.merchant.enable_skill_sets = True
        cls.merchant.save()

    def test_bulk_upload_low_balance(self):
        self.merchant.change_balance(-999)
        self.merchant.refresh_from_db()
        resp = self.post_orders_in_csv(self.orders_list, status_code=status.HTTP_200_OK)
        last_message = resp.data['task']['log'][-1]
        self.assertEqual(last_message['message'], 'CSV upload was disabled, because merchant is blocked due to low '
                                                  'balance.')
        self.merchant.change_balance(999)
        self.merchant.refresh_from_db()

    def test_bulk_upload(self):
        # Upload file
        resp = self.post_orders_in_csv(self.orders_list,  status_code=status.HTTP_200_OK)

        self.assertEqual(len(resp.data['orders']), settings.CSV_UPLOAD_PREVIEW_AMOUNT)
        self.assertDictEqual(resp.data['orders'][settings.CSV_UPLOAD_PREVIEW_AMOUNT - 1]['customer'], {
            'email': self.customer.email,
            'name': self.customer.name,
            'phone': self.customer.phone
        })
        self._assert_state_params(resp)
        self._assert_task_data(resp, {
            'status': BulkDelayedUpload.READY,
            'orders_created': 0,
            'method': "WEB",
            'id': BulkDelayedUpload.objects.first().id
        })
        task_id = resp.data['task']['id']
        self.assertTrue(CSVOrdersFile.objects.filter(bulk_id=task_id).exists())

        # Process file
        resp = self.client.post('/api/bulk/%d/process' % (task_id,))
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        task = BulkDelayedUpload.objects.all().last()
        self.assertDictEqual({
            'status': BulkDelayedUpload.COMPLETED,
            'processed': self.orders_batch_size,
            'saved': 0,
            'last_message': 'File processing has been finished. Number of lines that have been processed: %d.'
                            % (self.orders_batch_size,)
        }, {
            'status': task.status,
            'processed': task.state_params['processed'],
            'saved': task.state_params['saved'],
            'last_message': task.log[-1]['message']
        })

        # Confirm file upload
        resp = self.client.post('/api/bulk/%d/confirm' % (task_id,))
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        task = BulkDelayedUpload.objects.all().last()
        self.assertDictEqual({
            'status': BulkDelayedUpload.CONFIRMED,
            'processed': self.orders_batch_size,
            'saved': self.orders_batch_size,
            'last_message': 'All files are saved. Number of tasks that have been saved: %d.' % (self.orders_batch_size,)
        }, {
            'status': task.status,
            'processed': task.state_params['processed'],
            'saved': task.state_params['saved'],
            'last_message': task.log[-1]['message']
        })
        resp = self.client.get('/api/orders?bulk_id=%d&page_size=%s' % (task_id, self.orders_batch_size))
        self.assertEqual(resp.data['count'], self.orders_batch_size)
        self.assertEqual(len(resp.data['results']), self.orders_batch_size)

    def from_file(self, f, context=None, headers=None, size=15):
        context = context or {}
        res = (headers or self.default_headers) + '\n'
        t = Template(f.read())
        return res + '\n'.join(t.render(dict({'ind': ind}, **context)) for ind in xrange(size))

    def test_send_outdated_csv_jobs(self):
        with open(os.path.join(DIR_PATH, 'files/jobs.csv'), 'rt') as _f:
            data = {
                'file': cStringIO(self.from_file(_f, context={'date': '2018-08-22 19:05'}))
            }

        driver = DriverFactory(merchant=self.merchant, member_id=6)
        resp = self.client.post(self.url, format='multipart', data=data)
        task_id = resp.data['task']['id']
        self.assertTrue(CSVOrdersFile.objects.filter(bulk_id=task_id).exists())

        # Process file
        resp = self.client.post('/api/bulk/%d/process' % (task_id,))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_send_job_address_2(self):
        headers = 'Customer name*,Job address*,Job address 2,Driver ID,Job deadline,Comment,Customer_Email,' \
                  'Customer Phone,Job name'
        with open(os.path.join(DIR_PATH, 'files/jobs_address_2.csv'), 'rt') as _f:
            data = {
                'file': cStringIO(self.from_file(_f, headers=headers, size=2))
            }
        DriverFactory(merchant=self.merchant, member_id=6)
        resp = self.client.post(self.url, format='multipart', data=data)
        task_id = resp.data['task']['id']
        self.assertTrue(CSVOrdersFile.objects.filter(bulk_id=task_id).exists())
        resp = self.client.post('/api/bulk/%d/process' % (task_id,))
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.client.post('/api/bulk/%d/confirm' % (task_id,))
        orders = Order.objects.filter(bulk_id=task_id)
        self.assertEqual(orders.count(), 2)
        self.assertFalse(orders.filter(deliver_address__secondary_address='').exists())

    def test_bulk_upload_without_required_fields(self):
        headers = 'Customer name*,Driver ID,Job deadline,Comment,Customer_Email,Customer Phone,Job name'
        csv_text = self.create_csv_text([[], ] * 5, headers=headers)
        resp = self.send_opened_file(csv_text)
        self.assertEqual(len(resp.data['errors']), 0)
        self.assertEqual(resp.data['task']['log'][-1]['message'],
                         'Some required columns are not found or have invalid names. Missing columns: job_address')

    def test_drivers_assigned(self):
        amount = 8
        csv_text = self.create_random_csv({'driver_id': lambda ind: '' if ind % 3 else self.driver.id}, length=amount)

        resp = self.send_opened_file(csv_text)
        self.assertEqual(resp.data['orders'][0]['driver']['member_id'], self.driver.member_id)
        resp = self.client.post('/api/bulk/%d/process' % (resp.data['task']['id'],))
        task_id = resp.data['id']
        resp = self.client.post('/api/bulk/%d/confirm' % (task_id,))
        self.assertEqual(Order.objects.filter(bulk_id=task_id).count(), amount)
        self.assertEqual(Order.objects.filter(status=OrderStatus.ASSIGNED).count(), 3)

    def test_wrong_driver(self):
        amount = 5
        csv_text = self.create_random_csv({'driver_id': lambda ind: '' if ind else 666}, length=amount)
        resp = self.send_opened_file(csv_text)
        self.assertEqual(resp.data['task']['status'], BulkDelayedUpload.FAILED)
        self.assertEqual(len(resp.data['errors']), 1)
        csv_text = self.create_random_csv({'driver_id': lambda ind: 666 if ind and not ind % 4 else ''}, length=amount)
        resp = self.send_opened_file(csv_text)
        task_id = resp.data['task']['id']
        resp = self.client.post('/api/bulk/%d/process' % (task_id,))
        self.assertEqual(len(resp.data['data']), 1)
        self.assertEqual(BulkDelayedUpload.objects.get(id=task_id).status, BulkDelayedUpload.COMPLETED)

    def test_encoding_support(self):
        with open(os.path.join(DIR_PATH, 'files/test_non_ascii_csv.csv'), 'rb') as _f:
            data = {
                'file': BytesIO(_f.read())
            }
            resp = self.client.post(self.url, format='multipart', data=data)
        enc = BulkDelayedUpload.objects.filter(id=resp.data['task']['id']).values('csv_file__encoding').first()
        self.assertNotEqual(enc['csv_file__encoding'], 'ascii')

    def test_small_amount_of_jobs(self):
        with open(os.path.join(DIR_PATH, 'files/test_non_ascii_csv.csv'), 'rb') as _f:
            data = {
                'file': BytesIO(_f.read())
            }
            resp = self.client.post(self.url, format='multipart', data=data)
        task_id = resp.data['task']['id']
        resp = self.client.post('/api/bulk/%d/process' % (task_id,))
        resp = self.client.post('/api/bulk/%d/confirm' % (task_id,))
        self.assertEqual(Order.objects.filter(bulk_id=task_id).count(), 3)

    def test_line_separator_in_comment(self):
        with open(os.path.join(DIR_PATH, 'files/line_separator_issue.csv'), 'rb') as _f:
            data = {
                'file': BytesIO(_f.read())
            }
            resp = self.client.post(self.url, format='multipart', data=data)
        task_id = resp.data['task']['id']
        self.client.post('/api/bulk/%d/process' % (task_id,))
        self.client.post('/api/bulk/%d/confirm' % (task_id,))
        self.assertEqual(Order.objects.filter(bulk_id=task_id).count(), 3)

    def test_sequential_order(self):
        amount = 6
        csv_text = self.create_random_csv({'driver_id': lambda ind: self.driver.id}, length=amount)
        resp = self.send_opened_file(csv_text)
        task_id = resp.data['task']['id']
        resp = self.client.post('/api/bulk/%d/process' % (task_id,))
        self.assertEqual(BulkDelayedUpload.objects.get(id=task_id).status, BulkDelayedUpload.COMPLETED)
        model_lines = [o.line for o in OrderPrototype.objects.filter(bulk_id=task_id).order_by('line')]
        expected_lines = list(xrange(amount))
        self.assertEqual(model_lines, expected_lines)

    @override_settings(BULK_JOB_CREATION_BATCH_SIZE=6, RADARO_CSV={'PANDAS_CHUNKSIZE': 6})
    def test_with_small_bulk_size(self):
        amount = 14
        csv_text = self.create_random_csv({'driver_id': lambda ind: self.driver.id}, length=amount)
        resp = self.send_opened_file(csv_text)
        task_id = resp.data['task']['id']
        resp = self.client.post('/api/bulk/%d/process' % (task_id,))
        self.assertEqual(BulkDelayedUpload.objects.get(id=task_id).status, BulkDelayedUpload.COMPLETED)
        resp = self.client.post('/api/bulk/%d/confirm' % (task_id,))
        self.assertEqual(Order.objects.filter(bulk_id=task_id).count(), amount)
        self.assertEqual(BulkDelayedUpload.objects.get(id=task_id).status, BulkDelayedUpload.CONFIRMED)

    def test_excess_columns_do_not_break_upload(self):
        with open(os.path.join(DIR_PATH, 'files/test_excess_columns.csv'), 'rt', encoding='utf-8') as _f:
            data = {
                'file': cStringIO(_f.read())
            }
            resp = self.client.post(self.url, format='multipart', data=data)
        task_id = resp.data['task']['id']
        self.assertEqual(resp.data['task']['log'][1]['message'], 'Unknown columns are ignored. Columns: wrong_column')
        resp = self.client.post('/api/bulk/%d/process' % (task_id,))
        resp = self.client.post('/api/bulk/%d/confirm' % (task_id,))
        self.assertEqual(Order.objects.filter(bulk_id=task_id).count(), 3)

    def test_csv_upload_with_multiple_labels(self):
        self.label = LabelFactory(merchant=self.merchant)
        self.second_label = LabelFactory(merchant=self.merchant)

        amount = 4
        csv_text = self.create_random_csv({'driver_id': lambda ind: self.driver.id,
                                           'labels': lambda ind: '{};{}'.format(self.label.id,
                                                                                self.second_label.id)},
                                          length=amount)

        resp = self.send_opened_file(csv_text)
        task_id = resp.data['task']['id']
        resp = self.client.post('/api/bulk/%d/process' % (task_id,))
        self.assertEqual(BulkDelayedUpload.objects.get(id=task_id).status, BulkDelayedUpload.COMPLETED)
        resp = self.client.post('/api/bulk/%d/confirm' % (task_id,))
        self.assertEqual(Order.objects.filter(bulk_id=task_id,
                                              labels__in=[self.label.id, self.second_label.id]).distinct().count(),
                         amount)
        self.assertEqual(BulkDelayedUpload.objects.get(id=task_id).status, BulkDelayedUpload.CONFIRMED)

    def test_csv_upload_with_skillsets(self):
        self.skill_set = SkillSetFactory(merchant=self.merchant)
        self.second_skill_set = SkillSetFactory(merchant=self.merchant)
        self.driver.skill_sets.add(self.skill_set, self.second_skill_set)

        amount = 4
        csv_text = self.create_random_csv({'driver_id': lambda ind: self.driver.id,
                                           'skill_sets': lambda ind: '{};{}'.format(self.skill_set.id,
                                                                                    self.second_skill_set.id)},
                                          length=amount)

        resp = self.send_opened_file(csv_text)
        task_id = resp.data['task']['id']
        resp = self.client.post('/api/bulk/%d/process' % (task_id,))
        self.assertEqual(BulkDelayedUpload.objects.get(id=task_id).status, BulkDelayedUpload.COMPLETED)
        resp = self.client.post('/api/bulk/%d/confirm' % (task_id,))
        self.assertEqual(Order.objects.filter(bulk_id=task_id,
                                              skill_sets__in=[self.skill_set.id, self.second_skill_set.id]).distinct().count(),
                         amount)
        self.assertEqual(BulkDelayedUpload.objects.get(id=task_id).status, BulkDelayedUpload.CONFIRMED)

    def test_email_validation(self):
        with open(os.path.join(DIR_PATH, 'files/broken_email.csv'), 'rt', encoding='utf-8') as _f:
            data = {
                'file': cStringIO(_f.read())
            }
            resp = self.client.post(self.url, format='multipart', data=data)
        task_id = resp.data['task']['id']
        self.assertTrue(BulkDelayedUpload.objects.filter(id=task_id, status=BulkDelayedUpload.FAILED).exists())
        self.assertDictEqual(resp.data['errors'][0]['data'], {'customer': {'email': ['Enter a valid email address.']}})

    def test_comment_of_job_saves_and_deadline_3_hours_in_future(self):
        deadline = order_deadline()
        with open(os.path.join(DIR_PATH, 'files/test_non_ascii_csv.csv'), 'rb') as _f:
            data = {
                'file': BytesIO(_f.read())
            }
            resp = self.client.post(self.url, format='multipart', data=data)
        task_id = resp.data['task']['id']
        self.assertGreater(parser.parse(resp.data['orders'][0]['deliver_before']), deadline)
        resp = self.client.post('/api/bulk/%d/process' % (task_id,))
        resp = self.client.post('/api/bulk/%d/confirm' % (task_id,))
        order = Order.objects.get(model_prototype__line=1, model_prototype__bulk_id=task_id)
        self.assertEqual(order.comment, 'Some description')
        self.assertGreater(order.deliver_before, deadline)

    def test_bulk_upload_with_delivery_interval(self):
        delivery_date = (datetime.now() + timedelta(days=1)).date()
        lower_time, upper_time = time(hour=8), time(hour=13, minute=30)

        lower, upper = map(
            lambda t: datetime.combine(delivery_date, t, tzinfo=self.merchant.timezone),
            (lower_time, upper_time)
        )
        lower_str, upper_str = map(lambda dt: dt.astimezone(pytz.UTC).isoformat(), (lower, upper))

        csv_text = self.create_random_csv({'deliver_after': lambda ind: lower_str,
                                           'job_deadline': lambda ind: upper_str}, length=1)
        resp = self.send_opened_file(csv_text)
        task_id = resp.data['task']['id']
        self.client.post('/api/bulk/%d/process' % (task_id,))
        self.assertEqual(BulkDelayedUpload.objects.get(id=task_id).status, BulkDelayedUpload.COMPLETED)
        self.client.post('/api/bulk/%d/confirm' % (task_id,))
        self.assertEqual(BulkDelayedUpload.objects.get(id=task_id).status, BulkDelayedUpload.CONFIRMED)
        self.assertTrue(Order.objects.filter(bulk_id=task_id, deliver_after=lower, deliver_before=upper)
                        .exists())

    def test_bulk_upload_with_pickup_interval(self):
        pickup_date = (datetime.now() + timedelta(days=1)).date()
        pickup_after_time, pickup_before_time, deliver_before_time = time(hour=13), time(hour=15), time(hour=20)

        pickup_after, pickup_before, deliver_before = map(
            lambda t: datetime.combine(pickup_date, t, tzinfo=self.merchant.timezone),
            (pickup_after_time, pickup_before_time, deliver_before_time))

        pickup_after_str, pickup_before_str, deliver_before_str = map(
            lambda dt: dt.astimezone(pytz.UTC).isoformat(), (pickup_after, pickup_before, deliver_before))

        csv_text = self.create_random_csv({'pickup_after': lambda ind: pickup_after_str,
                                           'pickup_deadline': lambda ind: pickup_before_str,
                                           'job_deadline': lambda ind: deliver_before_str}, length=1)
        resp = self.send_opened_file(csv_text)
        task_id = resp.data['task']['id']
        self.client.post('/api/bulk/%d/process' % (task_id,))
        self.assertEqual(BulkDelayedUpload.objects.get(id=task_id).status, BulkDelayedUpload.COMPLETED)
        self.client.post('/api/bulk/%d/confirm' % (task_id,))
        self.assertEqual(BulkDelayedUpload.objects.get(id=task_id).status, BulkDelayedUpload.CONFIRMED)
        self.assertTrue(Order.objects.filter(bulk_id=task_id, pickup_after=pickup_after, pickup_before=pickup_before)
                        .exists())


class PerformanceUploadTestCase(CreateJobsForReportMixin, BaseBulkUploadTestCase):
    orders_batch_size = 3000

    @tag('performance')
    def test_large_csv_upload(self):
        self.merchant.balance = 1000000
        self.merchant.save()
        self.client.force_authenticate(self.manager)
        for scale in (0.03333333, 0.23333333, 0.5, 1, 0.3):
            size = int(scale * self.orders_batch_size)
            measurements = []
            tries = 3
            performance = PerformanceMeasure()
            for ind in xrange(tries):
                print(
                    '\nMeasurement {} with batch: {}\n========================\n'
                        .format(ind + 1, size),
                    performance
                )
                sid = transaction.savepoint()
                resp = self.post_orders_in_csv(self.orders_list[:size])
                resp = self.client.post('/api/bulk/%d/process' % (resp.data['task']['id'],))
                task_id = resp.data['id']
                resp = self.client.post('/api/bulk/%d/confirm' % (task_id,))
                perf, diff = performance.measure()
                print(perf, diff)
                measurements.append(diff)
                transaction.savepoint_rollback(sid)
            print('Average time: {} sec'.format(sum(m.time for m in measurements) / 3.))
            print('Afterall memory growth: {} MB'.format(sum(m.memory for m in measurements)))


class DatesUploadTestCase(BaseBulkUploadTestCase):
    CSV_FILENAME = 'test_2.csv'
    orders_batch_size = 5

    @classmethod
    def create_orders(cls):
        next_year_may = (timezone.now() + timedelta(days=365)).replace(month=5, microsecond=0)
        cls.dates = [next_year_may.replace(day=x).astimezone(cls.merchant.timezone)
                     for x in range(1, cls.orders_batch_size + 1)]
        cls.orders = [OrderFactory(
            driver=None,
            customer=cls.customer,
            deliver_before=dt
        ) for dt in cls.dates]

    def test_date_format_of_bulk_upload(self):
        for _format, _ in Merchant.date_formats:
            self.merchant.date_format = _format
            self.merchant.save()
            bulk_id = self.process_order_list(self.orders)
            order_dates = Order.objects\
                .filter(bulk_id=bulk_id)\
                .order_by('deliver_before')\
                .values_list('deliver_before', flat=True)
            validate_dates = [d.astimezone(self.merchant.timezone) == self.dates[ind]
                              for ind, d in enumerate(order_dates)]
            self.assertTrue(all(validate_dates))


class PhoneFormatsUploadTestCase(BaseBulkUploadTestCase):
    CSV_FILENAME = 'test_3.csv'

    GERMANY = 'DE'

    phones = {
        (countries.AUSTRALIA,): (
            {'sent': '+61419594073', 'expected': '+61419594073'},
            {'sent': '61419594074', 'expected': '+61419594074'},
            {'sent': '', 'expected': ''},
            {'sent': '405590835', 'expected': '+61405590835'},
            {'sent': '0423 421 405', 'expected': '+61423421405'},
            {'sent': '0438004888', 'expected': '+61438004888'},
            {'sent': '+61 438-004-889', 'expected': '+61438004889'}
        ),
        (GERMANY, ): (
            {'sent': '385747678', 'expected': '+49385747678'},
            {'sent': '09461 198884', 'expected': '+499461198884'},
            {'sent': '07724-156550', 'expected': '+497724156550'},
            {'sent': '09255756735', 'expected': '+499255756735'},
            {'sent': '493085827327', 'expected': '+493085827327'},
            {'sent': '4949415366', 'expected': '+4949415366'},
            {'sent': '01570-1344401', 'expected': '+4915701344401'},
            {'sent': '01620-238018', 'expected': '+491620238018'},
            {'sent': '', 'expected': ''}
        ),
        (countries.AUSTRALIA, GERMANY): (
            {'sent': '+61419594073', 'expected': '+61419594073'},
            {'sent': '61419594074', 'expected': '+61419594074'},
            {'sent': '+61 438-004-889', 'expected': '+61438004889'},
            {'sent': '49 9461 198884', 'expected': '+499461198884'},
            {'sent': '+497724-156550', 'expected': '+497724156550'},
            {'sent': '', 'expected': ''}
        )
    }

    @classmethod
    def setUpClass(cls):
        super(PhoneFormatsUploadTestCase, cls).setUpClass()
        cls.Order = namedtuple('OrderTuple', 'deliver_address comment job_name customer')

    def create_file_with_phones(self):
        resp = self.post_orders_in_csv(self.orders)
        return resp

    def run_test_for_country_merchant(self):
        countries = tuple(self.merchant.countries)
        resp = self.create_file_with_phones()
        task_id = resp.data['task']['id']

        # Process file
        resp = self.client.post('/api/bulk/%d/process' % (task_id,))
        resp = self.client.post('/api/bulk/%d/confirm' % (task_id,))
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        customers = Customer.objects.exclude(id=self.customer.id).filter(merchant=self.merchant)
        for p in self.phones[countries]:
            self.assertTrue(customers.filter(phone=p['expected']).exists())

    def default_customers(self, phones):
        return [Customer(
            name='John Doe{}'.format(ind),
            phone=phone['sent'],
            email='example{}@example.com'.format(ind)
        ) for ind, phone in enumerate(phones)]

    def test_au_phone_formats(self):
        self.merchant.countries = [countries.AUSTRALIA, ]
        self.merchant.save()
        self.customers = self.default_customers(self.phones[(countries.AUSTRALIA,)])
        self.orders = [self.Order(
            deliver_address='Melbourne, VIC {}'.format(3060 + ind),
            comment='Test task in csv',
            job_name='John\'s job',
            customer=c
        ) for ind, c in enumerate(self.customers)]
        self.run_test_for_country_merchant()

    def test_de_phone_formats(self):
        self.merchant.countries = [self.GERMANY, ]
        self.merchant.save()
        self.customers = self.default_customers(self.phones[(self.GERMANY, )])
        self.orders = [self.Order(
            deliver_address='Germany, Berlin',
            comment='Test task in csv',
            job_name='John\'s job',
            customer=c
        ) for ind, c in enumerate(self.customers)]
        self.run_test_for_country_merchant()

    def test_au_and_de_phone_formats(self):
        self.merchant.countries = [countries.AUSTRALIA, self.GERMANY]
        self.merchant.save()
        self.customers = self.default_customers(self.phones[(countries.AUSTRALIA, self.GERMANY)])
        self.orders = [self.Order(
            deliver_address='Germany, Berlin',
            comment='Test task in csv',
            job_name='John\'s job',
            customer=c
        ) for ind, c in enumerate(self.customers)]
        self.run_test_for_country_merchant()
