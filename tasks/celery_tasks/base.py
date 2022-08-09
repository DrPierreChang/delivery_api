from __future__ import absolute_import

from django.conf import settings
from django.db import transaction
from django.utils import timezone

import sentry_sdk
from celery.schedules import crontab
from celery.task import periodic_task

from delivery.celery import app
from merchant.models import Merchant
from reporting.context_managers import track_fields_on_change
from reporting.models import Event
from routing.google import GoogleClient
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order


@app.task()
def generate_duration(event_id=None):
    event = Event.objects.filter(id=event_id).first()
    start = Event.objects.filter(
        object_id=event.object_id,
        content_type_id=event.content_type_id,
        new_value=OrderStatus.IN_PROGRESS,
    ).values_list('happened_at', flat=True).last()
    finish = Event.objects.filter(
        object_id=event.object_id,
        content_type_id=event.content_type_id,
        new_value=OrderStatus.DELIVERED,
    ).values_list('happened_at', flat=True).last()
    if not (start and finish) or finish < start:
        return
    duration = finish - start
    Order.objects.filter(id=event.object_id).update(duration=duration)


def generate_driver_path(order):
    with GoogleClient.track_merchant(order.merchant):
        order.finalize_order()


@app.task()
def fail_job(job_id):
    order = Order.objects.filter(id=job_id).first()
    if order:
        with track_fields_on_change(order):
            order.status = OrderStatus.FAILED
            order.save(update_fields=('status',))


@periodic_task(run_every=crontab(hour='*/20'))
def fail_outdated_in_progress_jobs():
    deadline = timezone.now() - timezone.timedelta(days=7)
    failed_orders = Order.objects.filter(status=OrderStatus.IN_PROGRESS, updated_at__lt=deadline)
    with transaction.atomic():
        for order in failed_orders:
            fail_job.delay(order.id)


@periodic_task(run_every=crontab(hour=0, minute=0, day_of_week="monday"), ignore_result=True)
def check_abandoned_webhook_urls():
    for m in Merchant.objects.filter(webhook_failed_times__gte=settings.WEBHOOK_FAIL_LIMIT):
        msg = 'Webhook failed more then {} times. Consider it as abandoned. Merchant ID: ' \
              '{}.'.format(m.webhook_failed_times, m.id)
        sentry_sdk.capture_message(msg, level='WARNING')


__all__ = ['generate_duration', 'generate_driver_path', 'fail_outdated_in_progress_jobs',
           'fail_job', 'check_abandoned_webhook_urls']
