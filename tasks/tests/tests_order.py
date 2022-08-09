from __future__ import absolute_import, unicode_literals

import copy
import io
import random
from datetime import datetime as dt
from datetime import timedelta

import django
from django.forms.models import model_to_dict
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.timezone import now

from rest_framework import status

import mock
import pytz
from dateutil import parser
from factory.compat import UTC
from factory.fuzzy import FuzzyChoice
from PIL import Image

from base.factories import DriverFactory, ManagerFactory
from base.utils import dictionaries_difference, get_fuzzy_location
from documents.tests.factories import TagFactory
from driver.factories import DriverLocationFactory
from merchant.factories import MerchantFactory, SkillSetFactory
from notification.tests.mixins import NotificationTestMixin
from tasks.api.legacy.serializers.orders import OrderDeadlineSerializer
from tasks.mixins.order_status import OrderStatus
from tasks.models import OrderLocation
from tasks.models.orders import Order
from tasks.tests.factories import CustomerFactory, OrderFactory
from tasks.utils import create_order_event_times, create_order_for_test

from .base_test_cases import BaseOrderTestCase


class OrderTestCase(NotificationTestMixin, BaseOrderTestCase):
    @classmethod
    def setUpTestData(cls):
        super(OrderTestCase, cls).setUpTestData()
        loc = DriverLocationFactory(member=cls.driver)
        cls.driver.last_location = loc
        cls.driver.save()
        cls.job_data = {
            'customer': {
                'name': 'Test Customer'
            },
            'deliver_address': {
                'address': 'Eaton Gate, 2 Sloane Square, South Kensington, London SW1W 9BJ, UK',
                'location': '51.4938516,-0.1567399',
                'raw_address': 'Eaton Gate, 2 Sloane Square',
            }
        }

    def setUp(self):
        self.order = self.create_default_order(sub_branding=self.sub_branding, driver=None)
        self.second_merchant = MerchantFactory(notify_of_not_assigned_orders=True, enable_skill_sets=True)
        self.skill_set = SkillSetFactory(merchant=self.second_merchant)
        self.second_merchant.required_skill_sets_for_notify_orders.add(self.skill_set)
        self.second_merchant_manager = ManagerFactory(merchant=self.second_merchant)
        self.second_merchant_customer = CustomerFactory(merchant=self.second_merchant)
        self.second_merchant_first_driver = DriverFactory(merchant=self.second_merchant)
        self.second_merchant_first_driver.skill_sets.add(self.skill_set)
        self.second_merchant_second_driver = DriverFactory(merchant=self.second_merchant)
        self.second_merchant_second_driver.skill_sets.add(self.skill_set)
        self.second_merchant_manager = ManagerFactory(merchant=self.second_merchant)

    def test_order_creation(self):
        self.merchant.notify_of_not_assigned_orders = True
        self.merchant.enable_skill_sets = True
        self.merchant.save()

        skill_set = SkillSetFactory(merchant=self.merchant)
        self.driver.skill_sets.add(skill_set)
        self.merchant.required_skill_sets_for_notify_orders.add(skill_set)

        job_data = copy.deepcopy(self.job_data)
        job_data['skill_sets'] = [skill_set.id, ]

        self.client.force_authenticate(self.manager)

        with self.mock_send_versioned_push() as send_push_mock:
            resp = self.client.post('/api/orders/', data=job_data)
            # This merchant has 1 driver
            self.assertEqual(send_push_mock.call_count, 1)

        self.assertEqual(resp.status_code, 201)
        Order.objects.get(order_id=resp.data['order_id'])

    def test_create_order_by_driver(self):
        self.client.force_authenticate(self.second_merchant_first_driver)

        job_data = copy.deepcopy(self.job_data)
        job_data['skill_sets'] = [self.skill_set.id, ]
        resp = self.client.post('/api/orders/', data=job_data)
        self.assertEqual(resp.status_code, 403)

        self.second_merchant.driver_can_create_job = True
        self.second_merchant.save()

        with self.mock_send_versioned_push() as send_push_mock:
            resp = self.client.post('/api/orders/', data=job_data)
            # This merchant has 2 driver. First driver created a job, the push came to the second driver
            self.assertEqual(send_push_mock.call_count, 1)

        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(order_id=resp.data['order_id']).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, Order.NOT_ASSIGNED)

    def test_create_assigned_order_by_driver(self):
        self.client.force_authenticate(self.second_merchant_second_driver)
        test_job_data = self.job_data.copy()
        test_job_data.update(driver=self.second_merchant_first_driver.id, status=Order.ASSIGNED)

        resp = self.client.post('/api/orders/', data=test_job_data)
        self.assertEqual(resp.status_code, 403)

        self.second_merchant.driver_can_create_job = True
        self.second_merchant.save()

        resp = self.client.post('/api/orders/', data=test_job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(order_id=resp.data['order_id']).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, Order.ASSIGNED)
        self.assertEqual(order.driver_id, self.second_merchant_first_driver.id)

    def _create_non_finished_orders(self):
        self.default_order_batch(size=50)
        self.default_order_batch(
            size=50,
            status=Order.ASSIGNED
        )
        self.default_order_batch(
            size=100,
            status=Order.IN_PROGRESS
        )

    def test_order_list_sorting_for_manager(self):
        self._create_non_finished_orders()
        current_time = now()
        latest_hours = 24 * 7
        for o in Order.objects.filter(status=Order.IN_PROGRESS):
            h = random.randint(1, latest_hours-1)
            fake_time = current_time + timedelta(hours=h)
            o.status = 'delivered'
            o.end_order()
            Order.objects.filter(pk=o.pk).update(updated_at=fake_time)
        self.client.force_authenticate(self.manager)
        for t in [{
            'params': {'group': 'active'},
            'assertor': self.assertGreaterEqual,
            'field': 'deliver_before'
        }, {
            'params': {'status': 'delivered'},
            'assertor': self.assertLessEqual,
            'field': 'updated_at'
        }]:
            with mock.patch('django.utils.timezone.now') as get_now:
                get_now.return_value = current_time + timedelta(hours=2*latest_hours)
                resp = self.client.get('/api/orders/', data=t['params'])
                res = resp.data['results']
                self.assertEqual(resp.status_code, 200)
                for ind in range(0, len(res) - 1):
                    t['assertor'](parser.parse(res[ind + 1][t['field']]), parser.parse(res[ind][t['field']]))

    def test_nonactive_orders_list_sorting_for_driver(self):
        self._create_non_finished_orders()
        current_time = now()
        latest_hours = 24 * 7
        for i, o in enumerate(Order.objects.filter(status=Order.IN_PROGRESS)):
            h = random.randint(1, latest_hours-1)
            fake_time = current_time + timedelta(hours=h)
            o.status = 'delivered' if i % 2 else 'failed'
            o.end_order()
            Order.objects.filter(pk=o.pk).update(updated_at=fake_time)
        self.client.force_authenticate(self.driver)
        for t in [{
            'params': {'group': 'failed', 'page_size': 100},
            'assertor': self.assertLessEqual,
            'field': 'updated_at',
            'requested_at': current_time + timedelta(hours=latest_hours)
        }, {
            'params': {'group': 'completed', 'page_size': 100},
            'assertor': self.assertLessEqual,
            'field': 'updated_at',
            'requested_at': current_time + timedelta(hours=latest_hours)
        }, {
            'params': {'group': 'archived', 'page_size': 100},
            'assertor': self.assertLessEqual,
            'field': 'updated_at',
            'requested_at': current_time + timedelta(hours=2*latest_hours)
        }]:
            with mock.patch('django.utils.timezone.now') as get_now:
                get_now.return_value = t['requested_at']
                resp = self.client.get('/api/orders/', data=t['params'])
                res = resp.data['results']
                self.assertEqual(resp.status_code, 200)
                for ind in range(0, len(res) - 1):
                    t['assertor'](parser.parse(res[ind + 1][t['field']]), parser.parse(res[ind][t['field']]))

    def test_assign_driver(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.patch('/api/orders/%s/' % self.order.order_id, {
            'driver': self.driver.id,
            'status': Order.ASSIGNED,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['driver'], self.driver.id)
        self.assertEqual(resp.json()['status'], Order.ASSIGNED)

    def _test_driver_orders(self, version=''):
        self.order.driver = self.driver
        self.order.status = 'assigned'
        self.order.save()

        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api{}/orders/'.format(version))
        self.assertGreater(resp.data['count'], 0)
        self.assertContains(resp, self.order.order_id)
        self.assertNotContains(resp, Order.NOT_ASSIGNED)
        return resp

    def test_driver_orders(self):
        self._test_driver_orders()

    def test_driver_orders_v2(self):
        resp = self._test_driver_orders('/v2')
        _id = resp.data['results'][0]['server_entity_id']
        self.assertTrue(Order.objects.filter(id=_id).exists())

    def _test_driver_not_assigned_orders(self, version=''):
        self.second_merchant.in_app_jobs_assignment = True
        self.second_merchant.save()
        self.client.force_authenticate(self.second_merchant_first_driver)
        tomorrow_date = timezone.now() + timedelta(days=1)
        yesterday = timezone.now() - timedelta(days=1)

        order = self.create_order(
            self.second_merchant_manager,
            self.second_merchant,
            self.second_merchant_customer,
            status=OrderStatus.NOT_ASSIGNED,
            deliver_before=tomorrow_date,
            driver=None
        )

        resp = self.client.get('/api{}/orders/'.format(version))
        self.assertGreater(resp.data['count'], 0)
        self.assertContains(resp, order.order_id)

        _order = Order.objects.filter(order_id=order.order_id)
        _order.update(deadline_notified=True, deadline_passed=True, deliver_before=yesterday)

        resp = self.client.get('/api{}/orders/'.format(version))
        self.assertEqual(resp.data['count'], 0)

        order.deliver_before = tomorrow_date
        order.save()

        resp = self.client.get('/api{}/orders/'.format(version))
        self.assertGreater(resp.data['count'], 0)
        self.assertContains(resp, order.order_id)

    def test_driver_not_assigned_orders_v1(self):
        self._test_driver_not_assigned_orders()

    def test_driver_not_assigned_orders_v2(self):
        self._test_driver_not_assigned_orders(version='/v2')

    def test_manager_orders_list_getting(self):
        OrderFactory.create_batch(
            size=10,
            merchant=self.merchant,
            manager=self.manager,
        )
        self.client.force_authenticate(self.manager)
        for url, tp in (('/api/orders/', str), ('/api/latest/orders/', dict)):
            resp = self.client.get(url)
            resp_json_data = resp.json()
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(type(resp_json_data['results'][0]['deliver_address']['location']), tp)
            self.assertGreater(resp_json_data.get('count'), 0)

    def test_submanager_orders_list_getting(self):
        OrderFactory.create_batch(
            size=10,
            merchant=self.merchant,
            manager=self.manager,
            sub_branding=self.sub_branding,
            status=OrderStatus.ASSIGNED,
        )
        self.client.force_authenticate(self.submanager)
        resp = self.client.get('/api/web/subbrand/orders/')
        resp_json_data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(resp_json_data.get('count'), 0)

    def test_order_deletion(self):
        self.client.force_authenticate(self.manager)
        request_url = '/api/orders/{0}/'.format(self.order.order_id)

        with mock.patch('webhooks.celery_tasks.send_external_event') as send_external_event:
            resp = self.client.delete(request_url)
            self.assertTrue(send_external_event.called)
            self.assertEqual(send_external_event.call_args.args[3], 'job.deleted')

        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Order.objects.filter(id=self.order.id).exists())
        self.assertTrue(Order.all_objects.filter(id=self.order.id).exists())

    def test_manager_active_orders_list_getting(self):
        OrderFactory.create_batch(
            size=20,
            merchant=self.merchant,
            manager=self.manager,
            sub_branding=self.sub_branding,
            status=FuzzyChoice(Order._status_dict.values()).fuzz()
        )
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/orders/active/')
        active_orders_count = Order.objects.filter(status__in=OrderStatus.status_groups.UNFINISHED).count()
        self.assertEqual(resp.data['count'], active_orders_count)

    def test_many_submanager_orders_list_getting(self):
        OrderFactory.create_batch(
            size=20,
            merchant=self.merchant,
            manager=self.manager,
            sub_branding=self.sub_branding,
            status=FuzzyChoice(Order._status_dict.values()).fuzz()
        )
        self.client.force_authenticate(self.submanager)
        resp = self.client.get('/api/web/subbrand/orders/')
        orders_count = Order.objects.exclude(status=OrderStatus.NOT_ASSIGNED)
        orders_count = orders_count.filter(sub_branding=self.sub_branding).count()
        self.assertEqual(resp.data['count'], orders_count)

    def test_orders_path_getting(self):
        self.order.status = OrderStatus.ASSIGNED
        self.order.driver = self.driver
        locations = list(DriverLocationFactory.create_batch(size=10, member=self.driver))
        self.order.path = {'full': [loc.location for loc in locations]}
        self.order.save()

        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/orders/%s/path/' % self.order.order_id)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['path']), len(locations))

    def test_assign_time_getting(self):
        day_before = dt.now(tz=UTC) - timedelta(days=1)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = day_before
            cur_time = dt.combine(django.utils.timezone.now().date(), dt.min.time()).replace(tzinfo=UTC)
            switch_times = create_order_event_times(cur_time, to_status=OrderStatus.IN_PROGRESS)
            order_id = create_order_for_test(
                test_class_item=self,
                manager=self.manager,
                driver=self.driver,
                order_data={
                    'customer': {'name': 'Test Customer', },
                    'deliver_address': {'location': get_fuzzy_location(), }
                },
                switching_status_times=switch_times
            ).order_id

        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/orders/%s/assign_time/' % order_id)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(parser.parse(resp.data['assign_time']).astimezone(tz=pytz.UTC),
                         switch_times[OrderStatus.ASSIGNED])

    def test_assign_time_getting_without_assign_event(self):
        """ Order that created with assigned status, so there is no assign event"""

        self.second_merchant.driver_can_create_job = True
        self.second_merchant.save()
        self.client.force_authenticate(self.second_merchant_first_driver)
        day_before = dt.now(tz=UTC) - timedelta(days=1)
        data = {
            'driver': self.second_merchant_first_driver.id,
            'status': OrderStatus.ASSIGNED,
            'customer': {'name': 'Test Customer', },
            'deliver_address': {'location': get_fuzzy_location(), }
        }
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = day_before
            resp = self.client.post('/api/orders/', data=data)
            order_id = resp.data['order_id']

        self.client.force_authenticate(self.second_merchant_manager)
        resp = self.client.get('/api/orders/%s/assign_time/' % order_id)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(parser.parse(resp.data['assign_time']).astimezone(tz=pytz.UTC), day_before)

    def test_last_comments_getting(self):
        first_order_creation_date = dt.now(tz=UTC) - timedelta(days=10)

        orders_id = []
        for delta_day in range(7):
            order_data = {
                'customer': {'name': 'Test Customer', },
                'deliver_address': {'location': get_fuzzy_location(), }
            }
            with mock.patch('django.utils.timezone.now') as mock_now:
                mock_now.return_value = first_order_creation_date + timedelta(days=delta_day)
                cur_time = dt.combine(django.utils.timezone.now().date(), dt.min.time()).replace(tzinfo=UTC)
                switch_times = create_order_event_times(cur_time)
                order_id = create_order_for_test(
                    test_class_item=self,
                    manager=self.manager,
                    driver=self.driver,
                    order_data=order_data,
                    switching_status_times=switch_times
                ).order_id
                order = Order.objects.get(order_id=order_id)
                customer_uidb64 = urlsafe_base64_encode(force_bytes(order.customer.pk))
                self.client.patch('/api/customers/%s/orders/%s/rating/' % (customer_uidb64, str(order.order_token)),
                                  data={'customer_comment': 'Comment #%s' % delta_day, })
                orders_id.insert(0, order.order_id)

        self.client.force_authenticate(self.manager)

        resp = self.client.get('/api/orders/last_comments/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp_orders_id = list(map(lambda x: x['order_id'], resp.data))
        self.assertListEqual(resp_orders_id, orders_id[:len(resp_orders_id)])

    @staticmethod
    def _date2datetime(date, merchant):
        return dt(year=date.year, month=date.month, day=date.day, tzinfo=merchant.timezone)

    def test_orders_table_getting(self):
        first_order_creation_date = dt.now(tz=UTC) - timedelta(days=20)
        request_date = {
            'from': first_order_creation_date.date(),
            'to': (first_order_creation_date + timedelta(days=13)).date(),
        }

        for delta_day in range(19):
            for i in range(3):
                order_data = {
                    'customer': {'name': 'Test customer', },
                    'deliver_address': {'location': get_fuzzy_location(), }
                }
                with mock.patch('django.utils.timezone.now') as mock_now:
                    mock_now.return_value = dt.combine(first_order_creation_date + timedelta(days=delta_day), dt.min.time()).replace(tzinfo=UTC)
                    cur_time = (django.utils.timezone.now() + timedelta(minutes=50*i)).replace(tzinfo=UTC)
                    switch_times = create_order_event_times(cur_time)
                    create_order_for_test(
                        test_class_item=self,
                        manager=self.manager,
                        driver=self.driver,
                        order_data=order_data,
                        switching_status_times=switch_times
                    )

        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/orders/table/', data={
            'driver_id': '',
            'date_from': request_date['from'],
            'date_to': request_date['to'],
        })

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        orders_from_db = Order.objects.filter(
            merchant=self.merchant,
            created_at__gte=self._date2datetime(request_date['from'], self.merchant),
            created_at__lte=self._date2datetime(request_date['to'], self.merchant)
        )
        self.assertEqual(resp.data['count'], orders_from_db.count())

    def test_order_change(self):
        trackable_fields = {'title', 'label', 'customer', 'deliver_address', 'deliver_before',
                            'description', 'comment', 'sub_branding'}
        unchanged_fields = ('customer', )
        delivery_date = timezone.now() + timedelta(days=1)
        data = {"comment": "Test comment for update",
                "deliver_before": delivery_date.isoformat(),
                "customer": {
                        "id": self.order.customer.id,
                        "name": self.order.customer.name,
                        "phone": self.order.customer.phone,
                        "email": self.order.customer.email
                    }
                }
        old_dict = model_to_dict(self.order, fields=trackable_fields)
        self.client.force_authenticate(self.manager)
        resp = self.client.patch('/api/orders/%s/' % self.order.order_id, data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['comment'], data['comment'])

        self.order.refresh_from_db()
        new_dict = model_to_dict(self.order, fields=trackable_fields)
        key_diff, _, _ = dictionaries_difference(old_dict, new_dict)
        self.assertEqual(set(data).intersection(key_diff).intersection(unchanged_fields), set())

    def test_order_getting_v2(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/v2/orders/%s/' % self.order.id)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['id'], self.order.id)

    def test_not_assigned_order_getting_by_submanager_v2(self):
        self.client.force_authenticate(self.submanager)
        resp = self.client.get('/api/web/subbrand/orders/%s/' % self.order.id)
        self.assertEqual(resp.status_code, 404)

    def test_assigned_order_getting_by_submanager_v2(self):
        order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            driver=self.driver,
            status=Order.ASSIGNED,
            customer=self.customer,
            sub_branding=self.sub_branding,
        )
        self.client.force_authenticate(self.submanager)
        resp = self.client.get('/api/web/subbrand/orders/%s/' % order.id)
        self.assertEqual(resp.status_code, 200)

    def test_submanager_drivers_list_getting(self):
        self.client.force_authenticate(self.submanager)
        resp = self.client.get('/api/web/subbrand/drivers/')
        resp_json_data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(resp_json_data.get('count'), 0)

    def test_order_deadlines(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/v2/orders/deadlines/')
        self.assertEqual(resp.status_code, 200)
        item = resp.data['results'][0]
        self.assertDictEqual(item, OrderDeadlineSerializer(Order.objects.get(id=item['id'])).data)

    def test_save_raw_address_field(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.post('/api/orders/', data=self.job_data)
        self.assertEqual(resp.status_code, 201)
        order_location_1 = OrderLocation.objects.filter(deliver__order_id=resp.data['order_id']).first()
        self.assertEqual(order_location_1.raw_address, self.job_data['deliver_address']['raw_address'])

        changed_job_data = copy.deepcopy(self.job_data)
        changed_job_data['deliver_address']['raw_address'] += ', South Kensington'

        resp = self.client.post('/api/orders/', data=changed_job_data)
        self.assertEqual(resp.status_code, 201)
        order_location_2 = OrderLocation.objects.filter(deliver__order_id=resp.data['order_id']).first()
        self.assertEqual(order_location_2.raw_address, changed_job_data['deliver_address']['raw_address'])

        self.assertNotEqual(order_location_1.id, order_location_2.id)

    def test_save_address_2(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.post('/api/orders/', data=self.job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(order_id=resp.data['order_id']).first()
        self.assertEqual(order.deliver_address.secondary_address, '')

        changed_job_data = copy.deepcopy(self.job_data)
        changed_job_data['deliver_address_2'] = '22'
        resp = self.client.post('/api/orders/', data=changed_job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(order_id=resp.data['order_id']).first()
        self.assertEqual(order.deliver_address.secondary_address, changed_job_data['deliver_address_2'])

        resp = self.client.patch('/api/v2/orders/%s/' % self.order.id, {'deliver_address_2': '123'})
        order = Order.objects.filter(order_id=resp.data['order_id']).first()
        self.assertEqual(order.deliver_address.secondary_address, '123')

    def test_save_address_2_by_driver(self):
        changed_job_data = copy.deepcopy(self.job_data)
        changed_job_data['deliver_address_2'] = '22'
        self.client.force_authenticate(self.second_merchant_first_driver)
        self.second_merchant.driver_can_create_job = True
        self.second_merchant.save()

        resp = self.client.post('/api/orders/', data=changed_job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(order_id=resp.data['order_id']).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.deliver_address.secondary_address, changed_job_data['deliver_address_2'])

    def test_job_capacity(self):
        capacity = 600
        job_data = copy.deepcopy(self.job_data)
        job_data.update({'capacity': capacity})

        self.client.force_authenticate(self.second_merchant_manager)
        resp = self.client.post('/api/orders', data=job_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        self.second_merchant.enable_job_capacity = True
        self.second_merchant.save()
        resp = self.client.post('/api/orders', data=job_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        order = Order.objects.filter(order_id=resp.data['order_id']).first()
        self.assertEqual(order.capacity, capacity)

    def test_assign_job_with_high_capacity(self):
        self.second_merchant.enable_job_capacity = True
        self.second_merchant.save()
        self.second_merchant_first_driver.car.capacity = 1000
        self.second_merchant_first_driver.car.save()
        self.test_order = OrderFactory(merchant=self.second_merchant,
                                       manager=self.second_merchant_manager,
                                       capacity=1500)

        self.client.force_authenticate(self.second_merchant_manager)
        resp = self.client.patch(
            '/api/orders/{}/'.format(self.test_order.order_id), data={'driver': self.second_merchant_first_driver.id,
                                                                      'status': OrderStatus.ASSIGNED}
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        self.test_order.capacity = 800
        self.test_order.save()
        self.test_order.refresh_from_db()
        resp = self.client.patch(
            '/api/orders/{}/'.format(self.test_order.order_id), data={'driver': self.second_merchant_first_driver.id,
                                                                      'status': OrderStatus.ASSIGNED}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def _generate_image(self):
        file = io.BytesIO()
        image = Image.new('RGBA', size=(100, 100), color=(155, 0, 0))
        image.save(file, 'png')
        file.name = 'test.png'
        file.seek(0)
        return file

    def test_order_documents(self):
        document = self._generate_image()
        order = self.order
        merchant = self.merchant
        tags = TagFactory.create_batch(merchant=merchant, size=3)

        order.driver = self.driver
        order.status = order.ASSIGNED
        order.save()

        self.client.force_authenticate(self.driver)

        path = '/api/v2/orders/%s/upload_confirmation_document/' % self.order.id
        data = {
                'document': document,
                'name': 'bla',
                'tag': tags[0].id,
            }

        merchant.enable_delivery_confirmation_documents = False
        merchant.enable_delivery_confirmation = False
        merchant.save()
        document.seek(0)
        resp = self.client.patch(path, data=data, format='multipart')
        self.assertEqual(resp.status_code, 403)

        merchant.enable_delivery_confirmation_documents = True
        merchant.enable_delivery_confirmation = True
        merchant.save()
        document.seek(0)

        with mock.patch('webhooks.celery_tasks.send_external_event') as send_external_event:
            resp = self.client.patch(path, data=data, format='multipart')
            external_data = send_external_event.call_args[0][1]
            self.assertEqual(len(external_data['old_values']['order_confirmation_documents']), 0)
            self.assertEqual(len(external_data['new_values']['order_confirmation_documents']), 1)
            self.assertEqual(external_data['new_values']['order_confirmation_documents'][0]['name'], data['name'])

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['order_confirmation_documents']), 1)
        order.refresh_from_db()
        self.assertEqual(order.order_confirmation_documents.count(), 1)
        self.assertEqual(order.order_confirmation_documents.first().tags.count(), 1)

        # Duplicate upload succeeds, but no duplicate is actually created
        document.seek(0)
        resp = self.client.patch(path, data=data, format='multipart')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(order.order_confirmation_documents.count(), 1)

        document.seek(0)
        data = {
            'document': document,
            'name': 'bla 2',
            'tag': tags[0].id,
        }
        # Checking that webhook always returns one new document
        with mock.patch('webhooks.celery_tasks.send_external_event') as send_external_event:
            resp = self.client.patch(path, data=data, format='multipart')
            external_data = send_external_event.call_args[0][1]
            self.assertEqual(len(external_data['old_values']['order_confirmation_documents']), 0)
            self.assertEqual(len(external_data['new_values']['order_confirmation_documents']), 1)
            self.assertEqual(external_data['new_values']['order_confirmation_documents'][0]['name'], data['name'])

        order.refresh_from_db()
        self.assertEqual(order.order_confirmation_documents.count(), 2)

    def test_driver_orders_list_getting(self):
        OrderFactory.create_batch(
            size=10,
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.IN_PROGRESS,
            driver=self.driver,
        )
        self.client.force_authenticate(self.driver)
        resp = self.client.get('/api/mobile/orders/v1/')
        resp_json_data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(type(resp_json_data['results'][0]['deliver_address']['location']), dict)
        self.assertGreater(resp_json_data.get('count'), 0)
