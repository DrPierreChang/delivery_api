from django.conf import settings
from django.db import models
from django.utils import timezone

from celery.schedules import crontab
from celery.task import periodic_task

from base.models import Member
from delivery.celery import app
from driver.models import DriverLocation
from radaro_utils.helpers import use_signal_receiver
from radaro_utils.signals import google_api_request_event
from reporting.context_managers import track_fields_on_change
from reporting.signals import create_event


@periodic_task(run_every=crontab(minute='*/1'))
def check_internet_connection():
    from base.models import Member
    delta = timezone.now() - timezone.timedelta(seconds=settings.DRIVER_INTERNET_CONNECTION_TIMEOUT)
    for member in Member.drivers.filter(has_internet_connection=True, last_ping__lt=delta):
        old_dict = {'has_internet_connection': True}
        new_dict = {'has_internet_connection': False}

        member.has_internet_connection = False
        member.save(update_fields=['has_internet_connection'])

        create_event(
            old_dict, new_dict, initiator=member, instance=member, sender=member,
            track_change_event=('has_internet_connection',)
        )


@periodic_task(run_every=crontab(hour=0, minute=0, day_of_week="monday"), time_limit=10*60)
def delete_driver_locations():
    delta = timezone.now() - timezone.timedelta(days=7)
    DriverLocation.objects.filter(created_at__lte=delta, last_driver__isnull=True).delete()


@app.task()
def process_new_location(driver_id, coordinate_id):
    from base.models import Member
    from tasks.models import OrderStatus

    driver = Member.objects.get(id=driver_id)
    driver.last_location_id = coordinate_id
    DriverLocation.objects.filter(id=coordinate_id).update(
        google_request_cost=driver.current_merchant.price_per_location_processing,
        in_progress_orders=driver.order_set.filter(status=OrderStatus.IN_PROGRESS).count()
    )

    google_requests_count = {'count': 0}

    def count_google_request(*args, **kwargs):
        google_requests_count['count'] += 1

    update_fields = ['last_location_id']
    try:
        with use_signal_receiver(google_api_request_event, count_google_request):
            driver.process_location(coordinate_id)
            update_fields.extend(['current_path', 'current_path_updated', 'expected_driver_route'])
    finally:
        driver.save(update_fields=update_fields)
        if google_requests_count['count'] > 0:
            DriverLocation.objects.filter(id=coordinate_id) \
                .update(google_requests=models.F('google_requests') + google_requests_count['count'])


@app.task()
def stop_active_orders_of_driver(driver_id):
    from radaro_utils import helpers
    from tasks.models import Order
    driver = Member.all_objects.filter(id=driver_id).first()
    if driver is None:
        return

    orders_qs = Order.objects.filter(driver_id=driver_id)

    assigned_orders = orders_qs.filter(status=Order.ASSIGNED)
    for order_list in helpers.chunks(assigned_orders, 50):
        with track_fields_on_change(order_list, initiator=driver, sender=Member):
            for order in order_list:
                order.status = Order.NOT_ASSIGNED
                order.driver = None
                order.save()

    active_orders = orders_qs.filter(status__in=Order.status_groups.ACTIVE_DRIVER)
    for order_list in helpers.chunks(active_orders, 50):
        with track_fields_on_change(order_list, initiator=driver, sender=Member):
            for order in order_list:
                order.status = Order.FAILED
                order.save()
