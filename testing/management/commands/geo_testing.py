import json

from django.core.management import BaseCommand

from testing.settings import TIMEOUT
from testing.tests.geo import Tester


class Command(BaseCommand):
    help = 'Closes the specified poll for voting'

    def add_arguments(self, parser):
        parser.add_argument('tests', nargs='+', type=str)
        parser.add_argument(
            '--env',
            action='store',
            dest='env',
            default='staging',
            required=False,
            help='Environment to load. Default: {}.'.format('staging'),
        )
        parser.add_argument(
            '--gpx',
            action='store',
            dest='gpx',
            required=True,
            help='Name of gpx track to load and use. Required.',
        )
        parser.add_argument(
            '--timeout',
            action='store',
            dest='timeout',
            default=TIMEOUT,
            help='Timeout before sending coordinates. Default {}s.'.format(TIMEOUT),
            type=float
        )
        parser.add_argument(
            '--customer',
            action='store',
            dest='customer',
            required=False,
            help='Customer data in JSON. Should consist of email, name, phone.',
            type=str
        )
        parser.add_argument(
            '--path_index',
            action='store',
            dest='path_index',
            required=False,
            help='Path Index.',
            type=int
        )

    def handle(self, *args, **options):
        tester = Tester(options['env'])
        kw = {}
        for test in options['tests']:
            kw['timeout'] = options.get('timeout', TIMEOUT)
            kw['path_index'] = options.get('path_index', None)
            customer = options.get('customer')
            if customer:
                kw['customer'] = json.loads(customer)
            getattr(tester, test)(options['gpx'], **kw)
