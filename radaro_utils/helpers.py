import calendar
import json
from datetime import datetime

from django.conf import settings
from django.db.models import Func

from rest_framework.serializers import ValidationError

import pytz
from constance import config


def chunks(l, n, length=None, since=0):
    """
    Yield successive n-sized chunks from l.
    Have possibility to override length not to call len().
    """
    if length is None:
        length = len(l)
    for i in range(since, length, n):
        yield l[i:i + n]


def validate_photos_count(photos):
    max_count = config.CONFIRM_PHOTOS_UPLOAD_LIMIT
    if len(photos) > max_count:
        raise ValidationError('Too many photos. Must be no more than %s photos.' % max_count)
    return photos


def to_timestamp(value):
    ms = value.microsecond / 1000000.
    return calendar.timegm(value.utctimetuple()) + ms


def spaces_to_underscores(string_):
    return '_'.join(string_.split(' ')).lower()


def is_compatible_type(value, type_):
    try:
        type_(value)
        return True
    except ValueError:
        return False


class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()

        return json.JSONEncoder.default(self, o)


def utc_localize_from_timestamp(timestamp):
    return pytz.utc.localize(datetime.utcfromtimestamp(timestamp))


class use_signal_receiver(object):
    def __init__(self, signal, receiver):
        self.signal = signal
        self.receiver = receiver

    def __enter__(self):
        self.signal.connect(self.receiver)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.signal.disconnect(self.receiver)


def DateUTCOffset(expression, utc_offset, default_tz: str = settings.TIME_ZONE, **extra):
    '''
        Custom query expression to get date from datetime object with
        time zone offset.

        Example usage
        queryset.annotate(
            created_date=DateUTCOffset('created_at', '3:00:00')
        )
    '''

    class DateWithTZ(Func):
        function = 'DATE'

        template = "%(function)s(%(expressions)s AT TIME ZONE (select coalesce(" \
                   "(select name from pg_timezone_names where utc_offset='{timezone}' limit 1), '{default_tz}')))" \
            .format(timezone=utc_offset, default_tz=default_tz)

    return DateWithTZ(expression, **extra)


def DateInTimezone(expression, timezone, **extra):
    """
        Custom query expression to get date from datetime object with
        time zone.

        Example usage
        queryset.annotate(
            created_date=DateInTimezone('created_at', 'Europe/Minsk')
        )
    """

    class DateWithTZ(Func):
        function = 'DATE'

        template = "%(function)s(%(expressions)s AT TIME ZONE '{timezone}')".format(timezone=str(timezone))

    return DateWithTZ(expression, **extra)
