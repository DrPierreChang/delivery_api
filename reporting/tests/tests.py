from __future__ import unicode_literals

from collections import namedtuple
from datetime import datetime as dt
from datetime import timedelta

import django.utils.timezone
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

import mock
from factory import fuzzy
from factory.compat import UTC

from base.api.legacy.serializers import SmallUserInfoSerializer
from base.factories import DriverFactory, ManagerFactory
from base.utils import get_fuzzy_location
from merchant.factories import MerchantFactory, SubBrandingFactory
from merchant.models import Label
from reporting.models import ExportReportInstance
from tasks.mixins.order_status import OrderStatus
from tasks.models.orders import Order
from tasks.tests.factories import OrderFactory
from tasks.utils import create_order_event_times, create_order_for_test

from ..models import Event


class ReportsTestCase(APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    @classmethod
    def setUpTestData(cls):
        super(ReportsTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory()
        cls.driver = DriverFactory(merchant=cls.merchant)
        cls.manager = ManagerFactory(merchant=cls.merchant)

    def test_get_orders_reports_list(self):
        first_order_creation_date = dt.now(tz=UTC) - timedelta(days=10)
        request_time = {
            'from': dt.combine(first_order_creation_date.date(), dt.min.time()).replace(tzinfo=UTC),
            'to': dt.combine((first_order_creation_date + timedelta(days=3)).date(), dt.min.time()).replace(tzinfo=UTC)
        }

        for delta_day in range(5):
            order_data = {
                'customer': {'name': 'Test Customer', },
                'deliver_address': {'location': get_fuzzy_location(), }
            }
            with mock.patch('django.utils.timezone.now') as mock_now:
                mock_now.return_value = first_order_creation_date + timedelta(days=delta_day)
                cur_time = dt.combine(django.utils.timezone.now().date(), dt.min.time()).replace(tzinfo=UTC)
                switch_times = create_order_event_times(cur_time)
                create_order_for_test(
                    test_class_item=self,
                    manager=self.manager,
                    driver=self.driver,
                    order_data=order_data,
                    switching_status_times=switch_times
                )

        self.client.force_authenticate(self.manager)

        for delta_day in range(10):
            with mock.patch('django.utils.timezone.now') as mock_now:
                mock_now.return_value = first_order_creation_date + timedelta(days=delta_day)
                order_status = fuzzy.FuzzyChoice(OrderStatus.status_groups.FINISHED).fuzz()
                OrderFactory.create(
                    driver=self.driver,
                    status=order_status,
                    merchant=self.merchant
                )

        resp = self.client.get('/api/reports/orders/', data={
            'date_from': request_time['from'].isoformat(),
            'date_to': request_time['to'].isoformat(),
            'driver_id': self.driver.id
        })

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            resp.data['sum_data']['total_tasks'],
            Order.objects.filter(
                driver=self.driver,
                merchant=self.merchant,
                status__in=OrderStatus.status_groups.FINISHED,
                updated_at__gte=request_time['from'],
                updated_at__lte=request_time['to']).count()
        )

    def test_export_reports(self):
        first_order_creation_date = dt.now(tz=UTC) - timedelta(days=10)
        request_time = {
            'from': dt.combine(first_order_creation_date.date(), dt.min.time()).replace(tzinfo=UTC),
            'to': dt.combine((first_order_creation_date + timedelta(days=3)).date(), dt.min.time()).replace(tzinfo=UTC)
        }

        for delta_day in range(5):
            order_data = {
                'customer': {'name': 'Test Customer', },
                'deliver_address': {'location': get_fuzzy_location(), }
            }
            with mock.patch('django.utils.timezone.now') as mock_now:
                mock_now.return_value = first_order_creation_date + timedelta(days=delta_day)
                cur_time = dt.combine(django.utils.timezone.now().date(), dt.min.time()).replace(tzinfo=UTC)
                switch_times = create_order_event_times(cur_time)
                create_order_for_test(
                    test_class_item=self,
                    manager=self.manager,
                    driver=self.driver,
                    order_data=order_data,
                    switching_status_times=switch_times
                )

        self.client.force_authenticate(self.manager)

        # Request for creating report
        self.client.get('/api/reports/orders/', data={
            'date_from': request_time['from'].isoformat(),
            'date_to': request_time['to'].isoformat(),
            'driver_id': self.driver.id,
            'export': 'csv'
        })

        resp = self.client.get('/api/export-reports/%s' % ExportReportInstance.objects.last().id)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_export_active_reports(self):
        first_order_creation_date = dt.now(tz=UTC) - timedelta(days=10)
        request_time = {
            'from': dt.combine(first_order_creation_date.date(), dt.min.time()).replace(tzinfo=UTC),
            'to': dt.combine((first_order_creation_date + timedelta(days=3)).date(), dt.min.time()).replace(tzinfo=UTC)
        }

        for delta_day in range(5):
            order_data = {
                'customer': {'name': 'Test Customer', },
                'deliver_address': {'location': get_fuzzy_location(), }
            }
            with mock.patch('django.utils.timezone.now') as mock_now:
                mock_now.return_value = first_order_creation_date + timedelta(days=delta_day)
                cur_time = dt.combine(django.utils.timezone.now().date(), dt.min.time()).replace(tzinfo=UTC)
                for order_status in [OrderStatus.DELIVERED, OrderStatus.IN_PROGRESS, OrderStatus.ASSIGNED]:
                    switch_times = create_order_event_times(cur_time, to_status=order_status)
                    create_order_for_test(
                        test_class_item=self,
                        manager=self.manager,
                        driver=self.driver,
                        order_data=order_data,
                        switching_status_times=switch_times
                    )

        self.client.force_authenticate(self.manager)

        # Request for creating report
        resp = self.client.get('/api/reports/orders/', data={
            'date_from': request_time['from'].isoformat(),
            'date_to': request_time['to'].isoformat(),
            'driver_id': self.driver.id,
            'group': 'active',
            'export': 'csv'
        })

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        inst = ExportReportInstance.objects.get(id=resp.json()['id'])
        with inst.file.open() as _file:
            report_orders_count = sum(1 for _ in _file) - 1
        active_orders_for_report_count = Order.objects.filter(merchant=self.merchant,
                                                              status__in=OrderStatus.status_groups.ACTIVE,
                                                              updated_at__gte=request_time['from'],
                                                              updated_at__lte=request_time['to']).count()
        self.assertEqual(report_orders_count, active_orders_for_report_count)

    def test_export_reports_for_subbrand(self):
        subbrand = SubBrandingFactory(merchant=self.merchant)
        other_merchant = MerchantFactory()
        other_subbrand = SubBrandingFactory(merchant=other_merchant)

        first_order_creation_date = dt.now(tz=UTC) - timedelta(days=10)
        request_time = {
            'from': dt.combine(first_order_creation_date.date(), dt.min.time()).replace(tzinfo=UTC),
            'to': dt.combine((first_order_creation_date + timedelta(days=3)).date(), dt.min.time()).replace(tzinfo=UTC)
        }

        additional_order_info = ((sb, delta_day) for sb in [subbrand.id, other_subbrand.id, None] for delta_day in
                                 range(5))
        for sb_id, delta_day in additional_order_info:
            order_data = {
                'customer': {'name': 'Test Customer', },
                'deliver_address': {'location': get_fuzzy_location(), },
                'sub_branding': sb_id,
            }
            with mock.patch('django.utils.timezone.now') as mock_now:
                mock_now.return_value = first_order_creation_date + timedelta(days=delta_day)
                cur_time = dt.combine(django.utils.timezone.now().date(), dt.min.time()).replace(tzinfo=UTC)
                switch_times = create_order_event_times(cur_time)
                create_order_for_test(
                    test_class_item=self,
                    manager=self.manager,
                    driver=self.driver,
                    order_data=order_data,
                    switching_status_times=switch_times
                )

        self.client.force_authenticate(self.manager)

        # Request for creating report
        resp = self.client.get('/api/reports/orders/', data={
            'date_from': request_time['from'].isoformat(),
            'date_to': request_time['to'].isoformat(),
            'driver_id': self.driver.id,
            'sub_branding_id': subbrand.id,
            'export': 'csv'
        })

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        inst = ExportReportInstance.objects.get(id=resp.json()['id'])
        with inst.file.open() as _file:
            report_orders_count = sum(1 for _ in _file) - 1
        subbrand_orders_for_report_count = Order.objects.filter(merchant=self.merchant,
                                                                sub_branding=subbrand,
                                                                updated_at__gte=request_time['from'],
                                                                updated_at__lte=request_time['to']).count()
        self.assertEqual(report_orders_count, subbrand_orders_for_report_count)

    def test_get_orders_stat(self):
        first_order_creation_date = dt.now(tz=UTC) - timedelta(days=10)
        request_time = {
            'from': dt.combine(first_order_creation_date.date(), dt.min.time()).replace(tzinfo=UTC),
            'to': dt.combine((first_order_creation_date + timedelta(days=3)).date(), dt.min.time()).replace(tzinfo=UTC)
        }

        for delta_day in range(5):
            order_data = {
                'customer': {'name': 'Test Customer', },
                'deliver_address': {'location': get_fuzzy_location(), }
            }
            self.client.force_authenticate(self.driver)
            self.client.post('/api/drivers/me/locations', data={"location": get_fuzzy_location(), })
            self.client.logout()
            with mock.patch('django.utils.timezone.now') as mock_now:
                mock_now.return_value = first_order_creation_date + timedelta(days=delta_day)
                cur_time = dt.combine(django.utils.timezone.now().date(), dt.min.time()).replace(tzinfo=UTC)
                switch_times = create_order_event_times(cur_time)
                create_order_for_test(
                    test_class_item=self,
                    manager=self.manager,
                    driver=self.driver,
                    order_data=order_data,
                    switching_status_times=switch_times
                )

        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/reports/orderstats/', data={
            'date_from': request_time['from'].isoformat(),
            'date_to': request_time['to'].isoformat(),
            'driver_id': '',
        })

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp_sum_distance = sum([x['sum_distance'] or 0 for x in resp.data['data']])
        resp_sum_tasks = sum([x['finished_tasks'] or 0 for x in resp.data['data']])
        resp_sum_duration = sum([x['sum_duration'] or 0 for x in resp.data['data']])

        db_orders = Order.objects.filter(
            updated_at__gte=request_time['from'],
            updated_at__lte=request_time['to'],
            merchant=self.merchant,
        )
        db_orders_sum_distance = sum([x[0] or 0 for x in db_orders.values_list('order_distance')]) \
            / self.merchant.distance_show_in
        db_orders_sum_duration = sum([x[0].total_seconds() if x[0] else 0
                                      for x in db_orders.values_list('duration')]) / 60.
        db_orders_count = db_orders.filter(status__in=OrderStatus.status_groups.FINISHED).count()

        self.assertAlmostEqual(resp_sum_distance, db_orders_sum_distance)
        self.assertAlmostEqual(resp_sum_duration, db_orders_sum_duration)
        self.assertEqual(resp_sum_tasks, db_orders_count)

    def test_get_orders_locations_list(self):
        first_order_creation_date = dt.now(tz=UTC) - timedelta(days=20)
        request_time = {
            'from': dt.combine(first_order_creation_date.date(), dt.min.time()).replace(tzinfo=UTC),
            'to': dt.combine((first_order_creation_date + timedelta(days=3)).date(), dt.min.time()).replace(tzinfo=UTC)
        }

        locations = [get_fuzzy_location() for _ in range(10)]
        for delta_day in range(17):
            order_data = {
                'customer': {'name': 'Test Customer', },
                'deliver_address': {'location': locations[delta_day % 10], }
            }
            with mock.patch('django.utils.timezone.now') as mock_now:
                mock_now.return_value = first_order_creation_date + timedelta(days=delta_day)
                self.client.force_authenticate(self.driver)
                self.client.post('/api/drivers/me/locations', data={"location": get_fuzzy_location(), })
                self.client.logout()
                cur_time = dt.combine(django.utils.timezone.now().date(), dt.min.time()).replace(tzinfo=UTC)
                switch_times = create_order_event_times(cur_time)
                create_order_for_test(
                    test_class_item=self,
                    manager=self.manager,
                    driver=self.driver,
                    order_data=order_data,
                    switching_status_times=switch_times
                )

        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/reports/locations/', data={
            'date_from': request_time['from'].isoformat(),
            'date_to': request_time['to'].isoformat(),
            'driver_id': '',
        })

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        locations_count = Order.objects.filter(
            merchant=self.merchant,
            updated_at__gte=request_time['from'],
            updated_at__lte=request_time['to']
        ).count()
        self.assertEqual(len(resp.data), locations_count)


