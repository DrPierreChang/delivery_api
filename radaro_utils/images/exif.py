from datetime import datetime

import pytz


def prepare_exif_float_tuple(float_tuple):
    # Conversion example: ((10, 1), (10, 1), (1234, 100)) -> (10, 10, 1.234)
    return tuple(
        number if offset == 1 else (number * 1. / offset)
        for (number, offset) in float_tuple,
    )


def prepare_exif_gps_location(ref, gps_location):
    # Conversion example: N, ((52, 1), (29, 1), (2253, 100)) -> 52.489592
    gps_location = prepare_exif_float_tuple(gps_location)
    prepared_location = gps_location[0] + gps_location[1] / 60.0 + gps_location[2] / 3600.0
    if ref in ['S', 'W']:
        prepared_location = -prepared_location

    return prepared_location


def prepare_exif_gps_datetime(date, time):
    dt = datetime.strptime(date, '%Y:%m:%d')
    gps_time = prepare_exif_float_tuple(time)
    dt = dt.replace(hour=int(gps_time[0]), minute=int(gps_time[1]), second=int(gps_time[2]))
    dt = pytz.utc.localize(dt)
    return dt


def prepare_exif_gps(exif_gps):
    from PIL import ExifTags
    exif_gps = {
        ExifTags.GPSTAGS[key]: value
        for key, value in exif_gps.items()
        if key in ExifTags.GPSTAGS
    }

    required_field = ['GPSLatitudeRef', 'GPSLatitude', 'GPSLongitudeRef', 'GPSLongitude']
    for field in required_field:
        if field not in exif_gps:
            return (None, None, None)

    lat = prepare_exif_gps_location(exif_gps['GPSLatitudeRef'], exif_gps['GPSLatitude'])
    lon = prepare_exif_gps_location(exif_gps['GPSLongitudeRef'], exif_gps['GPSLongitude'])

    required_field = ['GPSDateStamp', 'GPSTimeStamp']
    for field in required_field:
        if field not in exif_gps:
            return (lat, lon, None)

    dt = prepare_exif_gps_datetime(exif_gps['GPSDateStamp'], exif_gps['GPSTimeStamp'])
    return lat, lon, dt
