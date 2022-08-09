from __future__ import absolute_import

import datetime

from django.conf import settings
from django.utils import timezone, translation
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from notification.models import MerchantMessageTemplate
from notification.utils import format_upcoming_delivery_time


def generate_data_for_remind_upcoming_delivery(order):
    template_type = MerchantMessageTemplate.UPCOMING_DELIVERY
    upcoming_delivery_upper_bound = datetime.timedelta(seconds=settings.CUSTOMER_MESSAGES['upcoming_delivery_timeout']
                                                       + settings.CUSTOMER_MESSAGES['task_period'])
    now = timezone.now()

    merchant = order.merchant
    merchant_tz = merchant.timezone
    now_in_merchant_tz = now.astimezone(merchant_tz)

    upper_bound = order.deliver_before.astimezone(merchant_tz)
    lower_bound = order.deliver_after.astimezone(merchant_tz) if order.deliver_after else \
        upper_bound - datetime.timedelta(hours=order.merchant.delivery_interval)

    with translation.override(merchant.language):

        welcome_text, day_postfix = '', ''

        if upper_bound.date() != now_in_merchant_tz.date():
            delta = upper_bound - now_in_merchant_tz
            if delta.total_seconds() >= upcoming_delivery_upper_bound.total_seconds():
                delivery_day = date_format(order.deliver_before.astimezone(merchant_tz), 'E j')
                day_postfix = _('on {delivery_day}').format(delivery_day=delivery_day)
                template_type = MerchantMessageTemplate.INSTANT_UPCOMING_DELIVERY
            else:
                day_postfix = _('tomorrow')
            welcome_text = _('Good news! ')

        if merchant.instant_upcoming_delivery:
            template_type = MerchantMessageTemplate.INSTANT_UPCOMING_DELIVERY

        hours_interval = '{start} - {end}'.format(
            start=format_upcoming_delivery_time(order.customer, lower_bound),
            end=format_upcoming_delivery_time(order.customer, upper_bound)
        )

        time_interval = hours_interval if not day_postfix else '{hours_interval} {day}' \
            .format(hours_interval=hours_interval, day=day_postfix)

        context = {
            'time_interval': time_interval,
            'hours_interval': hours_interval,
            'delivery_day': day_postfix or _('today'),
            'welcome_text': welcome_text,
            'merchant': order.sub_branding or order.merchant,
            'customer_address': order.deliver_address.address,
            'url': order.get_order_url(),
        }

    return template_type, context


def generate_data_for_today_remind_upcoming_delivery(order):
    template_type = MerchantMessageTemplate.TODAY_UPCOMING_DELIVERY
    merchant_tz = order.merchant.timezone

    upper_bound = order.deliver_before.astimezone(merchant_tz)
    lower_bound = (
        order.deliver_after.astimezone(merchant_tz) if order.deliver_after
        else upper_bound - datetime.timedelta(hours=order.merchant.delivery_interval)
    )

    hours_interval = '{start} - {end}'.format(
        start=format_upcoming_delivery_time(order.customer, lower_bound),
        end=format_upcoming_delivery_time(order.customer, upper_bound)
    )

    context = {
        'time_interval': hours_interval,
        'merchant': order.sub_branding or order.merchant,
        'url': order.get_order_url(),
    }

    return template_type, context