class EventsTestCase(APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    def setUp(self):
        self.merchant = MerchantFactory()
        self.driver = DriverFactory(merchant=self.merchant)
        self.manager = ManagerFactory(merchant=self.merchant)

    def test_new_events(self):
        kw = {k: getattr(self, k) for k in ('merchant', 'manager')}
        o = OrderFactory.create(driver=None, **kw)
        self.client.force_authenticate(self.manager)
        delta = {
            'status': 'assigned',
            'driver': self.driver.id
        }
        resp = self.client.patch('/api/latest/orders/{}/'.format(o.id), data=delta)
        self.assertEqual(resp.status_code, 200)
        ds = timezone.now() - timedelta(minutes=5)
        resp = self.client.get('/api/latest/new-events/', params={'date_since': ds})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        data.pop('events_before')
        data.pop('events_since')
        obj = data['events'][0].pop('object')
        new_o = Order.objects.filter(id=o.id).first()
        self.assertEqual(obj['status'], new_o.status)
        self.maxDiff = None
        _type = ContentType.objects.get_for_model(o, for_concrete_model=False).model

        Request = namedtuple('Request', ['version'])
        request = Request(settings.LATEST_API_VERSION)

        with mock.patch('crequest.middleware.CrequestMiddleware.get_request', return_value=request):
            assert_data = {
                'events': [{
                    'event': Event._action[Event.MODEL_CHANGED + 1][1],
                    'initiator': dict(SmallUserInfoSerializer(self.manager).data),
                    'obj_dump': {
                        'new_values': delta,
                        'old_values': {
                            'status': Order.NOT_ASSIGNED,
                            'driver': None
                        }
                    },
                    'type': _type,
                    'object_id': o.id
                }],
            }
        self.assertDictEqual(data, assert_data)

    def test_label_color_v2(self):
        self.merchant.enable_labels = True
        self.merchant.save()
        date = timezone.now()
        data = {
            "name": "Test",
            "color": Label.BASE_COLORS[Label.DARK_GREEN]
        }
        self.client.force_authenticate(self.manager)
        self.client.post('/api/v2/merchant/my/labels', data=data)
        resp = self.client.get('/api/v2/new-events/', params={"date_since": date})
        self.assertEqual(resp.data["events"][0]["obj_dump"]["color"], Label.BASE_COLORS[Label.DARK_GREEN])

    def test_web_label_color_v2(self):
        self.merchant.enable_labels = True
        self.merchant.save()
        date = timezone.now()
        data = {
            "name": "Test",
            "color": Label.BASE_COLORS[Label.DARK_GREEN]
        }
        self.client.force_authenticate(self.manager)
        self.client.post('/api/v2/merchant/my/labels', data=data)
        resp = self.client.get('/api/web/dev/new-events/', params={"date_since": date})
        self.assertEqual(resp.data["events"][0]["object"]["color"], Label.BASE_COLORS[Label.DARK_GREEN])
