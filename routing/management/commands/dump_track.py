import json
import os
import time

from django.core.management import BaseCommand

import gpxpy
import gpxpy.gpx

from tasks.models import Order


def convert_to_gpx(points):
    gpx = gpxpy.gpx.GPX()
    # Create first track in our GPX:
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)

    # Create first segment in our GPX track:
    gpx_segment = gpxpy.gpx.GPXTrackSegment()
    gpx_track.segments.append(gpx_segment)

    for point in [map(float, p_str.split(',')) for p_str in points]:
        gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(*point))
    return gpx.to_xml()


def convert_to_json(points):
    locs = []
    for loc in points:
        loc['timestamp'] = int(time.mktime(loc['created_at'].timetuple()))
        del loc['created_at']
        locs.append(loc)
    return json.dumps(locs)


serializers = {
    'gpx': convert_to_gpx,
    'json': convert_to_json
}


class Command(BaseCommand):
    help = 'Dumps track for you using order jids.'

    def add_arguments(self, parser):
        parser.add_argument(
            'jids',
            nargs='+',
            type=int,
            help='Job ids of tracks to dump.'
        )
        parser.add_argument(
            '--format',
            action='store',
            dest='format',
            required=True,
            help='This is format of track to dump. Choices are: {}.'.format(', '.join(serializers.keys())),
            choices=serializers.keys()
        )
        parser.add_argument(
            '--folder',
            action='store',
            dest='format',
            required=False,
            help='This is output folder.',
        )
        parser.add_argument(
            '--name',
            action='store',
            dest='name',
            required=True,
            help='This is output name.',
        )

    def handle(self, *args, **options):
        folder_path = options.get('folder', '.')
        if folder_path and folder_path[-1] != '/':
            folder_path += '/'
        if not os.path.exists(folder_path):
            os.mkdir(folder_path)
        for jid in options['jids']:
            o = Order.objects.get(order_id=jid)
            if options['format'] == 'gpx':
                path_obj = o.path
            elif options['format'] == 'json':
                path_obj = o.driver.location\
                    .filter(created_at__gte=o.started_at, created_at__lte=o.updated_at)\
                    .order_by('created_at')\
                    .values('location', 'accuracy', 'created_at', 'speed')
            else:
                raise Exception('No supported format was provided.')
            path_content = serializers[options['format']](path_obj)
            with open(options['name'], 'wt') as f:
                f.write(path_content)
