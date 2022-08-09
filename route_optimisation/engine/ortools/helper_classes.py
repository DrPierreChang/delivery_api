from operator import attrgetter
from typing import List

import googlemaps.convert

from .utils import prepare_capacity


class LocationMixin(object):
    def __init__(self, location, *args, **kwargs):
        super(LocationMixin, self).__init__(*args, **kwargs)
        self.location = location

    @property
    def latlng_location(self):
        return googlemaps.convert.latlng(self.location)


class SiteBase(LocationMixin):
    original_id_getter = attrgetter('original_id')
    id_prefix = ''

    def __init__(self, unique_id, location, *args, **kwargs):
        super(SiteBase, self).__init__(location, *args, **kwargs)
        self._unique_id = self._original_id = unique_id

    @property
    def unique_id(self):
        return '%s%s' % (self.id_prefix, str(self._unique_id))

    @property
    def original_id(self):
        return self._original_id

    def get_prototype(self):
        return {'id': self.original_id}


class VehicleBreak:
    __slots__ = ('start_time', 'end_time', 'diff_allowed', 'duration',)

    def __init__(self, start_time: int, end_time: int, diff_allowed: int):
        self.start_time: int = start_time
        self.end_time: int = end_time
        self.diff_allowed: int = diff_allowed * 60  # seconds
        self.duration: int = end_time - start_time


class Vehicle(object):
    UNLIMITED_CAPACITY = prepare_capacity(100000)

    def __init__(self, vehicle_id, start_time, end_time, start_depot=None, end_depot=None,
                 start_location=None, end_location=None, skill_set=None, capacity=None, breaks=None):
        self.end_location = end_location
        self.start_location = start_location
        self.end_time = end_time
        self.start_time = start_time
        self.end_depot = end_depot
        self.start_depot = start_depot
        self.end_site = None
        self.start_site = None
        self.vehicle_id = vehicle_id
        self.skill_set = skill_set or []
        self.capacity = prepare_capacity(capacity) or self.UNLIMITED_CAPACITY
        self.required_start_sequence = None
        self.breaks: List[VehicleBreak] = [VehicleBreak(**b) for b in (breaks or [])]

    def get_start_site(self):
        return self.start_depot or self.start_location or self.start_site

    def get_end_site(self):
        return self.end_depot or self.end_location or self.end_site


class ConcreteLocation(SiteBase):
    id_prefix = 'c_loc_'

    def __init__(self, unique_id, location, address, original_id, *args, **kwargs):
        super(SiteBase, self).__init__(location, *args, **kwargs)
        self._unique_id = unique_id
        self._original_id = original_id
        self.address = address

    def get_prototype(self):
        proto = super().get_prototype()
        proto['location'] = self.latlng_location
        proto['address'] = self.address
        return proto


class Depot(SiteBase):
    id_prefix = 'depot_'


class FakeDepot(Depot):
    def __init__(self, *args, **kwargs):
        super(FakeDepot, self).__init__(0, {'lat': 'Fake', 'lng': 'location'}, *args, **kwargs)


class JobSite(SiteBase):
    def __init__(
            self, order_id, location,
            deliver_before, deliver_after,
            driver_member_id, skill_set=None,
            capacity=None, service_time=None,
            allow_skip=True,
            *args, **kwargs
    ):
        super(JobSite, self).__init__(order_id, location, *args, **kwargs)
        self.driver_member_id = driver_member_id
        self.window_start = deliver_after
        self.window_end = deliver_before
        self.skill_set = skill_set or []
        self.service_time = service_time * 60 if service_time is not None else None  # seconds
        self.capacity = prepare_capacity(capacity or 1)
        self.allow_skip = allow_skip

    def check_vehicle_skills_set(self, veh: Vehicle):
        return not set(self.skill_set).difference(set(veh.skill_set))

    def check_assigned_vehicle(self, veh: Vehicle):
        return self.driver_member_id is not None and veh.vehicle_id == self.driver_member_id

    def is_allowed_vehicle(self, veh: Vehicle):
        return self.driver_member_id is None or veh.vehicle_id == self.driver_member_id


class Pickup(JobSite):
    id_prefix = 'pickup_'

    def __init__(self, parent_order_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_order_id = parent_order_id

    @property
    def unique_id(self):
        return '%s[%s]' % (super().unique_id, self.parent_order_id)

    def get_prototype(self):
        proto = super().get_prototype()
        proto['parent_order_id'] = self.parent_order_id
        return proto


class Delivery(JobSite):
    id_prefix = 'delivery_'
