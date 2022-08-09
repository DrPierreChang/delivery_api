from collections import defaultdict
from datetime import datetime
from operator import attrgetter

import pytz

from driver.api.legacy.serializers.location import DriverLocationSerializer
from driver.models import DriverLocation
from tasks.models import Order, OrderLocation


def serialize_order(order_id):
    fields = [
        'driver.first_name', 'driver.last_name', 'driver.id',
        'serialized_track', 'real_path',
        'deliver_address.location', 'order_id',
    ]
    order = Order.objects.select_related('deliver_address', 'driver')\
        .get(id=order_id)
    item = defaultdict(dict)
    for field in fields:
        val = attrgetter(field)(order)

        store = item
        field_key = field.split('.')[0]
        for f_name in field.split('.')[1:]:
            store = store[field_key]
            field_key = f_name
        store[field_key] = val
    return item


class TestDriver(object):
    def __init__(self):
        self.expected_driver_route = None
        self.current_path = None
        self.current_path_updated = None
        self.location_serializer = DriverLocationSerializer

    def serialize_location(self, location):
        return self.location_serializer(location).data

    def _finalize(self, current_path, end):
        return dict(current_path, **{
            'now': self.location_serializer(end).data
        })


class TestOrder(object):
    def __init__(self, location):
        self.deliver_address = OrderLocation(location=location)


def transform_location(dd):
    coordinate = DriverLocation(**dd)
    coordinate.timestamp = pytz.utc.localize(datetime.utcfromtimestamp(coordinate.timestamp))
    coordinate.improved_location = None
    def save_mock(*args, **kwargs): pass
    coordinate.save = save_mock
    return coordinate
