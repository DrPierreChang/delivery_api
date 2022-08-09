import copy
import logging
import operator as op_
from datetime import timedelta

from django.utils import timezone

from constance import config
from geopy import distance as geo_distance

from routing.utils import filter_driver_path


class LocationLogger(object):
    LOCATIONS_DISTANCE = 'locations-distance'
    TRACK_DISTANCE = 'track-distance',
    TIMEOUT = 'timeout'
    NO_DATA = 'no-data'

    location_saved_str = 'Locations saved. Reason: {}. Is array: {}'
    location_ignored_str = 'Locations ignored. Reason: {}. Is array: {}'
    saving_data = 'Saving next locations: {}'

    def __init__(self):
        self._logger = logging.getLogger(__name__)

    def saved(self, reason, is_array):
        self._logger.info(self.location_saved_str.format(reason, is_array))

    def ignored(self, reason, is_array):
        self._logger.info(self.location_ignored_str.format(reason, is_array))

    def info(self, data):
        self._logger.info(self.saving_data.format(str(data)))


logger = LocationLogger()


def prepare_locations_from_serializer(serializer, last_location, is_offline, location_data=None):
    DISTANCE_THRESHOLD = config.DISTANCE_THRESHOLD  # meters
    TIMEOUT_THRESHOLD = timedelta(seconds=4 * 60 + 30)

    serializer.is_valid(raise_exception=True)
    location_data = location_data if location_data is not None else serializer.validated_data

    if not location_data:
        logger.ignored(logger.NO_DATA, 'unknown')
        return

    logger.info(location_data)
    if not last_location:
        serializer.save(offline=is_offline)
        return

    time_diff = timezone.now() - last_location.created_at
    is_many = isinstance(location_data, list)

    if time_diff >= TIMEOUT_THRESHOLD:
        serializer.save(offline=is_offline)
        logger.saved(logger.TIMEOUT, is_many)
        return

    new_location = location_data[-1] if is_many else location_data
    distance = geo_distance.geodesic(
        *[list(map(float, _loc.split(','))) for _loc in (last_location.location, new_location['location'])]
    )

    if is_many:
        track, track_distance = filter_driver_path(
            copy.copy(location_data),
            getter=op_.itemgetter
        )
        if distance.meters > DISTANCE_THRESHOLD or track_distance > DISTANCE_THRESHOLD:
            serializer.save(offline=True)
            logger.saved(
                logger.LOCATIONS_DISTANCE if distance.meters > DISTANCE_THRESHOLD else logger.TRACK_DISTANCE,
                True
            )
        else:
            logger.ignored('{} and {}'.format(logger.LOCATIONS_DISTANCE, logger.TRACK_DISTANCE), True)
    elif distance.meters > DISTANCE_THRESHOLD:
        serializer.save()
        logger.saved(logger.LOCATIONS_DISTANCE, False)
    else:
        logger.ignored(LocationLogger.LOCATIONS_DISTANCE, False)
