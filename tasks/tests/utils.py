import base64
import json
import os
import random
import re
from datetime import timedelta
from itertools import starmap

from django.utils import timezone

from six.moves import xrange

from merchant.models import Merchant
from reporting.models import Event
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

from .base_test_cases import BaseOrderTestCase

date_formats = {
    Merchant.LITTLE_ENDIAN: "%d/%m/%Y %X",
    Merchant.MIDDLE_ENDIAN: "%m/%d/%Y %X",
    Merchant.BIG_ENDIAN: "%Y-%m-%d %X"
}


class CreateOrderCSVTextMixin(object):
    default_headers = 'Customer name*,Job address*,Driver ID,Pickup after,Pickup deadline,Deliver after,Job deadline,' \
                      'Comment,Customer_Email,Customer Phone,Reference,Labels,Barcodes,Skill Sets'
    item_template = '{customer_name},"{job_address}",{driver_id},{pickup_after},{pickup_deadline},{deliver_after},' \
                    '{job_deadline},{comment},{customer_email},{customer_phone},{reference},{labels},{barcodes},' \
                    '{skill_sets}\n'

    bounds = ((56.10, 23.11), (51.16, 32.47))

    def rand_str(self, ind):
        return base64.b16encode(os.urandom(1 + ind))

    @classmethod
    def create_csv_text(cls, orders, date_format=Merchant.LITTLE_ENDIAN, headers=None):
        first_string = headers if headers else cls.default_headers + '\n'
        res = first_string
        for order in orders:
            customer = getattr(order, 'customer', None)
            driver = getattr(order, 'driver', None)
            pickup_after = getattr(order, 'pickup_after', '')
            pickup_before = getattr(order, 'pickup_before', '')
            deliver_after = getattr(order, 'deliver_after', '')
            deliver_before = getattr(order, 'deliver_before', '')
            deliver_address = getattr(order, 'deliver_address', None)
            deliver_location = getattr(deliver_address, 'location', None)
            barcodes = [{"code_data": "Test code " + str(int(random.uniform(1, 1000000)))}]

            res += cls.item_template.format(
                customer_name=getattr(customer, 'name', ''),
                job_address=deliver_location or deliver_address or '',
                driver_id=getattr(driver, 'id', None) or '',
                pickup_after=pickup_after.strftime(date_formats[date_format]) if pickup_after else '',
                pickup_deadline=pickup_before.strftime(date_formats[date_format]) if pickup_before else '',
                deliver_after=deliver_after.strftime(date_formats[date_format]) if deliver_after else '',
                job_deadline=deliver_before.strftime(date_formats[date_format]) if deliver_before else '',
                comment=getattr(order, 'comment', None) or '',
                customer_email=getattr(customer, 'email', ''),
                customer_phone=getattr(customer, 'phone', None) or '',
                reference=getattr(order, 'title', ''),
                labels='',
                barcodes=json.dumps(barcodes),
                skill_sets=''
            )
        return res

    def create_random_csv(self, compose, length=8):
        csv_compose = {
            'customer_name': self.rand_str,
            'job_deadline': lambda ind: str(timezone.now() + timedelta(days=ind + 1)),
            'job_address': lambda ind: '{},{}'.format(*starmap(random.uniform, zip(*self.bounds)))
        }
        all_headers = re.sub(r'[\"\{\}]', '', self.item_template[:-1]).split(',')
        _csv_compose = dict(csv_compose, **compose)
        bd = []
        for _ind in xrange(length):
            bd.append(self.item_template.format(**{h: _csv_compose.get(h, lambda ind: '')(_ind) for h in all_headers}))
        return self.default_headers + '\n' + ''.join(bd)


class CreateJobsForReportMixin(BaseOrderTestCase):
    @classmethod
    def setUpTestData(cls):
        super(CreateJobsForReportMixin, cls).setUpTestData()
        cls.steps = (
            (slice(4, None),
             {
                 'status': OrderStatus.ASSIGNED,
                 'driver_id': cls.driver.id,
                 'updated_at': timezone.now()
             }),
            (slice(8, None),
             {
                 'status': OrderStatus.IN_PROGRESS,
                 'updated_at': timezone.now()
             }),
            (slice(10, 13),
             {
                 'status': OrderStatus.DELIVERED,
                 'updated_at': timezone.now()
             }),
            (slice(13, None),
             {
                 'status': OrderStatus.FAILED,
                 'updated_at': timezone.now()
             })
        )

    def get_steps(self, scale):
        steps = ((slice(sl.start * scale, sl.stop * scale if sl.stop is not None else None), _)
                 for sl, _ in self.steps)
        return steps

    def apply_delta(self, objects, delta):
        Model = type(objects[0])
        Model.objects.filter(id__in=[o.id for o in objects]).update(**delta)
        for k, v in delta.items():
            Event.objects.bulk_create(Event(
                event=Event.CHANGED,
                field=k,
                new_value=v,
                merchant=self.merchant,
                initiator=self.manager,
                object=o
            ) for o in objects)
        Event.objects.bulk_create(Event(
            event=Event.MODEL_CHANGED,
            merchant=self.merchant,
            initiator=self.manager,
            object=o,
            obj_dump={"old_values": {k: getattr(o, k) for k in delta}, "new_values": delta}
        ) for o in objects)

    def create_orders_for_report(self, steps, size):
        real_driver = self.driver
        self.driver = None
        orders = self.default_order_batch(size=size, status=OrderStatus.NOT_ASSIGNED)
        Order.objects.create_bulk_events(orders)
        self.driver = real_driver
        for part, delta in steps:
            self.apply_delta(orders[part], delta=delta)
