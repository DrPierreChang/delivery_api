from __future__ import absolute_import, unicode_literals

import itertools as it_
import operator as op_

from django.conf import settings
from django.db import transaction

import celery

from delivery.celery import app
from radaro_utils import compat
from radaro_utils.search import watson_index_bulk_update
from reporting.models import Event
from reporting.signals import send_create_event_signal
from tasks.models import Order
from tasks.models.bulk import BulkDelayedUpload
from tasks.push_notification.utils import send_notifications_for_assigned_jobs_by_bulk


def get_bulk(_bulk):
    if isinstance(_bulk, int):
        return BulkDelayedUpload.objects.select_related('creator').get(id=_bulk)
    return _bulk


@app.task(ignore_result=False)
def create_orders_from_prototypes(_bulk, *slice):
    bulk = get_bulk(_bulk)
    bulk.create_orders(*slice)
    return True


@app.task()
def process_bulk_created_orders(_bulk, set_confirmation=False):
    bulk = get_bulk(_bulk)
    if set_confirmation:
        bulk.confirm()
        bulk.save()

    created_orders = Order.objects.filter(bulk=bulk)
    created_orders = created_orders.select_related('manager', 'merchant')
    created_orders = created_orders.prefetch_related('skill_sets', 'terminate_codes', 'labels', 'barcodes', 'skids')

    events = []
    for order in created_orders:
        events.append(Event(object=order, obj_dump=order.order_dump, initiator=order.manager,
                            merchant_id=order.merchant_id, event=Event.CREATED))

    events = Event.objects.bulk_create(events)
    send_create_event_signal(events=events)

    for order in created_orders:
        order.remind_about_upcoming_delivery()
    watson_index_bulk_update(created_orders)
    orders = Order.objects.filter(bulk=bulk, status=Order.ASSIGNED).select_related('driver').order_by('driver')
    send_notifications_for_assigned_jobs_by_bulk(it_.groupby(orders, op_.attrgetter('driver')))


def bulk__create_jobs(bulk, async_=False, set_confirmation=True):
    jobs_len = bulk.prototypes.filter(processed=False).count()
    batch_sz = settings.BULK_JOB_CREATION_BATCH_SIZE

    slices = zip(compat.range(0, jobs_len + batch_sz, batch_sz), compat.range(batch_sz, jobs_len + batch_sz, batch_sz))
    if async_:
        celery.chord((
            create_orders_from_prototypes.s(bulk.id, sl1, sl2)
            for sl1, sl2 in slices
        ), process_bulk_created_orders.si(bulk.id, set_confirmation=set_confirmation))()
    else:
        for sl1, sl2 in slices:
            create_orders_from_prototypes(bulk.id, sl1, sl2)
        if set_confirmation:
            bulk.confirm()
            bulk.save()
        transaction.on_commit(process_bulk_created_orders.si(bulk.id).delay)


__all__ = ['create_orders_from_prototypes', 'process_bulk_created_orders', 'bulk__create_jobs']
