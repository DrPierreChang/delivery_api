import functools
import logging
from typing import Type

from django.conf import settings

import googlemaps
import googlemaps.convert
from geopy import exc

from radaro_utils.helpers import chunks
from radaro_utils.signals import google_api_request_event
from routing.google.const import ApiName
from routing.google.geopy import GoogleV3ClientFactory, NominatimClientFactory
from routing.google.googlemaps import GoogleMapsClientFactory
from routing.google.registry import merchant_registry
from routing.google.utils import MapsAPIClientFactory
from routing.utils import get_geo_distance

logger = logging.getLogger('routing.google')


def create_client(*client_factories: Type[MapsAPIClientFactory]):
    def decorator(func):
        @functools.wraps(func)
        def wrapper_client(self, *args, **kwargs):
            track_merchant = kwargs.pop('track_merchant', False)
            channel = merchant_registry.get_google_api_channel() if track_merchant else None
            logger.debug('[Channel] create client %s, track_merchant: %s' % (channel, track_merchant))

            proxies = {'http': settings.GOOGLE_API_PROXY, 'https': settings.GOOGLE_API_PROXY} \
                if settings.GOOGLE_API_PROXY is not None \
                else None

            clients = []
            for factory in client_factories:
                client = factory.create(google_api_key=settings.GOOGLE_API_KEY, timeout=self.timeout,
                                        channel=channel, proxies=proxies)
                clients.append(client)
            result = func(self, *clients, *args, **kwargs)
            for client in clients:
                if hasattr(client, 'session'):
                    client.session.close()
            return result
        return wrapper_client
    return decorator


class GoogleClient(object):
    def __init__(self, timeout=None):
        self.timeout = timeout or settings.GOOGLE_API_TIMEOUT

    @staticmethod
    def track_merchant(merchant):
        return merchant_registry.register(merchant)

    @create_client(GoogleV3ClientFactory, NominatimClientFactory)
    def geocode(self, googlev3_client, nominatim, value, region, **kwargs):
        geocoder_chain = [
            lambda _val, _region: googlev3_client.geocode(_val, region=_region, **kwargs),
            lambda _val, _: nominatim.geocode(_val, **kwargs)
        ]
        for geocode in geocoder_chain:
            for _ in range(3):
                try:
                    return geocode(value, region)
                except (exc.GeocoderTimedOut, exc.GeocoderUnavailable, exc.GeocoderServiceError):
                    continue

    @create_client(GoogleMapsClientFactory)
    def snap_to_roads(self, client, points, interpolate=True):
        def proc(locations):
            locs = []
            distance = 0
            if len(locations) == 0:
                return locs, distance
            pnts = client.snap_to_roads(locations, interpolate=interpolate)
            google_api_request_event.send(None, api_name=ApiName.SNAPPING)
            for ind in range(len(pnts) - 1):
                lat1, lon1, lat2, lon2 = list(pnts[ind]['location'].values()) \
                                         + list(pnts[ind + 1]['location'].values())
                distance += get_geo_distance(lon1, lat1, lon2, lat2)
                locs.append('{latitude},{longitude}'.format(latitude=lat1, longitude=lon1))
            if pnts:
                locs.append('{latitude},{longitude}'.format(**pnts[-1]['location']))
            return locs, distance

        point_locations = [pnt.location for pnt in points]
        if len(point_locations) <= 100:
            return proc(point_locations)
        else:
            last_location = point_locations[0]
            result_path = []
            result_distance = 0
            for chunk in chunks(point_locations, 99):
                path, distance = proc([last_location] + chunk)
                result_path += path
                result_distance += distance
                last_location = path[-1]
            return result_path, result_distance

    @create_client(GoogleMapsClientFactory)
    def directions(self, client, start, end, waypoints=None):
        waypoints = waypoints or []
        options = dict(origin=start, destination=end, waypoints=waypoints, avoid=('ferries',))
        resp = client.directions(**options)
        google_api_request_event.send(None, api_name=ApiName.DIRECTIONS, options=options)
        if not resp:
            return []
        return googlemaps.convert.decode_polyline(resp[0]['overview_polyline']['points'])

    @create_client(GoogleMapsClientFactory)
    def directions_distance(self, client, origin, *points):
        result = []
        while points:
            # Directions request allows maximum 25 waypoints, plus the origin, and destination.
            points_for_request = points[:26]
            waypoints, dest = list(points_for_request[:-1]), points_for_request[-1]

            options = dict(origin=origin, waypoints=waypoints, destination=dest, mode='driving', avoid=('ferries',))
            resp = client.directions(**options)
            google_api_request_event.send(None, api_name=ApiName.DIRECTIONS, options=options)
            if not resp:
                return [0]
            result.extend([leg['distance']['value'] for leg in resp[0]['legs']])

            origin = dest
            points = points[26:]

        return result

    @create_client(GoogleMapsClientFactory)
    def reverse_geocode(self, client, coord, approximate=True, language=None):
        params = {}
        if approximate:
            params['location_type'] = 'approximate'
        if language:
            params['language'] = language
        resp = client.reverse_geocode(coord, **params)
        if resp:
            return resp[0]['formatted_address']
        return ''

    @create_client(GoogleMapsClientFactory)
    def pure_directions_request(self, client, origin, destination, waypoints=None, optimize_waypoints=False):
        options = dict(origin=origin, destination=destination, waypoints=waypoints,
                       optimize_waypoints=optimize_waypoints, avoid=('ferries',))
        google_api_request_event.send(None, api_name=ApiName.DIRECTIONS, options=options)
        return client.directions(**options)

    @create_client(GoogleMapsClientFactory)
    def single_dima_element(self, client, origin, destination, language=None):
        options = dict(origins=[origin], destinations=[destination], avoid='ferries')
        if language:
            options['language'] = language
        res = client.distance_matrix(**options)['rows'][0]['elements'][0]
        google_api_request_event.send(None, api_name=ApiName.DIMA, options=options)
        return res

    @create_client(GoogleMapsClientFactory)
    def single_dima_element_with_polyline(self, client, origin, destination):
        options = dict(origin=origin, destination=destination, avoid='ferries')
        google_api_request_event.send(None, api_name=ApiName.DIRECTIONS, options=options)
        res = client.directions(**options)
        if not res:
            return {'status': 'ZERO_RESULTS'}
        return {**res[0]['legs'][0], 'status': 'OK'}

    @staticmethod
    def glue_polylines(steps):
        if len(steps) == 0:
            return ''
        if len(steps) == 1 and 'polyline' in steps[0]:
            return steps[0]['polyline']['points']

        points = []
        last_point = None
        for step in steps:
            if 'polyline' in step:
                step_points = googlemaps.convert.decode_polyline(step['polyline']['points'])
                for one_point in step_points:
                    if one_point != last_point:
                        last_point = one_point
                        points.append(last_point)

        return googlemaps.convert.encode_polyline(points)
