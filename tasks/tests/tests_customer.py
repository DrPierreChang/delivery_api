from datetime import datetime as dt
from datetime import timedelta

import django
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from rest_framework import status
from rest_framework.test import APITestCase

import mock
from factory.compat import UTC

from base.factories import DriverFactory, ManagerFactory
from base.utils import get_fuzzy_location
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory, SubBrandingFactory
from merchant.models import Merchant
from notification.factories import FCMDeviceFactory
from notification.mixins import MessageTemplateStatus
from tasks.celery_tasks import CACHE_KEY_UPCOMING_DELIVERY
from tasks.mixins.order_status import OrderStatus
from tasks.models import Customer, Order
from tasks.tests.base_test_cases import BaseOrderTestCase
from tasks.tests.factories import CustomerFactory, OrderFactory
from tasks.utils import create_order_event_times, create_order_for_test


class CustomerTestCase(APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    customer_order_api_url = '/api/customers/{uid}/orders/{token}/{path}'

    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(
            call_center_email='call@center.com',
            customer_review_opt_in_enabled=True
        )
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(work_status=WorkStatus.WORKING, merchant=cls.merchant)
        cls.merchant.templates\
            .filter(template_type=MessageTemplateStatus.LOW_FEEDBACK)\
            .update(enabled=True)
        cls.sub_brand = SubBrandingFactory(merchant=cls.merchant)

    def setUp(self):
        two_days_before = dt.now(tz=UTC) - timedelta(days=2)
        with mock.patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = two_days_before
            cur_time = dt.combine(django.utils.timezone.now().date(), dt.min.time()).replace(tzinfo=UTC)
            switch_times = create_order_event_times(cur_time, to_status=OrderStatus.DELIVERED)
            order_id = create_order_for_test(
                test_class_item=self,
                manager=self.manager,
                driver=self.driver,
                order_data={
                    'customer': {'name': 'Test Customer', },
                    'deliver_address': {'location': get_fuzzy_location(), },
                    'sub_branding_id': self.sub_brand.id
                },
                switching_status_times=switch_times
            ).order_id

        self.client.logout()
        self.order = Order.objects.get(order_id=order_id)
        self.customer = self.order.customer
        self.customer_uidb64 = urlsafe_base64_encode(force_bytes(self.customer.pk))

    def get_order_details(self):
        api_url = self.customer_order_api_url.format(
            uid=self.customer_uidb64, token=str(self.order.order_token), path=''
        )
        resp = self.client.get(api_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['order_id'], self.order.order_id)
        return resp.json()

    def change_status_to(self, order, order_status):
        order_resp = self.client.patch(
            '/api/orders/{}/'.format(order.order_id), {'status': order_status}
        )
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(order_resp.data['status'], order_status)

    def test_order_confirm(self):
        api_url = self.customer_order_api_url.format(
            uid=self.customer_uidb64, token=str(self.order.order_token), path='confirmation'
        )
        resp = self.client.patch(api_url, {})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['is_confirmed_by_customer'], True)

    def test_not_completed_order_confirm(self):
        self.order.status = OrderStatus.ASSIGNED
        self.order.save()

        api_url = self.customer_order_api_url.format(
            uid=self.customer_uidb64, token=str(self.order.order_token), path='confirmation'
        )

        resp = self.client.patch(api_url, {})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(resp.data['errors'].get('is_confirmed_by_customer', ''))

    def test_customers_orders_list(self):
        OrderFactory(customer=self.customer)
        OrderFactory(customer=CustomerFactory(
            merchant=self.merchant
        ))
        resp = self.client.get('/api/customers/{}/orders/'.format(self.customer_uidb64))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], Order.objects.filter(customer__id=self.customer.id).count())

    def test_customers_order_location(self):
        self.order.status = OrderStatus.IN_PROGRESS
        self.order.save()

        api_url = self.customer_order_api_url.format(
            uid=self.customer_uidb64, token=str(self.order.order_token), path='location'
        )

        resp = self.client.get(api_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_customers_confirmed_order_location(self):
        self.order.status = OrderStatus.DELIVERED
        self.order.is_confirmed_by_customer = True
        self.order.save()

        api_url = self.customer_order_api_url.format(
            uid=self.customer_uidb64, token=str(self.order.order_token), path='location'
        )

        resp = self.client.get(api_url)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_customers_order_rating(self):
        api_url = self.customer_order_api_url.format(
            uid=self.customer_uidb64, token=str(self.order.order_token), path='confirmation'
        )
        resp = self.client.patch(api_url, data={'rating': 7, })

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.rating, 7)

    def test_customer_low_rating(self):
        with mock.patch('notification.celery_tasks.send_template_notification.apply_async') as mock_notification:
            api_url = self.customer_order_api_url.format(
                uid=self.customer_uidb64, token=str(self.order.order_token), path='confirmation'
            )
            resp = self.client.patch(api_url, data={'rating': 3, })
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            mock_notification.assert_called_once()

    def test_customer_opt_in(self):
        api_url = self.customer_order_api_url.format(
            uid=self.customer_uidb64, token=str(self.order.order_token), path='confirmation'
        )

        resp = self.client.patch(api_url, data={'rating': 7, 'customer_review_opt_in': True})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertTrue(self.order.customer_review_opt_in)

    def test_customers_order_tracking(self):
        api_url = self.customer_order_api_url.format(
            uid=self.customer_uidb64, token=str(self.order.order_token), path='confirmation'
        )
        self.client.patch(api_url, {})

        api_url = self.customer_order_api_url.format(
            uid=self.customer_uidb64, token=str(self.order.order_token), path='stats'
        )

        resp = self.client.get(api_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_notify_customer_when_job_failed(self):
        self.client.force_authenticate(self.manager)
        order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.ASSIGNED,
            driver=self.driver
        )
        self.change_status_to(order, OrderStatus.IN_PROGRESS)
        with mock.patch('tasks.models.Order.notify_customer') as send_notification_mock:
            self.change_status_to(order, OrderStatus.FAILED)
            self.assertTrue(send_notification_mock.called)

        order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.ASSIGNED,
            driver=self.driver
        )
        with mock.patch('tasks.models.Order.notify_customer') as send_notification_mock:
            self.change_status_to(order, OrderStatus.FAILED)
            self.assertFalse(send_notification_mock.called)

    def test_customers_order_stats_messages(self):
        order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.NOT_ASSIGNED,
            customer=self.customer,
        )

        api_url = self.customer_order_api_url.format(
            uid=self.customer_uidb64, token=str(order.order_token), path='stats'
        )
        resp = self.client.get(api_url)
        self.assertRegex(resp.data['message']['heading'], r'^You have an upcoming order from .*')
        self.assertEqual(resp.data['message']['second_heading'], '')
        self.assertEqual(resp.data['message']['sub_heading'], 'Stay tuned!')

        order.driver = self.driver
        order.status = OrderStatus.ASSIGNED
        order.save()

        resp = self.client.get(api_url)
        self.assertEqual(resp.data['message']['heading'], 'Your order is out for delivery')
        self.assertRegex(resp.data['message']['second_heading'], r'^You are number .*')
        self.assertRegex(resp.data['message']['sub_heading'], r'^Expect delivery.*')

        order.status = OrderStatus.IN_PROGRESS
        order.save()
        resp = self.client.get(api_url)
        self.assertNotIn('message', resp.data)

        order.status = OrderStatus.FAILED
        order.save()
        resp = self.client.get(api_url)
        self.assertEqual(resp.data['message']['heading'], 'The delivery has been unsuccessful this time')
        self.assertEqual(resp.data['message']['second_heading'], '')
        self.assertEqual(resp.data['message']['sub_heading'], 'Please contact us for more information')


class CustomerLastAddressTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory()
        cls.manager = ManagerFactory(merchant=cls.merchant)

    def setUp(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.post('/api/orders/', {
            'customer': {'name': 'New test customer'},
            'deliver_address': {'location': '51.4938516,-0.1567399'}
        })
        self.order = Order.objects.select_related('customer').get(order_id=resp.data['order_id'])

    def test_customer_has_last_address_after_order_create(self):
        self.assertIsNotNone(self.order.customer.last_address)

    def test_last_address_change_logic(self):
        customer_last_address = Customer.objects.get(id=self.order.customer.id).last_address.id
        resp = self.client.post('/api/orders/', {
            'customer': {'name': 'New test customer'},
            'deliver_address': {'location': '50.4938516,-1.1567399'}
        })
        new_order = Order.objects.select_related('customer').get(order_id=resp.data['order_id'])
        self.assertNotEqual(customer_last_address, new_order.customer.last_address.id)

        customer_last_address = new_order.customer.last_address.id
        resp = self.client.patch('/api/orders/{}/'.format(self.order.order_id), {
            'deliver_address': {'location': '49.4938516,-2.1567399'}
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        fresh_order = Order.objects.select_related('customer').get(id=self.order.id)
        self.assertNotEqual(customer_last_address, fresh_order.customer.last_address.id)

    def test_new_customer_has_last_address(self):
        self.client.patch('/api/orders/{}/'.format(self.order.order_id), {
            'customer': {'name': 'New Unique Name unique name'}
        })

        fresh_order = Order.objects.select_related('customer').get(id=self.order.id)
        self.assertNotEqual(self.order.customer.id, fresh_order.customer.id)
        self.assertIsNotNone(fresh_order.customer.last_address)


class SendEmailTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        super(SendEmailTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory(geofence_settings=Merchant.UPON_ENTERING)
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant, first_name='driver', work_status=WorkStatus.WORKING)
        cls.customer = CustomerFactory(merchant=cls.merchant)
        cls.assigned_order = OrderFactory(
            merchant=cls.merchant, manager=cls.manager,
            status=OrderStatus.ASSIGNED, driver=cls.driver,
            customer=cls.customer)

    def setUp(self):
        self.client.force_authenticate(self.manager)

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    def test_email_after_move_in_progress(self, mock_request):
        self.client.patch('/api/orders/{}/'.format(self.assigned_order.order_id), {
            'status': OrderStatus.IN_PROGRESS,
        })
        mock_request.assert_called()


class RemindDeliveryTestCase(BaseOrderTestCase):
    @classmethod
    def setUpTestData(cls):
        super(RemindDeliveryTestCase, cls).setUpTestData()
        cls.device = FCMDeviceFactory(user=cls.driver)

    def test_cache_time_task_upcoming_delivery(self):
        with mock.patch('tasks.models.orders.Order.notify_customer') as send_notification:
            last_reminder = timezone.now() - timezone.timedelta(seconds=(settings.CUSTOMER_MESSAGES['task_period']/2)-1)
            cache.set(CACHE_KEY_UPCOMING_DELIVERY, last_reminder)
            self.create_default_order(deliver_before=(
                    timezone.now()
                    + timezone.timedelta(seconds=settings.CUSTOMER_MESSAGES['upcoming_delivery_timeout'])
                    + timezone.timedelta(seconds=(settings.CUSTOMER_MESSAGES['task_period']/2)-1)
            ))

            last_reminder = timezone.now() - timezone.timedelta(seconds=(settings.CUSTOMER_MESSAGES['task_period']/2)+1)
            cache.set(CACHE_KEY_UPCOMING_DELIVERY, last_reminder)
            self.create_default_order(deliver_before=(
                    timezone.now()
                    + timezone.timedelta(seconds=settings.CUSTOMER_MESSAGES['upcoming_delivery_timeout'])
                    + timezone.timedelta(seconds=(settings.CUSTOMER_MESSAGES['task_period']/2)+1)
            ))

            send_notification.assert_called_once()
