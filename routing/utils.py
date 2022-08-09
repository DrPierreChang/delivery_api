from __future__ import absolute_import

import math
import operator as op_
import os

import gpxpy
import gpxpy.gpx
import shapely.geometry


def dump_track(folder, name, points):
    """
    :param folder: Name of folder to save
    :param name: Name of the gps track
    :param points: String array of lat,lng points
    :return: None
    """
    folder_path = folder + '/' if folder else ''
    if not os.path.exists(folder_path):
        os.mkdir(folder_path)
    gpx = gpxpy.gpx.GPX()

    # Create first track in our GPX:
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)

    # Create first segment in our GPX track:
    gpx_segment = gpxpy.gpx.GPXTrackSegment()
    gpx_track.segments.append(gpx_segment)

    for point in [list(map(float, p_str.split(','))) for p_str in points]:
        gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(*point))

    with open(name, 'wt') as f:
        f.write(gpx.to_xml())


def get_geo_distance(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = tuple(map(math.radians, [lon1, lat1, lon2, lat2]))
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return 6371000 * c


def y2lat(y):
    return 180.0 / math.pi * (2.0 * math.atan(math.exp(y * math.pi / 180.0)) - math.pi / 2.0)


def lat2y(lat):
    return 180.0 / math.pi * math.log(math.tan(math.pi / 4.0 + lat * (math.pi / 180.0) / 2.0))


def location_to_point(location):
    """ Convert dict location to point as (x, y)-tuple
    :param location: Location as dictionary {'lat': 42.123456, 'lng': 24.654321}
    :return: Tuple of x and y (24.654321, 44.777777). Latitude should be converted to `y`.
    """
    return location['lng'], lat2y(location['lat'])


def point_to_location(point):
    """ Convert (x, y)-tuple to dict location
    :param point: Tuple of x and y (24.654321, 44.777777)
    :return: Location as dictionary {'lat': 42.123456, 'lng': 24.654321}. 'y' should be converted to `latitude`
    """
    return {'lat': y2lat(point[1]), 'lng': point[0]}


def meters2decimal_degree(meters, latitude):
    return meters / (111.32 * 1000 * math.cos(latitude * (math.pi / 180)))


def circle_intersection(circle_center, line_start, line_end, radius):
    center_point, line_start_point, line_end_point = tuple(map(location_to_point, (circle_center, line_start, line_end)))
    radius_decimal_degrees = meters2decimal_degree(radius, circle_center['lat'])
    circle = shapely.geometry.Point(*center_point).buffer(radius_decimal_degrees).boundary
    line = shapely.geometry.LineString([line_start_point, line_end_point])

    intersection = circle.intersection(line)
    if isinstance(intersection, shapely.geometry.Point):
        return [point_to_location((intersection.x, intersection.y))]
    else:
        return list(map(lambda point: point_to_location((point.x, point.y)), intersection.geoms))


def nearest_point_on_line_segment(segment_start, segment_end, point_position):
    """ Finds nearest point on a line segment, that can be reached from `point_position`.

    AB - line segment from `segment_start` to `segment_end`.
    L - `point_position`.

    Example 1. `x` - is a nearest point on the line segment AB. This is a orthogonal projection of point L
           L
           |
           |
    A------x--------------------B

    Example 2. `B` - is a nearest point on the line segment AB.
    We can not make orthogonal projection on line segment, so `B` - is the nearest point
                L
               /
              /
             /
    A-------B

    :param segment_start: (x,y)-tuple
    :param segment_end: (x,y)-tuple
    :param point_position: (x,y)-tuple
    :return: (x,y)-tuple
    """
    point = shapely.geometry.Point(*point_position)
    line = shapely.geometry.LineString([segment_start, segment_end])
    projection = line.interpolate(line.project(point))
    return projection.x, projection.y


def nearest_location_to_line_segment(segment_start_location, segment_end_location, location):
    segment_start_point, segment_end_point, interesting_point = \
        tuple(map(location_to_point, [segment_start_location, segment_end_location, location]))
    nearest_point = nearest_point_on_line_segment(segment_start_point, segment_end_point, interesting_point)
    return point_to_location(nearest_point)


def calculate_initial_compass_bearing(pointA, pointB):
    """
    Calculates the bearing between two points.
    The formulae used is the following:
        theta = atan2(sin(delta(long)).cos(lat2),
                  cos(lat1).sin(lat2) - sin(lat1).cos(lat2).cos(delta(long)))
    :Parameters:
      - `pointA: The tuple representing the latitude/longitude for the
        first (closer) point. Latitude and longitude must be in decimal degrees
      - `pointB: The tuple representing the latitude/longitude for the
        second (further) point. Latitude and longitude must be in decimal degrees
    :Returns:
      The bearing in degrees
    :Returns Type:
      float
    """

    lat1 = math.radians(pointA[0])
    lat2 = math.radians(pointB[0])

    diff_long = math.radians(pointB[1] - pointA[1])

    x = math.sin(diff_long) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1)
                                           * math.cos(lat2) * math.cos(diff_long))

    initial_bearing = math.atan2(x, y)

    # Now we have the initial bearing but math.atan2 return values
    # from -180deg to + 180deg which is not what we want for a compass bearing
    # The solution is to normalize the initial bearing as shown below
    initial_bearing = math.degrees(initial_bearing)
    compass_bearing = (initial_bearing + 360) % 360

    return compass_bearing


