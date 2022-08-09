import copy
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional

import pytz
from dateutil.parser import parse

from route_optimisation.engine.utils import time_to_seconds


class FieldsToStrAble:
    fields_to_str = None

    def __str__(self):
        inside_str = '; '.join('%s: %s' % (field, getattr(self, field)) for field in self.fields_to_str)
        return f'{self.__class__.__name__}: <{inside_str}>'

    def __repr__(self):
        return str(self)


class Pickup(FieldsToStrAble):
    fields_to_str = ('pickup_id', 'pickup_address', 'pickup_after', 'pickup_before', 'capacity', 'service_time')

    def __init__(self, pickup_id, pickup_address, pickup_after=None, pickup_before=None,
                 capacity=None, service_time=None):
        self.pickup_id = pickup_id
        self.pickup_address = pickup_address
        self.pickup_after = pickup_after
        self.pickup_before = pickup_before
        self.capacity = capacity or 1
        self.service_time = service_time  # minutes

    def to_dict(self):
        return {
            'pickup_id': self.pickup_id,
            'pickup_address': self.pickup_address,
            'pickup_after': self.pickup_after,
            'pickup_before': self.pickup_before,
            'capacity': self.capacity,
            'service_time': self.service_time,
        }

    @classmethod
    def from_dict(cls, value: dict):
        return cls(**value)


class Job(FieldsToStrAble):
    fields_to_str = ('id', 'order_id', 'driver_member_id',
                     'deliver_address', 'deliver_after', 'deliver_before',
                     'pickups',
                     'capacity', 'skill_set', 'service_time', 'allow_skip',)

    def __init__(self, id, order_id, driver_member_id, deliver_address, deliver_before, deliver_after=None,
                 pickup_address=None, pickup_after=None, pickup_before=None, pickups=None,
                 capacity=None, skill_set=None, service_time=None, allow_skip=True):
        self.id = id
        self.order_id = order_id
        self.driver_member_id = driver_member_id
        self.deliver_address = deliver_address
        self.deliver_after = deliver_after
        self.deliver_before = deliver_before
        if pickups:
            self.pickups = [Pickup(**pickup) for pickup in pickups]
        else:
            self.pickups = [Pickup(id, pickup_address, pickup_after, pickup_before, capacity)] \
                if pickup_address else []
        self.capacity = capacity or 1
        self.skill_set: Optional[List[int]] = skill_set
        self.service_time: Optional[int] = service_time  # minutes
        self.allow_skip = allow_skip

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'driver_member_id': self.driver_member_id,
            'deliver_address': self.deliver_address,
            'deliver_after': self.deliver_after,
            'deliver_before': self.deliver_before,
            'pickups': [p.to_dict() for p in self.pickups],
            'capacity': self.capacity,
            'skill_set': self.skill_set,
            'service_time': self.service_time,
            'allow_skip': self.allow_skip,
        }

    @classmethod
    def from_dict(cls, value: dict):
        return cls(**value)

    @property
    def deliver_after_sec(self):
        if self.deliver_after is None:
            t = timedelta()
        else:
            deliver_after = parse(self.deliver_after)
            midnight = deliver_after.replace(hour=0, minute=0, second=0, microsecond=0)
            t = deliver_after - midnight
        return int(t.total_seconds())

    @property
    def deliver_before_sec(self):
        if self.deliver_before is None:
            t = timedelta(hours=24)
        else:
            deliver_before = parse(self.deliver_before)
            zero_time = deliver_before.replace(hour=0, minute=0, second=0, microsecond=0)
            t = deliver_before - zero_time
        return int(t.total_seconds())


class Hub(FieldsToStrAble):
    fields_to_str = ('id', 'location')

    def __init__(self, id, location):
        self.id = id
        self.location = location

    def to_dict(self):
        return {
            'id': self.id,
            'location': self.location,
        }

    @classmethod
    def from_dict(cls, value: dict):
        return cls(**value)


class Location(FieldsToStrAble):
    fields_to_str = ('location', 'id', 'address',)

    def __init__(self, location, address='', id=None):
        self.location = location
        self.address = address
        self.id = id

    def to_dict(self):
        return {
            'id': self.id,
            'location': self.location,
            'address': self.address,
        }

    @classmethod
    def from_dict(cls, value: dict):
        return cls(**value)


class DriverBreak(FieldsToStrAble):
    fields_to_str = ('start_time', 'end_time', 'diff_allowed',)

    def __init__(self, start_time, end_time, diff_allowed=None):
        self.start_time = start_time
        self.end_time = end_time
        self.diff_allowed: int = int(diff_allowed or 0)  # minutes

    def to_dict(self):
        return {
            'start_time': self.start_time,
            'end_time': self.end_time,
            'diff_allowed': self.diff_allowed,
        }

    @classmethod
    def from_dict(cls, value: dict):
        return cls(**value)


