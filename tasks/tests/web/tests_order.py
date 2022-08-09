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
from base.models import Member
from base.utils import dictionaries_difference, get_fuzzy_location
from driver.factories import DriverLocationFactory
from merchant.factories import MerchantFactory
from notification.tests.mixins import NotificationTestMixin
from tasks.api.web.orders.serializers import OrderDeadlineSerializer
from tasks.mixins.order_status import OrderStatus
from tasks.models.orders import Order
from tasks.tests.factories import OrderFactory
from tasks.utils import create_order_event_times, create_order_for_test

from ..base_test_cases import BaseOrderTestCase


class OrderTestCase(NotificationTestMixin, BaseOrderTestCase):
    @classmethod
    def setUpTestData(cls):
        super(OrderTestCase, cls).setUpTestData()
        loc = DriverLocationFactory(member=cls.driver)
        cls.driver.last_location = loc
        cls.driver.save()
        cls.job_data = {
            'deliver': {
                'customer': {
                    'name': 'Mike Kowalski',
                },
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {
                            'lat': 53.91254758887667,
                            'lng': 27.543441765010357
                        },
                    },
                    'secondary_address': '27'
                }
            }
        }

        cls.orders_url = '/api/web/dev/orders/'

    def setUp(self):
        self.order = self.create_default_order(sub_branding=self.sub_branding)
        self.second_merchant = MerchantFactory()
        self.second_merchant_manager = ManagerFactory(merchant=self.second_merchant)
        self.second_merchant_first_driver = DriverFactory(merchant=self.second_merchant)

    def test_order_creation(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.post(self.orders_url, data=self.job_data)
        self.assertEqual(resp.status_code, 201)
        Order.objects.get(order_id=resp.data['order_id'])

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
            h = random.randint(1, latest_hours - 1)
            fake_time = current_time + timedelta(hours=h)
            o.status = 'delivered'
            o.end_order()
            Order.objects.filter(pk=o.pk).update(updated_at=fake_time)
        self.client.force_authenticate(self.manager)
        for t in [{
            'params': {'group': 'active'},
            'assertor': self.assertGreaterEqual,
            'field': lambda res: res['deliver']['before']
        }, {
            'params': {'status': 'delivered'},
            'assertor': self.assertLessEqual,
            'field': lambda res: res['statistics']['updated_at']
        }]:
            with mock.patch('django.utils.timezone.now') as get_now:
                get_now.return_value = current_time + timedelta(hours=2 * latest_hours)
                resp = self.client.get(self.orders_url, data=t['params'])
                res = resp.data['results']
                self.assertEqual(resp.status_code, 200)
                for ind in range(0, len(res) - 1):
                    t['assertor'](parser.parse(t['field'](res[ind + 1])), parser.parse(t['field'](res[ind])))

    def test_order_sorting(self):
        self._create_non_finished_orders()
        self.client.force_authenticate(self.manager)

        from tasks.api.web.orders.views import WebOrderViewSet
        sort_options = [option if isinstance(option, str) else option[0] for option in WebOrderViewSet.ordering_fields]
        sort_options += [f'-{option}' for option in sort_options]
        for option in sort_options:
            resp = self.client.get(f'{self.orders_url}?order_by={option}')
            self.assertEqual(resp.status_code, 200)

    def test_assign_driver(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.patch(f'{self.orders_url}{self.order.id}/', {
            'driver_id': self.driver.id,
            'status': Order.ASSIGNED,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['driver_id'], self.driver.id)
        self.assertEqual(resp.json()['status'], Order.ASSIGNED)

    def test_manager_orders_list_getting(self):
        OrderFactory.create_batch(
            size=10,
            merchant=self.merchant,
            manager=self.manager,
        )
        self.client.force_authenticate(self.manager)

        resp = self.client.get(self.orders_url)
        resp_json_data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(type(resp_json_data['results'][0]['deliver']['address']['primary_address']['location']), dict)
        self.assertGreater(resp_json_data.get('count'), 0)

    def test_order_deletion(self):
        self.order.status = OrderStatus.NOT_ASSIGNED
        self.order.driver = None
        self.order.deliver_before = timezone.now() + timedelta(days=2)
        self.order.save()

        self.client.force_authenticate(self.manager)
        request_url = f'{self.orders_url}{self.order.id}/'

        with self.mock_send_versioned_push() as send_push_mock:
            resp = self.client.delete(request_url)
            # This merchant has 2 driver
            self.assertEqual(send_push_mock.call_count, Member.drivers.filter(merchant=self.merchant).count())

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
        resp = self.client.get(f'{self.orders_url}?group=active')
        active_orders_count = Order.objects.filter(status__in=OrderStatus.status_groups.UNFINISHED).count()
        self.assertEqual(resp.data['count'], active_orders_count)

    def test_orders_path_getting(self):
        self.order.status = OrderStatus.ASSIGNED
        self.order.driver = self.driver
        locations = list(DriverLocationFactory.create_batch(size=10, member=self.driver))
        self.order.path = {'full': [loc.location for loc in locations]}
        self.order.save()

        self.client.force_authenticate(self.manager)
        resp = self.client.get(f'{self.orders_url}{self.order.id}/path/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['path']), len(locations))

    def test_assign_time_getting(self):
        day_before = dt.now(tz=UTC) - timedelta(days=1)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = day_before
            cur_time = dt.combine(django.utils.timezone.now().date(), dt.min.time()).replace(tzinfo=UTC)
            switch_times = create_order_event_times(cur_time, to_status=OrderStatus.IN_PROGRESS)
            job_id = create_order_for_test(
                test_class_item=self,
                manager=self.manager,
                driver=self.driver,
                order_data={
                    'customer': {'name': 'Test Customer', },
                    'deliver_address': {'location': get_fuzzy_location(), }
                },
                switching_status_times=switch_times
            ).id

        self.client.force_authenticate(self.manager)
        resp = self.client.get((f'{self.orders_url}{job_id}/'))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(parser.parse(resp.data['statistics']['assigned_at']).astimezone(tz=pytz.UTC),
                         switch_times[OrderStatus.ASSIGNED])

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

        resp = self.client.get(f'{self.orders_url}last_customer_comments/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp_orders_id = list(map(lambda x: x['order_id'], resp.data))
        self.assertListEqual(resp_orders_id, orders_id[:len(resp_orders_id)])

    def test_order_change(self):
        trackable_fields = {'title', 'label', 'customer', 'deliver_address', 'deliver_before',
                            'description', 'comment', 'sub_branding_id'}
        unchanged_fields = ('customer',)
        delivery_date = timezone.now() + timedelta(days=1)
        data = {
            'comment': 'Test comment for update',
            'deliver': {
                'customer': {
                    'id': self.order.customer.id,
                    'name': self.order.customer.name,
                    'phone_number': self.order.customer.phone,
                    'email': self.order.customer.email,
                },
                'before': delivery_date.isoformat(),
            },
        }
        old_dict = model_to_dict(self.order, fields=trackable_fields)
        self.client.force_authenticate(self.manager)
        resp = self.client.patch(f'{self.orders_url}{self.order.id}/', data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()['comment'], data['comment'])

        self.order.refresh_from_db()
        new_dict = model_to_dict(self.order, fields=trackable_fields)
        key_diff, _, _ = dictionaries_difference(old_dict, new_dict)
        self.assertEqual(set(data).intersection(key_diff).intersection(unchanged_fields), set())

    def test_order_deadlines(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get(f'{self.orders_url}deadlines/')
        self.assertEqual(resp.status_code, 200)
        item = resp.data['results'][0]
        self.assertDictEqual(item, OrderDeadlineSerializer(Order.objects.get(id=item['id'])).data)

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
            f'{self.orders_url}{self.test_order.id}/',
            data={'driver_id': self.second_merchant_first_driver.id, 'status': OrderStatus.ASSIGNED}
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        self.test_order.capacity = 800
        self.test_order.save()
        self.test_order.refresh_from_db()
        resp = self.client.patch(
            f'{self.orders_url}{self.test_order.id}/',
            data={'driver_id': self.second_merchant_first_driver.id, 'status': OrderStatus.ASSIGNED}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def _generate_image(self):
        file = io.BytesIO()
        image = Image.new('RGBA', size=(100, 100), color=(155, 0, 0))
        image.save(file, 'png')
        file.name = 'test.png'
        file.seek(0)
        return file
