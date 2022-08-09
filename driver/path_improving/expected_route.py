import math

import googlemaps.convert

from routing.utils import (
    bearing_is_near,
    calculate_initial_compass_bearing,
    circle_intersection,
    distance_between,
    latlng_dict,
    near_points,
    nearest_location_to_line_segment,
)


class ExpectedPointInfo(object):
    def __init__(self, distance_to_route, location, segment_index):
        self.distance_to_route = distance_to_route
        self.location = location
        self.segment_index = segment_index


class ExpectedRoute(object):
    MIN_DISTANCE_EXPECTED_ROUTE_IS_VALID = 50
    ALLOWED_ACCURACY = 80
    MIN_DISTANCE_USE_SMOOTH_PATH = 600
    NEAR_ORDER_VALIDATION_DISTANCE = 150
    NEAR_ORDER_VALIDATION_ACCURACY = 30

    def __init__(self, builder, polyline=None):
        self.builder = builder
        self.route = None
        if polyline is not None:
            self.route = googlemaps.convert.decode_polyline(polyline)
        self.valid_point_info = None
        self.valid_prev_point_info = None

    @property
    def is_empty(self):
        return self.route is None or len(self.route) == 0

    def get_max_allowed_distance(self, driver_location):
        if driver_location.accuracy:
            return self._get_accuracy_coefficient(driver_location.accuracy) * driver_location.accuracy
        return self.MIN_DISTANCE_EXPECTED_ROUTE_IS_VALID

    @staticmethod
    def _get_accuracy_coefficient(x, a=1.77, b=8.8, c=-0.19):
        return a + b * math.exp(c * x)

    def set_route(self, new_route):
        self.route = new_route

    def get_path_between_valid_locations(self):
        path = self.route[self.valid_prev_point_info.segment_index+1:self.valid_point_info.segment_index+1]
        path.insert(0, self.valid_prev_point_info.location)
        path.append(self.valid_point_info.location)
        distance = sum(map(lambda x: distance_between(*x), zip(path[:-1], path[1:])))
        if distance > self.MIN_DISTANCE_USE_SMOOTH_PATH:
            return [self.valid_prev_point_info.location, self.valid_point_info.location]
        return path

    def _get_segments_from_expected_route(self):
        segments = zip(self.route[:-1], self.route[1:])
        for segment_index, (from_point, to_point) in enumerate(segments):
            yield segment_index, (from_point, to_point)

    def _nearest_point_for_each_segment(self, location):
        location_value = location.improved_location or location.location
        coordinates = tuple(map(float, location_value.split(',')))
        loc = latlng_dict(coordinates)

        no_segments_returned = True
        for segment_index, (segment_start_location, segment_end_location) in self._get_segments_from_expected_route():
            nearest_loc = nearest_location_to_line_segment(segment_start_location, segment_end_location, loc)
            yield ExpectedPointInfo(distance_between(loc, nearest_loc), nearest_loc, segment_index)
            no_segments_returned = False
        if no_segments_returned:
            nearest_loc = self.route[0]
            yield ExpectedPointInfo(distance_between(loc, nearest_loc), nearest_loc, 0)

    def _check_bearing(self, nearest_point, segment_index, desired_bearing):
        path = self.route[:segment_index+1]
        path.append(nearest_point)
        path = path[-3:]
        start_point, end_point = path[-2:]
        if near_points(start_point, end_point):
            start_point, end_point = path[:2]
        current_bearing = calculate_initial_compass_bearing((start_point['lat'], start_point['lng']),
                                                            (end_point['lat'], end_point['lng']))
        return bearing_is_near(desired_bearing, current_bearing, 60)

    def _find_intersection_point(self, location, radius):
        for segment_index, (start_loc, end_loc) in self._get_segments_from_expected_route():
            intersections = circle_intersection(location, start_loc, end_loc, radius)
            if len(intersections) == 0:
                continue
            elif len(intersections) == 1:
                snapped_location = intersections[0]
            else:
                snapped_location, best_dist = None, float('inf')
                for point in intersections:
                    dist = distance_between(point, start_loc)
                    if dist < best_dist:
                        best_dist = dist
                        snapped_location = point
            return ExpectedPointInfo(distance_between(location, snapped_location), snapped_location, segment_index)
        return None

    def _snap_bad_accuracy_point(self, location, previous_point_info):
        loc = latlng_dict(location.coordinates)
        if distance_between(previous_point_info.location, loc) < location.accuracy:
            best_values = previous_point_info
        else:
            best_values = self._find_intersection_point(loc, location.accuracy)
        return best_values

    def _snap_nearest_point(self, location, check_max_allowed_distance=True, pass_check_bearing=False):
        """
        :param location: DriverLocation object
        :return: ExpectedPointInfo object
        """
        best_values = None
        max_allowed_distance = self.get_max_allowed_distance(location)
        for expected_point_info in self._nearest_point_for_each_segment(location):
            if check_max_allowed_distance and expected_point_info.distance_to_route > max_allowed_distance:
                continue
            is_good_bearing = pass_check_bearing or self._check_bearing(expected_point_info.location,
                                                                        expected_point_info.segment_index,
                                                                        location.bearing)
            if is_good_bearing and (best_values is None
                                    or best_values.distance_to_route > expected_point_info.distance_to_route):
                best_values = expected_point_info
        return best_values

    def snap_to_point(self, location, check_accuracy=True, previous_point_info=None):
        """
        :param location: DriverLocation object
        :param check_accuracy: Should we check bad accuracy or not
        :param previous_point_info: Pass info about previous point
        :return: ExpectedPointInfo object
        """
        if check_accuracy and location.accuracy is not None and location.accuracy >= self.ALLOWED_ACCURACY:
            snapped_point = self._snap_bad_accuracy_point(location, previous_point_info)
            if snapped_point is None:
                snapped_point = self._snap_nearest_point(location, check_max_allowed_distance=False,
                                                         pass_check_bearing=True)
            return snapped_point

        if location.bearing != 0.0:
            nearest_values_with_bearing = self._snap_nearest_point(location)
            if nearest_values_with_bearing is not None:
                return nearest_values_with_bearing
        return self._snap_nearest_point(location, check_max_allowed_distance=False, pass_check_bearing=True)

    def is_valid(self, prev_location, curr_location, enable_log=True):
        if self.is_empty:
            if enable_log:
                self.builder.helper.log_bad_route_info(self, 'none_route')
            return False

        validation_function = self.basic_validation
        if self.builder.nearest_order is not None:
            distance = distance_between(*map(latlng_dict, [
                self.builder.nearest_order.deliver_address.coordinates, curr_location.coordinates
            ]))
            if distance < self.NEAR_ORDER_VALIDATION_DISTANCE:
                validation_function = self.near_order_validation

        return validation_function(prev_location, curr_location, enable_log)

    def near_order_validation(self, prev_location, curr_location, enable_log):
        self.valid_prev_point_info = self.snap_to_point(prev_location, check_accuracy=False)
        self.valid_point_info = self.snap_to_point(curr_location, previous_point_info=self.valid_prev_point_info)

        if curr_location.accuracy < self.NEAR_ORDER_VALIDATION_ACCURACY < self.valid_point_info.distance_to_route:
            self.valid_prev_point_info = None
            self.valid_point_info = None
        return True

    def basic_validation(self, prev_location, curr_location, enable_log):
        self.valid_prev_point_info = self.snap_to_point(prev_location, check_accuracy=False)
        self.valid_point_info = self.snap_to_point(curr_location, previous_point_info=self.valid_prev_point_info)
        max_allowed_distance = self.get_max_allowed_distance(curr_location)
        valid = self.valid_point_info.distance_to_route <= max_allowed_distance

        if valid:
            # Check right order of segments in expected route
            valid = self.valid_prev_point_info.segment_index <= self.valid_point_info.segment_index
            if not valid and enable_log:
                self.builder.helper.log_bad_route_info(self, 'ordering')
        elif enable_log:
            self.builder.helper.log_bad_route_info(self, 'distance', max_allowed_distance=max_allowed_distance)
        return valid

    def encode(self):
        return googlemaps.convert.encode_polyline(self.route)
