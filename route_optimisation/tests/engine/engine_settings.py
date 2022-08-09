from typing import Dict, List

from route_optimisation.const import MerchantOptimisationFocus
from route_optimisation.tests.test_utils.setting import (
    DriverSetting,
    HubSetting,
    LocationSetting,
    OrderSetting,
    SkillSetting,
)


class EngineSettings:
    def __init__(self, day, timezone, focus=MerchantOptimisationFocus.ALL):
        self.timezone = timezone
        self.day = day
        self.focus = focus
        self.skill_sets: Dict[int, SkillSetting] = {}
        self.hubs: Dict[int, HubSetting] = {}
        self.locations: Dict[int, LocationSetting] = {}
        self.drivers: List[DriverSetting] = []
        self.drivers_map: Dict[int, DriverSetting] = {}
        self.orders: List[OrderSetting] = []
        self.job_service_time = 0
        self.pickup_service_time = 0
        self.use_vehicle_capacity = False
        self.start_sequences = []

    def hub(self, location, hub_id=None):
        self.hubs[hub_id] = HubSetting(hub_id, location)

    def skill(self, skill_id, service_time=None):
        self.skill_sets[skill_id] = SkillSetting(skill_id, service_time)

    def location(self, location, location_id=None):
        self.locations[location_id] = LocationSetting(location_id, location)

    def driver(
            self, member_id, start_hub=None, end_hub=None,
            start_location=None, skill_set=None, breaks=None,
            *args, **kwargs
    ):
        skill_set = set(skill_set or []).intersection(self.skill_sets.keys())
        driver = DriverSetting(
            member_id,
            start_hub and self.hubs[start_hub],
            end_hub and self.hubs[end_hub],
            start_location=start_location and self.locations[start_location],
            skill_set=skill_set, breaks=breaks or [],
            *args, **kwargs
        )
        self.drivers.append(driver)
        self.drivers_map[member_id] = driver

    def order(self, order_id, deliver_address, driver=None, skill_set=None, *args, **kwargs):
        skill_set = skill_set or []
        skill_set = [self.skill_sets[skill_id] for skill_id in skill_set if skill_id in self.skill_sets]
        order = OrderSetting(
            order_id, deliver_address, driver=driver and self.drivers_map[driver],
            deliver_date=self.day, timezone=self.timezone, skill_set=skill_set,
            *args, **kwargs
        )
        self.orders.append(order)

    def service_time(self, minutes):
        self.job_service_time = minutes

    def set_pickup_service_time(self, minutes):
        self.pickup_service_time = minutes

    def add_start_sequence(self, sequence):
        self.start_sequences.append(sequence)
