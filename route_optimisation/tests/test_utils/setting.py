import random
from datetime import datetime, time
from operator import attrgetter
from typing import Iterable, List


class HubSetting:
    def __init__(self, hub_id, location):
        self.hub_id = hub_id
        self.location = location
        self._id = random.random()

    def to_dict(self):
        return dict(
            id=self.hub_id,
            location=self.location,
        )


class SkillSetting:
    def __init__(self, skill_id, service_time=None):
        self.skill_id = skill_id
        self.service_time = service_time


class LocationSetting:
    def __init__(self, location_id, location, address=''):
        self.location_id = location_id
        self.location = location
        self.address = address
        self._id = random.random()

    def to_dict(self):
        return dict(
            location=self.location,
            address=self.address
        )


class DriverBreakSetting:
    def __init__(self, start_time, end_time, diff_allowed=None):
        self.start_time = time(*start_time)
        self.end_time = time(*end_time)
        self.diff_allowed = diff_allowed

    def to_dict(self):
        return dict(
            start_time=str(self.start_time),
            end_time=str(self.end_time),
            diff_allowed=self.diff_allowed,
        )


class DriverSetting:
    def __init__(
            self, driver_id,
            start_hub: HubSetting = None, end_hub: HubSetting = None,
            start_time=None, end_time=None, day_off=False,
            start_location=None, end_location=None, default_point=None,
            existing_driver=None, skill_set=None,
            capacity=None, breaks: Iterable[DriverBreakSetting] = None
    ):
        self.skill_set: List[int] = skill_set or []
        self.end_location = end_location
        self.start_location = start_location
        self.default_point = default_point
        self.existing_driver = existing_driver
        self.driver_id = driver_id
        self.start_hub: HubSetting = start_hub
        self.end_hub: HubSetting = end_hub
        start_time, end_time = start_time or (8,), end_time or (21,)
        self.start_time = time(*start_time)
        self.end_time = time(*end_time)
        self.day_off = day_off
        self.capacity = capacity
        self.breaks: Iterable[DriverBreakSetting] = breaks or []

    def to_dict(self):
        return dict(
            id=self.driver_id,
            member_id=self.driver_id,
            start_time=str(self.start_time),
            end_time=str(self.end_time),
            start_hub=self.start_hub.to_dict() if self.start_hub else None,
            end_hub=self.end_hub.to_dict() if self.end_hub else None,
            start_location=self.start_location.to_dict() if self.start_location else None,
            end_location=self.end_location.to_dict() if self.end_location else None,
            skill_set=list(self.skill_set),
            capacity=self.capacity,
            breaks=[driver_break.to_dict() for driver_break in self.breaks]
        )


class PickupSetting:
    def __init__(self, pickup_id, pickup_address, timezone, deliver_date,
                 pickup_after_time=None, pickup_before_time=None,
                 capacity=None, service_time=None):
        self.pickup_id = pickup_id
        self.pickup_address = pickup_address
        self.timezone = timezone
        self.deliver_date = deliver_date
        self.pickup_after_time = pickup_after_time
        self.pickup_before_time = pickup_before_time
        self.capacity = capacity
        self.service_time = service_time

    def make_pickup_after(self):
        return self.timezone.localize(datetime.combine(self.deliver_date, self.pickup_after_time)) \
            if self.pickup_after_time else None

    def make_pickup_before(self):
        return self.timezone.localize(datetime.combine(self.deliver_date, self.pickup_before_time)) \
            if self.pickup_before_time else None

    def to_dict(self):
        pickup_after = self.make_pickup_after()
        pickup_before = self.make_pickup_before()
        return dict(
            pickup_id=self.pickup_id,
            pickup_address=self.pickup_address,
            pickup_after=pickup_after.isoformat() if pickup_after else None,
            pickup_before=pickup_before.isoformat() if pickup_before else None,
            capacity=self.capacity,
            service_time=self.service_time,
        )


class OrderSetting:
    def __init__(
            self, order_id, deliver_address, deliver_date=None,
            deliver_after_time=None, deliver_before_time=None,
            pickup_address=None, pickup_after_time=None, pickup_before_time=None,
            driver=None, timezone=None, skill_set=None, capacity=None,
            service_time=None, pickups=None, allow_skip=True,
    ):
        self.order_id = order_id
        self.location = deliver_address
        deliver_before_time = deliver_before_time or (23, 59, 59)
        self.deliver_after_time = time(*deliver_after_time) if deliver_after_time else None
        self.deliver_before_time = time(*deliver_before_time)
        self.pickup_address = pickup_address
        self.pickup_after_time = time(*pickup_after_time) if pickup_after_time else None
        self.pickup_before_time = time(*pickup_before_time) if pickup_before_time else None
        self.pickups = [PickupSetting(**pickup_args, timezone=timezone, deliver_date=deliver_date)
                        for pickup_args in (pickups or [])]
        self.driver = driver
        self.deliver_date = deliver_date
        self.timezone = timezone
        self.capacity = capacity
        self.service_time = service_time
        self.skill_set: List[SkillSetting] = skill_set or []
        self.allow_skip = allow_skip

    def make_deliver_after(self):
        return self.timezone.localize(datetime.combine(self.deliver_date, self.deliver_after_time)) \
            if self.deliver_after_time else None

    def make_pickup_after(self):
        return self.timezone.localize(datetime.combine(self.deliver_date, self.pickup_after_time)) \
            if self.pickup_after_time else None

    def make_pickup_before(self):
        return self.timezone.localize(datetime.combine(self.deliver_date, self.pickup_before_time)) \
            if self.pickup_before_time else None

    def make_deliver_before(self):
        return self.timezone.localize(datetime.combine(self.deliver_date, self.deliver_before_time))

    def calc_service_time(self):
        service_time = None
        for skill in self.skill_set:
            if skill.service_time is not None:
                service_time = (service_time or 0) + skill.service_time
        return service_time if service_time is not None else self.service_time

    def to_dict(self):
        deliver_after = self.make_deliver_after()
        pickup_after = self.make_pickup_after()
        pickup_before = self.make_pickup_before()
        return dict(
            id=self.order_id,
            order_id=self.order_id,
            driver_member_id=self.driver and self.driver.driver_id,
            deliver_address=self.location,
            deliver_after=deliver_after.isoformat() if deliver_after else None,
            deliver_before=self.make_deliver_before().isoformat(),
            pickup_address=self.pickup_address,
            pickup_after=pickup_after.isoformat() if pickup_after else None,
            pickup_before=pickup_before.isoformat() if pickup_before else None,
            pickups=list(map(lambda pickup: pickup.to_dict(), self.pickups)),
            skill_set=list(map(attrgetter('skill_id'), self.skill_set)),
            service_time=self.calc_service_time(),
            capacity=self.capacity,
            allow_skip=self.allow_skip,
        )
