from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from driver.models import DriverLocation
from routing.utils import dump_track
from tasks.celery_tasks import generate_driver_path
from tasks.models import Order


class Path:
    __slots__ = ('path', 'real_path', 'duration', 'serialized_track', 'order_distance',
                 'starting_point', 'changed_in_offline')

    def __init__(self, path=None, real_path=None, duration=timezone.timedelta(0), serialized_track=None,
                 distance=0, starting_point=None, offline=False, status=None, **kwargs):
        self.path = {status: path} if (status and path) else path or {}
        self.real_path = {status: [loc.location for loc in real_path]} if (status and real_path) else real_path or {}
        self.duration = duration
        self.serialized_track = serialized_track or []
        self.order_distance = distance
        self.starting_point = starting_point
        self.changed_in_offline = offline

    def __add__(self, other):
        params = {
            'path': dict(self.path, **other.path),
            'real_path': dict(self.real_path, **other.real_path),
            'duration': self.duration + other.duration,
            'serialized_track': self.serialized_track + other.serialized_track,
            'distance': self.order_distance + other.order_distance,
            'starting_point': self.starting_point,
            'changed_in_offline': self.changed_in_offline | other.changed_in_offline
        }
        return Path(**params)

    def __bool__(self):
        return bool(self.duration)

    def to_dict(self):
        attrs = {f: getattr(self, f, None) for f in self.__slots__}
        return attrs


def dump_order_track(folder, order_id):
    dump_track(folder, '{}_gps_track.gpx'.format(order_id), Order.objects.get(id=order_id).path)


def restore_path(order_id):
    order = Order.objects.get(id=order_id)
    evs = order.events.filter(field='status').order_by('happened_at')

    # Access first happened_at and last
    first_in_progress = evs.filter(new_value=Order.IN_PROGRESS).first()

    # If there's some unassign events after first in_progress then stop execution
    # Otherwise restore path
    ha = first_in_progress.happened_at
    if not evs.filter(happened_at__gt=ha, new_value__in=[Order.ASSIGNED, Order.NOT_ASSIGNED]).exists():

        # Deleting duplicating events
        evs.filter(new_value=Order.IN_PROGRESS, happened_at__gt=ha).delete()

        # Check if there are locations between restore points and completed event
        last_deliv = evs.filter(new_value=Order.DELIVERED).last()
        if last_deliv:
            locations_len = DriverLocation.objects.filter(member=last_deliv.object.driver, accuracy__lte=settings.MAX_ACCURACY_RANGE)\
                .filter(Q(created_at__gte=ha) & Q(created_at__lte=last_deliv.happened_at)).count()
            if locations_len:
                # Regenerate order path and started_at param
                generate_driver_path(last_deliv.object)
                Order.objects.filter(id=order_id).update(started_at=first_in_progress.happened_at)
