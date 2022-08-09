from collections import Iterable, namedtuple
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType

from celery.task import periodic_task
from geopy.exc import GeocoderTimedOut

from delivery.celery import app
from tasks.api.legacy.serializers.bulk import OrderPrototypeChunkSerializer as _BulkExternalJobSerializer
from tasks.celery_tasks.bulk import bulk__create_jobs
from tasks.models.external import ExternalJob

from .models import RevelSystem
from .utils import get_data_for_external_job


@periodic_task(run_every=timedelta(minutes=5))
def import_jobs():
    for id in RevelSystem.objects.filter(importing=False).values_list('id', flat=True):
        get_external_orders_from_revel.delay(id)


@app.task(time_limit=60 * 30)
def get_external_orders_from_revel(sales_system_id):
    rs = RevelSystem.objects.get(id=sales_system_id)

    rs.importing = True
    rs.save(update_fields=['importing'])

    update_fields = ['importing']

    try:
        if not rs.merchant.is_blocked:
            if rs.last_update:
                order_packs = rs.orders_pack.filter(updated_date__gte=rs.last_update)\
                                            .filter(customer__isnull=False)\
                                            .expand(customer=True)
            else:
                order_packs = rs.orders_pack.filter(customer__isnull=False)\
                                                .expand(customer=True)

            for order_pack in order_packs:
                build_order_from_revel.delay(rs.id, order_pack)
    except Exception as e:
        print(e)
    else:
        update_fields.append('modified')
    finally:
        rs.importing = False
        rs.save(update_fields=update_fields)


@app.task(bind=True, max_retries=5)
def build_order_from_revel(self, rs_id, orders):
    rs = RevelSystem.objects.get(id=rs_id)
    if not isinstance(orders, Iterable):
        orders = [orders, ]

    source = rs
    source_type = ContentType.objects.get_for_model(source.__class__)

    external_ids = [x.id for x in orders]

    map_external_to_internal = dict(ExternalJob.objects.filter(external_id__in=external_ids)
                                    .values_list('external_id', 'id'))

    external_jobs_raw = []
    for order in orders:
        if str(order.id) in map_external_to_internal:
            continue
        try:
            data = get_data_for_external_job(order)
        except GeocoderTimedOut as exc:
            num_retries = self.retries
            seconds_to_wait = 2.0 * num_retries
            raise self.retry(exc=exc, countdown=seconds_to_wait)
        except Exception as exc:
            raise
        else:
            data['source_type'] = source_type.pk
            data['source_id'] = rs.id

            external_jobs_raw.append(data)

    Request = namedtuple('Request', ['user'])
    request = Request(user=rs.merchant.member_set.first())

    bulk_serializer = _BulkExternalJobSerializer(data=external_jobs_raw, context={'request': request})
    bulk = bulk_serializer.validate_and_save()
    bulk__create_jobs(bulk, async_=True)
