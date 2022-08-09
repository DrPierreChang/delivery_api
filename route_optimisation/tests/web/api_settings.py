from datetime import time
from operator import attrgetter
from typing import Dict, Optional

from base.factories import CarFactory, DriverFactory
from base.models import Member
from driver.utils import WorkStatus
from merchant.factories import HubFactory, HubLocationFactory, SkillSetFactory
from merchant.models import Hub, SkillSet
from route_optimisation.const import HubOptions
from route_optimisation.models import DriverRouteLocation
from route_optimisation.tests.factories import DriverRouteLocationFactory
from route_optimisation.tests.test_utils.setting import DriverSetting, HubSetting, LocationSetting, OrderSetting
from routing.google.registry import merchant_registry
from routing.utils import latlng_dict
from schedule.models import Schedule
from tasks.mixins.order_status import OrderStatus
from tasks.models import ConcatenatedOrder, Order
from tasks.tests.factories import OrderFactory, OrderLocationFactory


class APISettings:
    def __init__(self, ro_type, day, timezone, merchant, manager):
        self.merchant = merchant
        self.manager = manager
        self.timezone = timezone
        self.day = day

        self.hubs_map: Dict[int, Hub] = {}
        self.hubs_setting_map: Dict[int, HubSetting] = {}
        self.locations_map: Dict[int, DriverRouteLocation] = {}
        self.locations_setting_map: Dict[int, LocationSetting] = {}
        self.skills_map: Dict[int, SkillSet] = {}
        self.drivers_map: Dict[int, Member] = {}
        self.drivers_setting_map: Dict[int, DriverSetting] = {}
        self.orders_map: Dict[int, Order] = {}
        self.orders_map_for_ro: Dict[int, Order] = {}

        self.ro_type = ro_type
        self.skip_day = False
        self.job_service_time = 0
        self.pickup_service_time = 0
        self.re_optimise_assigned = None
        self.use_vehicle_capacity = None
        self.working_hours = None
        self.start_place = HubOptions.START_HUB.default_hub
        self.start_hub: Optional[int] = None
        self.start_location = None
        self.end_place = HubOptions.END_HUB.default_hub
        self.end_hub: Optional[int] = None
        self.end_location = None

    # Hubs
    def hub(self, location, hub_id):
        hub_setting = self._create_hub_setting(location, hub_id)
        hub = self._create_hub(hub_setting)
        self.hubs_map[hub_id] = hub
        self.hubs_setting_map[hub_id] = hub_setting

    def copy_hubs(self, settings):
        self.hubs_map = settings.hubs_map
        self.hubs_setting_map = settings.hubs_setting_map

    def _create_hub_setting(self, location, hub_id):
        return HubSetting(hub_id, location)

    def _create_hub(self, hub_setting):
        return HubFactory(merchant=self.merchant, location=HubLocationFactory(location=hub_setting.location))

    # Locations
    def location(self, location, location_id, address=''):
        location_setting = self._create_location_setting(location, location_id, address)
        location = self._create_location(location_setting)
        self.locations_map[location_id] = location
        self.locations_setting_map[location_id] = location_setting

    def copy_locations(self, settings):
        self.locations_map = settings.locations_map
        self.locations_setting_map = settings.locations_setting_map

    def _create_location_setting(self, location, location_id, address) -> LocationSetting:
        return LocationSetting(location_id, location, address)

    def _create_location(self, location_setting: LocationSetting) -> DriverRouteLocation:
        with merchant_registry.suspend_warning():
            return DriverRouteLocationFactory(location=location_setting.location, address=location_setting.address)

    # Skills
    def skill(self, skill_id, service_time=None):
        self.skills_map[skill_id] = SkillSetFactory(merchant=self.merchant, service_time=service_time)

    def copy_skills(self, settings):
        self.skills_map = settings.skills_map

    # Drivers
    def driver(self, member_id, *args, **kwargs):
        driver_setting = self._create_driver_setting(member_id, *args, **kwargs)
        driver = self._create_driver(driver_setting)
        self.drivers_map[member_id] = driver
        self.drivers_setting_map[member_id] = driver_setting

    def copy_drivers(self, settings):
        self.drivers_map = settings.drivers_map
        self.drivers_setting_map = settings.drivers_setting_map

    def _create_driver_setting(self, member_id, start_hub=None, end_hub=None, start_location=None, end_location=None,
                               default_point=None, skill_set=None, *args, **kwargs):
        skill_set = set(skill_set or []).intersection(self.skills_map.keys())
        return DriverSetting(
            member_id,
            start_hub=start_hub and self.hubs_setting_map[start_hub],
            end_hub=end_hub and self.hubs_setting_map[end_hub],
            start_location=start_location and self.locations_map[start_location],
            end_location=end_location and self.locations_map[end_location],
            default_point=default_point and self.locations_setting_map[default_point].to_dict(),
            skill_set=skill_set,
            *args, **kwargs
        )

    def _create_driver(self, driver_setting):
        driver = DriverFactory(
            merchant=self.merchant,
            work_status=WorkStatus.WORKING,
            starting_hub_id=self.hubs_map[driver_setting.start_hub.hub_id].id if driver_setting.start_hub else None,
            ending_hub_id=self.hubs_map[driver_setting.end_hub.hub_id].id if driver_setting.end_hub else None,
            ending_point=HubLocationFactory(**driver_setting.default_point) if driver_setting.default_point else None,
            car=CarFactory(capacity=driver_setting.capacity),
        )
        schedule, _ = Schedule.objects.get_or_create(member=driver)
        schedule.schedule['constant'][self.day.weekday()]['start'] = driver_setting.start_time
        schedule.schedule['constant'][self.day.weekday()]['end'] = driver_setting.end_time
        schedule.schedule['constant'][self.day.weekday()]['day_off'] = driver_setting.day_off
        breaks = [{'start': item.start_time, 'end': item.end_time} for item in driver_setting.breaks]
        if breaks:
            schedule.schedule['one_time'][self.day] = {'breaks': breaks}
        schedule.save(update_fields=('schedule',))
        if driver_setting.skill_set:
            driver.skill_sets.set(list(map(lambda skill_id: self.skills_map[skill_id], driver_setting.skill_set)))
        return driver

    # Orders
    def order(self, order_id, *args, **kwargs):
        order_setting = self._create_order_setting(order_id, *args, **kwargs)
        order = self._create_order(order_setting)
        self.orders_map[order_id] = order
        self.orders_map_for_ro[order_id] = order

    def _create_order_setting(self, order_id, deliver_address, driver=None, skill_set=None, *args, **kwargs):
        skill_set = set(skill_set or []).intersection(self.skills_map.keys())
        return OrderSetting(
            order_id, deliver_address, driver=driver and self.drivers_setting_map[driver],
            deliver_date=self.day, timezone=self.timezone, skill_set=skill_set,
            *args, **kwargs
        )

    def _create_order(self, order_setting):
        deliver_after = order_setting.make_deliver_after()
        deliver_before = order_setting.make_deliver_before()
        pickup_after = order_setting.make_pickup_after()
        pickup_before = order_setting.make_pickup_before()
        order_status = OrderStatus.ASSIGNED if order_setting.driver else OrderStatus.NOT_ASSIGNED
        driver = order_setting.driver and self.drivers_map[order_setting.driver.driver_id]
        pickup_location = OrderLocationFactory(location=order_setting.pickup_address) \
            if order_setting.pickup_address else None
        order = OrderFactory(
            merchant=self.merchant, manager=self.manager, driver=driver,
            deliver_address=OrderLocationFactory(location=order_setting.location),
            status=order_status, deliver_after=deliver_after, deliver_before=deliver_before,
            pickup_address=pickup_location, pickup_after=pickup_after, pickup_before=pickup_before,
            capacity=order_setting.capacity,
        )
        if order_setting.skill_set:
            order.skill_sets.set(list(map(lambda skill_id: self.skills_map[skill_id], order_setting.skill_set)))
        return order

    def concatenated_order(self, order_id, orders):
        real_order_ids = [self.orders_map[o].id for o in orders]
        orders_qs = Order.objects.filter(id__in=real_order_ids)
        new_concatenated_order = ConcatenatedOrder.objects.create_from_order(orders_qs.first())
        orders_qs.update(concatenated_order=new_concatenated_order)
        new_concatenated_order.update_data()
        self.orders_map[order_id] = new_concatenated_order
        self.orders_map_for_ro[order_id] = new_concatenated_order
        for order in orders:
            del self.orders_map_for_ro[order]

    # Other options
    def service_time(self, minutes):
        self.job_service_time = minutes

    def set_pickup_service_time(self, minutes):
        self.pickup_service_time = minutes

    def set_start_place(self, hub=None, location=None):
        if hub:
            self.start_place = HubOptions.START_HUB.hub_location
            self.start_hub = hub
            self.start_location = None
        elif location:
            self.start_place = HubOptions.START_HUB.driver_location
            self.start_hub = None
            self.start_location = location
        else:
            self.start_place = HubOptions.START_HUB.default_hub
            self.start_hub = None
            self.start_location = None

    def set_end_place(self, hub=None, location=None, last_job=False, default_point=False):
        if hub:
            self.end_place = HubOptions.END_HUB.hub_location
            self.end_hub = hub
            self.end_location = None
        elif location:
            self.end_place = HubOptions.END_HUB.driver_location
            self.end_hub = None
            self.end_location = location
        elif last_job:
            self.end_place = HubOptions.END_HUB.job_location
            self.end_hub = None
            self.end_location = None
        elif default_point:
            self.end_place = HubOptions.END_HUB.default_point
            self.end_hub = None
            self.end_location = None
        else:
            self.end_place = HubOptions.END_HUB.default_hub
            self.end_hub = None
            self.end_location = None

    def set_re_optimise_assigned(self, value):
        self.re_optimise_assigned = value

    def set_use_vehicle_capacity(self, value):
        self.use_vehicle_capacity = value

    def set_working_hours(self, lower=None, upper=None):
        lower = lower or (9, 0)
        upper = upper or (17, 0)
        self.working_hours = {'lower': str(time(*lower)), 'upper': str(time(*upper))}

    # Help methods
    def build_request_options(self):
        orders_ids = list(map(attrgetter('id'), self.orders_map_for_ro.values()))
        drivers_ids = list(map(attrgetter('id'), self.drivers_map.values()))
        start_location, end_location = None, None
        if self.start_location:
            start_location = self._convert_location_str2dict(self.locations_map[self.start_location].location)
        if self.end_location:
            end_location = self._convert_location_str2dict(self.locations_map[self.end_location].location)
        options = dict(
            jobs_ids=orders_ids, drivers_ids=drivers_ids,
            start_place=self.start_place,
            start_hub=self.hubs_map[self.start_hub].id if self.start_hub else None,
            start_location=start_location,
            end_place=self.end_place,
            end_hub=self.hubs_map[self.end_hub].id if self.end_hub else None,
            end_location=end_location,
        )
        if self.re_optimise_assigned is not None:
            options['re_optimise_assigned'] = self.re_optimise_assigned
        if self.use_vehicle_capacity is not None:
            options['use_vehicle_capacity'] = self.use_vehicle_capacity
        if self.working_hours is not None:
            options['working_hours'] = self.working_hours
        if self.job_service_time:
            options['service_time'] = self.job_service_time
        if self.pickup_service_time:
            options['pickup_service_time'] = self.pickup_service_time
        return options

    def _convert_location_str2dict(self, loc):
        latlng_tuple = tuple(map(float, loc.split(',')))
        return {'location': latlng_dict(latlng_tuple)}


class SoloAPISettings(APISettings):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initiator_driver = None
        self.initiator_driver_setting = None

    def set_initiator_driver(self, driver):
        self.initiator_driver = self.drivers_map[driver]
        self.initiator_driver_setting = self.drivers_setting_map[driver]

    def build_solo_request_data(self):
        start_location, end_location = None, None
        if self.start_location:
            start_location = self._convert_location_str2dict(self.locations_map[self.start_location].location)
        if self.end_location:
            end_location = self._convert_location_str2dict(self.locations_map[self.end_location].location)
        request_data = {'options': dict(
            start_hub=self.hubs_map[self.start_hub].id if self.start_hub else None,
            start_location=start_location,
            end_hub=self.hubs_map[self.end_hub].id if self.end_hub else None,
            end_location=end_location,
        )}
        if not self.skip_day:
            request_data['day'] = str(self.day)
        return request_data
