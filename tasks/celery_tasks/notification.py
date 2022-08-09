from __future__ import absolute_import

from django.utils import timezone

from celery.schedules import crontab
from celery.task import periodic_task

from delivery.celery import app
from notification.models import MerchantMessageTemplate
from tasks.mixins.order_status import OrderStatus
from tasks.models import Customer, Order
from tasks.push_notification.push_messages.event_composers import JobDeadlineMessage, JobSoonDeadlineMessage


@app.task()
def order_deadline_passed(order_id):
    try:
        order = Order.objects.get(
            id=order_id,
            deliver_before__lt=timezone.now(),
            status__in=OrderStatus.status_groups.UNFINISHED,
            deadline_passed=False)

        order.deadline_passed = True
        order.deadline_notified = True
        order.save(update_fields=('deadline_passed', 'deadline_notified'))
        if order.driver_id:
            order.driver.send_versioned_push(JobDeadlineMessage(order=order), async_=False)
    except Order.DoesNotExist:
        pass


@periodic_task(run_every=crontab(minute='*/10'))
def send_notification_about_soon_deadline():
    # from notification.utils import send_notification_for_user
    tz_now = timezone.now()
    to_time = tz_now + timezone.timedelta(minutes=30)
    orders = Order.objects.filter(status__in=OrderStatus.status_groups.UNFINISHED, deliver_before__lte=to_time)
    for order in orders.filter(deadline_notified=False).select_related('driver'):
        if order.driver:
            order.driver.send_versioned_push(JobSoonDeadlineMessage(order), async_=False)
        run_in = int((order.deliver_before - tz_now).total_seconds())
        run_in = run_in + 2 if run_in > 0 else 2
        order_deadline_passed.apply_async(countdown=run_in, args=(order.id,))

    # Some extra situation when there's outdated tasks but not marked as outdated
    # In this case we immediately set them outdated
    for order in orders.filter(deliver_before__lte=tz_now, deadline_passed=False):
        order_deadline_passed(order.id)
    orders.filter(deadline_notified=False).update(deadline_notified=True)


def notify_customer_delayed(order, template_type=MerchantMessageTemplate.CUSTOMER_JOB_STARTED):
    extra_context = {
        "merchant": order.sub_branding or order.merchant,
        "phone_number": (order.sub_branding and order.sub_branding.phone) or order.merchant.phone,
        "url": order.get_order_url()
    }

    order.notify_customer(template_type=template_type, extra_context=extra_context)


__all__ = ['order_deadline_passed', 'send_notification_about_soon_deadline', 'notify_customer_delayed']
