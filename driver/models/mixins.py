from django.conf import settings
from django.db import models

import sentry_sdk
from constance import config
from jsonfield import JSONField

from driver.path_improving import SmoothPathBuilder
from driver.utils import DriverStatus
from routing.google import GoogleClient
from routing.utils import filter_driver_path


class MemberImprovePathMixin(models.Model):
    track_serializer = None
    location_serializer = None

    current_path = JSONField(blank=True, null=True)
    expected_driver_route = models.TextField(blank=True, null=True)
    current_path_updated = models.DateTimeField(blank=True, null=True)

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        from driver.api.legacy.serializers.location import DriverLocationSerializer
        super(MemberImprovePathMixin, self).__init__(*args, **kwargs)
        self.track_serializer = self.location_serializer = DriverLocationSerializer

    @property
    def should_improve_location(self):
        return self.current_merchant.allowed_path_processing and self.status == DriverStatus.IN_PROGRESS

    def _fill_basic(self, current_path, serialized_locations):
        current_path['path'] = [
            dict(zip(('lat', 'lng'), map(float, (loc['improved_location'] or loc['location']).split(','))))
            for loc in serialized_locations
        ]
        return current_path

    def _finalize(self, current_path, end):
        return dict(current_path, **{
            'id': self.id,
            'now': self.location_serializer(end).data
        })

    def serialize_location(self, location):
        return self.location_serializer(location).data

    def process_location(self, coordinate_id):
        path_builder = SmoothPathBuilder(coordinate_id, self)
        with GoogleClient.track_merchant(self.current_merchant):
            path_builder.build()

    # Path replay functionality
    def _get_route_between_points(self, start, end, speed, before_path):
        current_path = dict()
        serialized_locations = self.location_serializer([start, end], many=True).data
        current_path['before'] = serialized_locations[0]
        if speed < config.IMPROVE_POINT_THRESHOLD_SPEED:
            self._fill_basic(current_path, serialized_locations)
        else:
            try:
                locations = [getattr(p, 'improved_location', p.location) or p.location for p in [start, end]]
                current_path['path'] = GoogleClient().directions(*locations, track_merchant=False)
                if before_path and before_path.get('path', False):
                    current_path['path_before'] = before_path['path']
            except Exception as ex:
                self._fill_basic(current_path, serialized_locations)
                sentry_sdk.capture_exception(ex)
        return current_path

    def get_all_routes(self, track):
        routes = []
        for item in ((start, track[ind + 1], track[ind + 1].speed, None)
                     for ind, start in enumerate(track[:-1])):
            route = self._get_route_between_points(*item)
            routes.append(self._finalize(route, item[1]))
        return routes

    # Finalize order functionality
    def serialize_track(self, start, finish):
        raw_driver_locations = self.location.filter(models.Q(timestamp__gte=start) & models.Q(timestamp__lte=finish))
        driver_locations_list = list(raw_driver_locations.filter(accuracy__lte=settings.MAX_ACCURACY_RANGE))
        if len(driver_locations_list):
            first_location = driver_locations_list[0]
            _path, path_length = filter_driver_path(driver_locations_list)
            if self.current_merchant.allowed_path_processing:
                try:
                    path, path_length = GoogleClient().snap_to_roads(driver_locations_list)
                except Exception as ex:
                    sentry_sdk.capture_exception(ex)
                    path = [pnt.location for pnt in _path]
            else:
                path = [pnt.location for pnt in _path]
        else:
            path = driver_locations_list
            first_location = None
            path_length = 0
        return {
            'path': path,
            'serialized_track': self.track_serializer(raw_driver_locations, many=True).data,
            'distance': path_length,
            'real_path': driver_locations_list,
            'first_location': first_location,
            'offline': raw_driver_locations.filter(offline=True).exists()
        }


__all__ = ['MemberImprovePathMixin']