def bearing_difference(bearing_1, bearing_2):
    r = (bearing_2 - bearing_1) % 360.0
    if r >= 180.0:
        r -= 360.0
    return r


def bearing_is_near(lead_bearing, slave_bearing, allowed_diff):
    return abs(bearing_difference(lead_bearing, slave_bearing)) <= allowed_diff


def near_points(point_a, point_b, precision=6):
    point_a = {'lat': round(point_a['lat'], precision), 'lng': round(point_a['lng'], precision)}
    point_b = {'lat': round(point_b['lat'], precision), 'lng': round(point_b['lng'], precision)}
    return point_a == point_b


def distance_between(location_one, location_two):
    return get_geo_distance(location_one['lng'], location_one['lat'],
                            location_two['lng'], location_two['lat'])


def latlng_dict(latlng_tuple):
    return dict(zip(['lat', 'lng'], latlng_tuple))


def latlng_dict_from_str(latlng_str):
    latlng_tuple = tuple(latlng_str.split(','))
    return latlng_dict(latlng_tuple)


def filter_driver_path(path, getter=op_.attrgetter):
    def get_params(_item):
        return getters['location'](_item).split(',') + [getters['speed'](_item), getters['accuracy'](_item)]

    getters = {field: getter(field) for field in ('location', 'speed', 'accuracy')}
    a_threshold = 1.39
    b_threshold = 13.9
    new_path = []
    path_length = 0.0
    if not path:
        return new_path, path_length
    initial = path[0]
    new_path.append(initial)
    lat1, lon1, prev_speed, prev_accuracy = get_params(initial)
    for item in path[1:]:
        lat2, lon2, cur_speed, cur_accuracy = get_params(item)
        distance = get_geo_distance(*tuple(map(float, (lon1, lat1, lon2, lat2))))
        prev_coefficient, cur_coefficient = [speed_coefficient(_item, a_threshold, b_threshold)
                                             for _item in (prev_speed, cur_speed)]
        if prev_accuracy * prev_coefficient + cur_accuracy * cur_coefficient < distance:
            lat1, lon1 = lat2, lon2
            prev_speed = cur_speed
            prev_accuracy = cur_accuracy
            new_path.append(item)
            path_length += distance

    return new_path, path_length


def speed_coefficient(speed, a, b):
    if speed > b:
        return 1
    return (1 - a) * speed / b + a
