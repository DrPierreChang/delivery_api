from datetime import time, timedelta

from django.template import Context, Template
from django.test import override_settings
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

import mock
import pytz

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import MerchantFactory
from notification.models import MerchantMessageTemplate, TemplateSMSMessage
from notification.utils import format_upcoming_delivery_time
from tasks.celery_tasks import (
    remind_about_customer_rating,
    remind_about_today_upcoming_delivery,
    remind_about_upcoming_delivery,
)
from tasks.models import OrderStatus
from tasks.tests.factories import CustomerFactory, OrderFactory


class SMSTemplateTestCase(APITestCase):
    merchant_name = 'Test'
    merchant_phone = '+61458798456'
    customer_name = 'cust'

    @classmethod
    def setUpTestData(cls):
        super(SMSTemplateTestCase, cls).setUpTestData()

        cls.merchant = MerchantFactory(name=cls.merchant_name,
                                       phone=cls.merchant_phone,
                                       timezone=pytz.timezone('Europe/Warsaw'))
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant)

    def setUp(self):
        from tasks.tests.factories import OrderFactory
        self.order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.ASSIGNED,
            driver=self.driver,
            sub_branding=None,
            customer=CustomerFactory(merchant=self.merchant, name=self.customer_name)
        )
        self.merchant.templates \
            .filter(template_type__in=[MerchantMessageTemplate.FOLLOW_UP,
                                       MerchantMessageTemplate.FOLLOW_UP_REMINDER,
                                       MerchantMessageTemplate.UPCOMING_DELIVERY]) \
            .update(enabled=True)
        self.client.force_authenticate(self.manager)

    def check_upcoming_delivery_sms(self, order, text, template_type=MerchantMessageTemplate.UPCOMING_DELIVERY):
        upcoming_delivery_template = MerchantMessageTemplate.objects.get(
            merchant=self.merchant,
            template_type=template_type
        )
        msg_queue = TemplateSMSMessage.objects.filter(order=order, template=upcoming_delivery_template)
        self.assertEqual(msg_queue.count(), 1)
        self.assertEqual(msg_queue.last().text[:len(text)], text)

    def change_status_to(self, order_status):
        order_resp = self.client.patch('/api/orders/%s/' % self.order.order_id, {
            'status': order_status,
        })
        self.assertEqual(order_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(order_resp.data['status'], order_status)

    def test_sms_on_order_status_change(self):
        with mock.patch('tasks.models.orders.Order.notify_customer') as mock_notify:
            self.change_status_to(OrderStatus.IN_PROGRESS)
            mock_notify.assert_called_once()
            _, kwargs = mock_notify.call_args
            self.assertIn('template_type', kwargs)
            self.assertEqual(kwargs['template_type'], MerchantMessageTemplate.CUSTOMER_JOB_STARTED)

        with mock.patch('tasks.models.orders.Order.notify_customer') as mock_notify:
            self.change_status_to(OrderStatus.FAILED)
            mock_notify.assert_called_once()
            _, kwargs = mock_notify.call_args
            self.assertIn('template_type', kwargs)
            self.assertEqual(kwargs['template_type'], MerchantMessageTemplate.CUSTOMER_JOB_TERMINATED)

    @override_settings(CUSTOMER_MESSAGES=dict(task_period=60, reminder_timeout=300, follow_up_reminder_timeout=900, upcoming_delivery_timeout=900))
    def test_reminder_sms(self):
        now = timezone.now()
        delivered_time = now - timedelta(seconds=330)
        in_progress_time = delivered_time - timedelta(seconds=10)

        with mock.patch('django.utils.timezone.now', return_value=in_progress_time):
            self.change_status_to(OrderStatus.IN_PROGRESS)
        with mock.patch('django.utils.timezone.now', return_value=delivered_time):
            self.change_status_to(OrderStatus.DELIVERED)

        with mock.patch('tasks.models.orders.Order.notify_customer') as mock_notify, \
                mock.patch('django.utils.timezone.now', return_value=now):
            remind_about_customer_rating()
            mock_notify.assert_called_once()
            _, kwargs = mock_notify.call_args
            self.assertIn('template_type', kwargs)
            self.assertEqual(kwargs['template_type'], MerchantMessageTemplate.FOLLOW_UP)

        now += timedelta(seconds=600)
        with mock.patch('tasks.models.orders.Order.notify_customer') as mock_notify, \
                mock.patch('django.utils.timezone.now', return_value=now):
            remind_about_customer_rating()
            mock_notify.assert_called_once()
            _, kwargs = mock_notify.call_args
            self.assertIn('template_type', kwargs)
            self.assertEqual(kwargs['template_type'], MerchantMessageTemplate.FOLLOW_UP_REMINDER)

    def test_upcoming_order_sms_for_order_in_future(self):
        from tasks.tests.factories import OrderFactory
        delivery_day = timezone.now() + timedelta(days=7)
        day_before_delivery = delivery_day - timedelta(days=1)

        with mock.patch('tasks.models.orders.Order.notify_customer') as mock_notify:
            self.old_order = OrderFactory(
                merchant=self.merchant,
                manager=self.manager,
                status=OrderStatus.ASSIGNED,
                driver=self.driver,
                sub_branding=None,
                customer=CustomerFactory(merchant=self.merchant, name=self.customer_name, phone='+61458798450'),
                deliver_before=delivery_day
            )
            remind_about_upcoming_delivery()
            mock_notify.assert_not_called()

        expected_text = 'Good news! Your order from Test will be delivered ' \
                        'to {customer_address} between {_from} - {_to} tomorrow!' \
            .format(
                _from=format_upcoming_delivery_time(
                    self.old_order.customer,
                    delivery_day - timedelta(hours=self.merchant.delivery_interval)
                ),
                _to=format_upcoming_delivery_time(self.old_order.customer, delivery_day),
                customer_address=self.old_order.deliver_address.address
            )

        with mock.patch('django.utils.timezone.now', return_value=day_before_delivery):
            remind_about_upcoming_delivery()
            self.check_upcoming_delivery_sms(self.old_order, expected_text)

    def test_upcoming_order_sms_for_soonest_orders(self):
        from tasks.tests.factories import OrderFactory
        midnight = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        fake_now = midnight + timedelta(hours=15)

        cur_day = fake_now + timedelta(hours=5)
        next_day = fake_now + timedelta(hours=23)

        with mock.patch('django.utils.timezone.now', return_value=fake_now):
            self.current_day_order = OrderFactory(
                merchant=self.merchant,
                manager=self.manager,
                status=OrderStatus.ASSIGNED,
                driver=self.driver,
                sub_branding=None,
                customer=CustomerFactory(merchant=self.merchant, phone='+61458798450'),
                deliver_before=cur_day
            )
            self.next_day_order = OrderFactory(
                merchant=self.merchant,
                manager=self.manager,
                status=OrderStatus.ASSIGNED,
                driver=self.driver,
                sub_branding=None,
                customer=CustomerFactory(merchant=self.merchant, phone='+61458798450'),
                deliver_before=next_day
            )

            expected_current_day_text = 'Your order from Test will be delivered ' \
                                        'to {customer_address} between {_from} - {_to}!' \
                .format(
                    _from=format_upcoming_delivery_time(
                        self.current_day_order.customer,
                        cur_day - timedelta(hours=self.merchant.delivery_interval)
                    ),
                    _to=format_upcoming_delivery_time(self.current_day_order.customer, cur_day),
                    customer_address=self.current_day_order.deliver_address.address
                )
            expected_next_day_text = 'Good news! Your order from Test will be delivered ' \
                                     'to {customer_address} between {_from} - {_to} tomorrow!' \
                .format(
                    _from=format_upcoming_delivery_time(
                        self.next_day_order.customer,
                        next_day - timedelta(hours=self.merchant.delivery_interval)
                    ),
                    _to=format_upcoming_delivery_time(self.next_day_order.customer, next_day),
                    customer_address=self.next_day_order.deliver_address.address
                )

            remind_about_upcoming_delivery()
            self.check_upcoming_delivery_sms(self.current_day_order, expected_current_day_text)
            self.check_upcoming_delivery_sms(self.next_day_order, expected_next_day_text)

    def test_order_upcoming_delivery_with_delivery_interval(self):
        midnight = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        fake_now = midnight + timedelta(hours=15)
        with mock.patch('django.utils.timezone.now', return_value=fake_now):
            lower_bound, upper_bound = timezone.now(), timezone.now() + timedelta(hours=5)
            order = OrderFactory(
                merchant=self.merchant,
                manager=self.manager,
                status=OrderStatus.ASSIGNED,
                driver=self.driver,
                sub_branding=None,
                customer=CustomerFactory(merchant=self.merchant, phone='+61458798450'),
                deliver_before=upper_bound,
                deliver_after=lower_bound
            )

            msg_template = MerchantMessageTemplate.objects.get(
                merchant=self.merchant,
                template_type=MerchantMessageTemplate.UPCOMING_DELIVERY
            )

            sms_text_template = Template(msg_template.text)
            time_interval = '{start} - {end}{day}'.format(
                start=format_upcoming_delivery_time(order.customer, order.deliver_after),
                day='',
                end=format_upcoming_delivery_time(order.customer, order.deliver_before),
            )
            context = Context({
                "merchant": order.merchant,
                "customer_address": order.deliver_address.address,
                "time_interval": time_interval
            })

            expected_sms_text = sms_text_template.render(context)
            remind_about_upcoming_delivery()
            self.check_upcoming_delivery_sms(order, expected_sms_text)

    def _instant_upcoming_delivery_notification(self, order, delivery_day, template_type):
        msg_template = MerchantMessageTemplate.objects.get(
            merchant=self.merchant,
            template_type=template_type
        )
        sms_text_template = Template(msg_template.text)
        time_interval = '{start} - {end}{day}'.format(
            start=format_upcoming_delivery_time(
                order.customer,
                order.deliver_before - timedelta(hours=self.merchant.delivery_interval)
            ),
            day=delivery_day,
            end=format_upcoming_delivery_time(order.customer, order.deliver_before),
        )
        context = Context({
            "merchant": order.merchant,
            "customer_address": order.deliver_address.address,
            "time_interval": time_interval,
            "delivery_day": delivery_day,
            "welcome_text": "Good news! "
        })

        expected_sms_text = sms_text_template.render(context)
        remind_about_upcoming_delivery()
        self.check_upcoming_delivery_sms(order, expected_sms_text, template_type)

    def test_order_instant_upcoming_delivery(self):
        self.merchant.templates.filter(
            template_type=MerchantMessageTemplate.INSTANT_UPCOMING_DELIVERY
        ).update(enabled=True)
        self.merchant.templates.filter(
            template_type=MerchantMessageTemplate.UPCOMING_DELIVERY
        ).update(enabled=False)

        order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.ASSIGNED,
            driver=self.driver,
            sub_branding=None,
            deliver_before=timezone.now() + timedelta(days=3),
            customer=CustomerFactory(merchant=self.merchant, phone='+61458798450')
        )
        delivery_day = 'on {}'.format(order.deliver_before.strftime('%B %-d'))

        self._instant_upcoming_delivery_notification(
            order, delivery_day, MerchantMessageTemplate.INSTANT_UPCOMING_DELIVERY
        )

    def test_mixed_upcoming_delivery_notification(self):
        self.merchant.templates.filter(
            template_type=MerchantMessageTemplate.INSTANT_UPCOMING_DELIVERY
        ).update(enabled=True)

        deliver_before = timezone.now() + timedelta(days=2)
        day_before_delivery = deliver_before - timedelta(days=1)

        order = OrderFactory(
            merchant=self.merchant,
            manager=self.manager,
            status=OrderStatus.ASSIGNED,
            driver=self.driver,
            sub_branding=None,
            deliver_before=deliver_before,
            customer=CustomerFactory(merchant=self.merchant, phone='+61458798450')
        )

        delivery_day = 'on {}'.format(order.deliver_before.strftime('%B %-d'))
        self._instant_upcoming_delivery_notification(
            order, delivery_day, MerchantMessageTemplate.INSTANT_UPCOMING_DELIVERY
        )

        with mock.patch('django.utils.timezone.now', return_value=day_before_delivery):
            delivery_day = " tomorrow"
            self._instant_upcoming_delivery_notification(
                order, delivery_day, MerchantMessageTemplate.UPCOMING_DELIVERY
            )

    def _today_upcoming_delivery_notification(self, order):
        template_type = MerchantMessageTemplate.TODAY_UPCOMING_DELIVERY
        msg_template = MerchantMessageTemplate.objects.get(
            merchant=self.merchant,
            template_type=template_type,
        )
        sms_text_template = Template(msg_template.text)

        upper_bound = order.deliver_before.astimezone(self.merchant.timezone)
        lower_bound = upper_bound - timedelta(hours=order.merchant.delivery_interval)

        hours_interval = '{start} - {end}'.format(
            start=format_upcoming_delivery_time(order.customer, lower_bound),
            end=format_upcoming_delivery_time(order.customer, upper_bound)
        )

        context = Context({
            "merchant": order.merchant,
            "time_interval": hours_interval,
            'url': order.get_order_url(),
        })

        expected_sms_text = sms_text_template.render(context)
        remind_about_today_upcoming_delivery()
        self.check_upcoming_delivery_sms(order, expected_sms_text, template_type)

    def test_order_today_upcoming_delivery(self):
        self.merchant.time_today_reminder = time(10, 2)
        self.merchant.save()

        now = timezone.now()
        mock_time = now.astimezone(self.merchant.timezone).replace(hour=10, minute=0, microsecond=0)

        with mock.patch('django.utils.timezone.now', return_value=mock_time):
            self.merchant.templates.filter(
                template_type=MerchantMessageTemplate.TODAY_UPCOMING_DELIVERY
            ).update(enabled=True)

            order = OrderFactory(
                merchant=self.merchant,
                manager=self.manager,
                status=OrderStatus.ASSIGNED,
                driver=self.driver,
                sub_branding=None,
                deliver_before=now + timedelta(hours=4),
                customer=CustomerFactory(merchant=self.merchant, phone='+61458798450')
            )

            self._today_upcoming_delivery_notification(order)
