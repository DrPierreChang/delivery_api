import time
from collections import namedtuple
from datetime import timedelta

from django.core.management import BaseCommand
from django.utils import timezone

from base.models import Member
from driver.api.legacy.serializers.location import DriverLocationSerializer
from radaro_utils.helpers import to_timestamp
from tasks.models import Order

FakeRequest = namedtuple('FakeRequest', ('user', 'version'))


class Command(BaseCommand):
    help = 'Replays selected order\'s path.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--order_id',
            action='store',
            dest='order_id',
            required=True,
            help='Order_id of order to replay.',
        )
        parser.add_argument(
            '--driver_id',
            action='store',
            dest='driver_id',
            required=True,
            help='Owner of coordinates.',
        )
        parser.add_argument(
            '--force_timeout',
            action='store',
            dest='force_timeout',
            required=False,
            help='Force timeout.',
        )

    def handle(self, *args, **options):
        _ignore = ('created_at', 'improved_location', 'timestamp')
        order = Order.objects.get(order_id=options['order_id'])
        driver = Member.drivers.get(member_id=options['driver_id'])
        request = FakeRequest(driver, 1)
        track = order.serialized_track
        force_timeout = options.get('force_timeout', None)
        timeouts = [force_timeout] * len(track) \
            if force_timeout \
            else [track[ind + 1]['timestamp'] - track[ind]['timestamp'] for ind, _ in enumerate(track[:-1])]
        for ind, tm in enumerate(timeouts):
            _dt = {a: v for a, v in track[ind].items() if a not in _ignore}
            data = DriverLocationSerializer(data=dict(_dt, timestamp=to_timestamp(timezone.now() - timedelta(seconds=1))),
                                            context={'request': request})
            data.is_valid()
            data.save()
            driver.set_last_ping(with_gps=True)
            time.sleep(float(tm))
