from operator import attrgetter

from django.utils import timezone

import googlemaps.convert
import sentry_sdk

from driver.path_improving.expected_route import ExpectedRoute
from driver.path_improving.helper_strategy import BasicHelper
from routing.google import GoogleClient
from routing.utils import latlng_dict


class SmoothPathBuilder(object):
    WINDOW_SIZE = 5

    def __init__(self, coordinate_id, driver, helper=None):
        if helper is None:
            helper = BasicHelper(coordinate_id)
        self.helper = helper

        self.driver = driver
        last_locations = self.helper.get_locations(self)
        if len(last_locations) == 1:
            last_locations.append(None)  # Prevent error on next line when only one location returned
        self.curr_location, self.prev_location = last_locations[:2]
        self.last_locations = list(reversed(last_locations))
        self.should_improve = self.helper.should_improve(self)
        self.expected_route = ExpectedRoute(builder=self, polyline=self.driver.expected_driver_route)
        self.nearest_order = None

    def update_expected_route(self):
        if self.nearest_order is None:
            self.expected_route.set_route([])
            self.driver.expected_driver_route = self.expected_route.encode()
            return

        points = None
        try:
            matched, _ = GoogleClient().snap_to_roads(self.last_locations, interpolate=False)
            if matched:
                points = matched[-self.WINDOW_SIZE:]
        except Exception as exc:
            sentry_sdk.capture_exception(exc)
        if points is None:
            points = list(map(attrgetter('location'), self.last_locations))
        points.append(self.nearest_order.deliver_address.location)
        self.expected_route.set_route(
            GoogleClient().directions(points[0], points[-1], waypoints=points[1:-1], track_merchant=True)
        )
        self.driver.expected_driver_route = self.expected_route.encode()

    def update_current_path(self):
        current_path = {}
        if self.should_improve:
            current_path = self._get_path_from_expected_route()
        self.driver.current_path = self.driver._finalize(current_path, self.curr_location)
        self.driver.current_path_updated = timezone.now()

    def _get_path_from_expected_route(self):
        before_path = self.driver.current_path
        if self.expected_route.valid_point_info is None:
            prev_location_value = self.prev_location.improved_location or self.prev_location.location
            prev_coordinates = tuple(map(float, prev_location_value.split(',')))
            path = list(map(latlng_dict, [prev_coordinates, self.curr_location.coordinates]))
        else:
            path = self.expected_route.get_path_between_valid_locations()
        current_path = {'path': path, 'before': self.driver.serialize_location(self.prev_location)}
        if before_path and before_path.get('path', False):
            current_path['path_before'] = before_path['path']
        return current_path

    def build(self):
        self.nearest_order = self.helper.get_nearest_order(self)
        if self.should_improve:
            if not self.expected_route.is_valid(self.prev_location, self.curr_location):
                self.update_expected_route()
                self.expected_route.is_valid(self.prev_location, self.curr_location, enable_log=False)
            if self.expected_route.valid_point_info is not None:
                expected_location = self.expected_route.valid_point_info.location
                self.curr_location.improved_location = googlemaps.convert.latlng(expected_location)
                self.helper.log_improved_location(self.curr_location.improved_location)
                self.curr_location.save(update_fields=('improved_location',))
        self.update_current_path()
