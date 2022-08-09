from __future__ import absolute_import

import datetime

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from celery.schedules import crontab
from celery.task import periodic_task

from merchant.models import Merchant
from merchant.models.mixins import MerchantTypes
from notification.models import MerchantMessageTemplate
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order
from tasks.utils import generate_data_for_remind_upcoming_delivery, generate_data_for_today_remind_upcoming_delivery

CACHE_KEY_UPCOMING_DELIVERY = 'order_cache_time_upcoming_delivery'


@periodic_task(run_every=datetime.timedelta(seconds=settings.CUSTOMER_MESSAGES['task_period']))
def remind_about_upcoming_delivery(order_id=None):
    cache.set(CACHE_KEY_UPCOMING_DELIVERY, timezone.now())

    if order_id:
        orders = Order.objects.filter(order_id=order_id)
    else:
        orders = Order.objects.all().get_orders_for_upcoming_delivery_remind()

    order_statuses = set(OrderStatus.status_groups.UNFINISHED) - set(OrderStatus.status_groups.TRACKABLE)

    orders = orders.filter(status__in=order_statuses).select_related('merchant')

    for order in orders:
        template_type, extra_context = generate_data_for_remind_upcoming_delivery(order)
        order.notify_customer(
            template_type=template_type,
            extra_context=extra_context
        )


@periodic_task(run_every=datetime.timedelta(seconds=settings.CUSTOMER_MESSAGES['task_period']))
def remind_about_today_upcoming_delivery():
    task_period = datetime.timedelta(seconds=settings.CUSTOMER_MESSAGES['task_period'])
    merchant_ids = []
    now = timezone.now()

    merchant_data = Merchant.objects.filter(
        templates__template_type=MerchantMessageTemplate.TODAY_UPCOMING_DELIVERY,
        templates__enabled=True
    ).values_list('id', 'timezone', 'time_today_reminder')
    for merchant_id, merchant_timezone, local_time_today_reminder in merchant_data:
        # based on "local_time_today_reminder" the nearest reminder is calculated
        datetime_now = now.astimezone(merchant_timezone)
        datetime_remind = merchant_timezone.localize(
            datetime.datetime.combine(datetime_now.date(), local_time_today_reminder)
        )
        if datetime_remind < datetime_now:
            datetime_remind += timezone.timedelta(days=1)

        if datetime_remind < datetime_now + task_period:
            merchant_ids.append(merchant_id)

    datetime_lower_deliver = now
    datetime_upper_deliver = now + datetime.timedelta(days=1)

    orders = Order.objects.filter(
        deliver_before__gte=datetime_lower_deliver,
        deliver_before__lt=datetime_upper_deliver,
        status=OrderStatus.ASSIGNED,
        merchant_id__in=merchant_ids,
    ).prefetch_related('merchant')

    for order in orders:
        local_now = now.astimezone(order.merchant.timezone)
        local_deliver = order.deliver_before.astimezone(order.merchant.timezone)
        if local_now.date() != local_deliver.date():
            continue

        eta = order.merchant.timezone.localize(
            datetime.datetime.combine(local_now.date(), order.merchant.time_today_reminder)
        )
        template_type, extra_context = generate_data_for_today_remind_upcoming_delivery(order)
        order.notify_customer(
            template_type=template_type,
            extra_context=extra_context,
            dispatch_eta=eta
        )


@periodic_task(run_every=datetime.timedelta(seconds=settings.CUSTOMER_MESSAGES['task_period']))
def remind_about_customer_rating():
    now = timezone.now()
    delta = datetime.timedelta(seconds=settings.CUSTOMER_MESSAGES['task_period'])

    upper_bound = now - datetime.timedelta(seconds=settings.CUSTOMER_MESSAGES['reminder_timeout'])
    orders_timeout = Order.aggregated_objects.filter(
        merchant__templates__template_type=MerchantMessageTemplate.FOLLOW_UP,
        merchant__templates__enabled=True,
        enable_rating_reminder=True,
    ).get_orders_for_remind(upper_bound - delta, upper_bound)

    upper_bound_follow_up = now - datetime.timedelta(seconds=settings.CUSTOMER_MESSAGES['follow_up_reminder_timeout'])
    follow_up_orders_timeout = Order.aggregated_objects.filter(
        merchant__templates__template_type=MerchantMessageTemplate.FOLLOW_UP_REMINDER,
        merchant__templates__enabled=True,
        enable_rating_reminder=True,
    ).get_orders_for_remind(upper_bound_follow_up - delta, upper_bound_follow_up)

    reminders = [
        (MerchantMessageTemplate.FOLLOW_UP, orders_timeout),
        (MerchantMessageTemplate.FOLLOW_UP_REMINDER, follow_up_orders_timeout)
    ]

    for template_type, orders in reminders:
        for order in orders:
            extra_context = {
                'merchant': order.sub_branding or order.merchant,
                'url': order.get_order_url()
            }
            order.notify_customer(template_type=template_type, extra_context=extra_context)


@periodic_task(run_every=crontab(hour='*', minute='*/10'))
def notify_miele_survey_customer():
    # Send special sms to customers at 7 p.m.
    # This customers should pass survey, but there is not active order in Radaro system.
    now = timezone.now()
    from_time = now - timezone.timedelta(days=1)
    orders = Order.objects.filter(status=OrderStatus.ASSIGNED, created_at__gte=from_time, created_at__lte=now)\
        .select_related('sub_branding')
    merchants = Merchant.objects.filter(merchant_type=MerchantTypes.MERCHANT_TYPES.MIELE_SURVEY)
    for merchant in merchants:
        if now.astimezone(merchant.timezone).hour != 19:
            continue
        merchant_orders = orders.filter(merchant=merchant)
        orders_to_notify = list(merchant_orders)
        merchant_orders.update(status=OrderStatus.DELIVERED)
        for order in orders_to_notify:
            order.notify_customer(template_type=MerchantMessageTemplate.SPECIAL_MIELE_SURVEY,
                                  extra_context={"merchant": order.sub_branding or merchant,
                                                 "url": order.get_order_url()})


__all__ = ['remind_about_customer_rating', 'remind_about_upcoming_delivery', 'CACHE_KEY_UPCOMING_DELIVERY',
           'notify_miele_survey_customer', 'remind_about_today_upcoming_delivery']