class Driver(FieldsToStrAble):
    UNLIMITED_CAPACITY = 100000

    fields_to_str = ('id', 'member_id', 'start_time', 'end_time', 'start_hub', 'end_hub',
                     'start_location', 'end_location', 'capacity', 'skill_set', 'breaks',)

    def __init__(
            self, id, member_id,
            start_time=None, end_time=None,
            start_hub=None, end_hub=None,
            start_location=None, end_location=None,
            working_windows=None, capacity=None, skill_set=None,
            breaks=None,
    ):
        self.id = id
        self.member_id = member_id
        self.start_time = start_time
        self.end_time = end_time
        self.start_hub = start_hub and Hub(**start_hub)
        self.end_hub = end_hub and Hub(**end_hub)
        self.start_location = start_location and Location(**start_location)
        self.end_location = end_location and Location(**end_location)
        self.working_windows = working_windows
        self.capacity = capacity or self.UNLIMITED_CAPACITY
        self.skill_set = skill_set
        self.breaks = [DriverBreak(**driver_break) for driver_break in (breaks or [])]

    def to_dict(self):
        return {
            'id': self.id,
            'member_id': self.member_id,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'start_hub': self.start_hub.to_dict() if self.start_hub is not None else None,
            'end_hub': self.end_hub.to_dict() if self.end_hub is not None else None,
            'start_location': self.start_location.to_dict() if self.start_location is not None else None,
            'end_location': self.end_location.to_dict() if self.end_location is not None else None,
            'capacity': self.capacity,
            'skill_set': self.skill_set,
            'breaks': [br.to_dict() for br in self.breaks],
        }

    @classmethod
    def from_dict(cls, value: dict):
        return cls(**value)

    @property
    def start_time_sec(self):
        return time_to_seconds(self.start_time)

    @property
    def end_time_sec(self):
        return time_to_seconds(self.end_time)


class JobKind(str, Enum):
    HUB = 'hub'
    LOCATION = 'location'
    PICKUP = 'pickup'
    DELIVERY = 'delivery'


class SequenceItem:
    def __init__(self, point_id, point_kind):
        self.point_id = point_id
        self.point_kind = point_kind

    def __str__(self):
        return '({}, {})'.format(self.point_kind, self.point_id)

    def __repr__(self):
        return str(self)

    def to_dict(self):
        return {
            'point_id': self.point_id,
            'point_kind': self.point_kind,
        }

    @classmethod
    def from_dict(cls, value: dict):
        return cls(**value)


class RequiredStartSequence:
    def __init__(self, driver_member_id, sequence):
        self.driver_member_id = driver_member_id
        self.sequence = sequence

    def __str__(self):
        return '<Required start sequence. driver member id: {}, sequence: {}>'.format(
            self.driver_member_id, self.sequence
        )

    def __repr__(self):
        return str(self)

    def to_dict(self):
        return {
            'driver_member_id': self.driver_member_id,
            'sequence': [s.to_dict() for s in self.sequence],
        }

    @classmethod
    def from_dict(cls, value: dict):
        value['sequence'] = [SequenceItem.from_dict(s) for s in value['sequence']]
        return cls(**value)


class EngineParameters:
    def __init__(self, timezone, default_job_service_time, default_pickup_service_time, day, focus,
                 optimisation_options=None,
                 jobs=None, drivers=None, use_vehicle_capacity=None, required_start_sequence=None):
        self.timezone = timezone
        self.default_job_service_time = default_job_service_time
        self.default_pickup_service_time = default_pickup_service_time
        self.day = day
        self.focus = focus
        jobs = optimisation_options.get('jobs', []) if optimisation_options else jobs
        self.jobs = [Job(**job) for job in jobs]
        drivers = optimisation_options.get('drivers', []) if optimisation_options else drivers
        self.drivers = [Driver(**driver) for driver in drivers]
        self.use_vehicle_capacity = optimisation_options.get('use_vehicle_capacity', False) \
            if optimisation_options else use_vehicle_capacity

        self.required_start_sequence = None
        required_start_sequence = optimisation_options.get('required_start_sequence', []) \
            if optimisation_options else required_start_sequence
        if required_start_sequence:
            sequences = []
            for sequence_setting in required_start_sequence:
                seq = [SequenceItem(**item) for item in sequence_setting['sequence']]
                sequences.append(RequiredStartSequence(sequence_setting['driver_member_id'], seq))
            self.required_start_sequence = sequences

    def to_dict(self):
        required_start_sequence = [sequence.to_dict() for sequence in self.required_start_sequence] \
            if self.required_start_sequence else None
        return {
            'day': str(self.day),
            'default_job_service_time': self.default_job_service_time,
            'default_pickup_service_time': self.default_pickup_service_time,
            'drivers': [driver.to_dict() for driver in self.drivers],
            'focus': self.focus,
            'jobs': [job.to_dict() for job in self.jobs],
            'required_start_sequence': required_start_sequence,
            'timezone': self.timezone.zone,
            'use_vehicle_capacity': self.use_vehicle_capacity,
        }

    @classmethod
    def from_dict(cls, value):
        val = copy.copy(value)
        val['timezone'] = pytz.timezone(val['timezone'])
        val['day'] = datetime.strptime(val['day'], "%Y-%m-%d").date()
        return cls(**val)
