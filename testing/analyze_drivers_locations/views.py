import json
from datetime import datetime

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

import pytz

from driver.path_improving import BuilderSimulatorHelper, SmoothPathBuilder
from radaro_utils.helpers import use_signal_receiver
from radaro_utils.signals import google_api_request_event
from routing.utils import get_geo_distance
from testing.analyze_drivers_locations.utils import TestDriver, TestOrder, transform_location


@csrf_exempt
def simulate_driver_path(request):
    order = json.loads(request.body)
    track = filter(lambda x: x['in_progress_orders'] > 0, order['serialized_track'])

    coordinates_info = []
    coordinates_cumul = [transform_location(track[0])]
    driver = TestDriver()
    for idx, track_item in enumerate(track[1:]):
        coordinate = transform_location(track_item)
        coordinates_cumul.append(coordinate)

        google_requests_count = {'count': 0}
        def count_google_request(*args, **kwargs):
            google_requests_count['count'] += 1
            print('Api request {} {}'.format(args, kwargs))

        builder_helper = BuilderSimulatorHelper(TestOrder(order['deliver_address']['location']), coordinates_cumul)
        with use_signal_receiver(google_api_request_event, count_google_request):
            path_builder = SmoothPathBuilder(None, driver, builder_helper)
            path_builder.build()
            print('\nIndex: {}, Coordinate: {}, Accuracy: {}, Improved:{}'.format(
                idx, coordinate, coordinate.accuracy, builder_helper.improved_location
            ))

        distance_diff = None
        if builder_helper.improved_location:
            loc1 = dict(zip(['lat', 'lng'], tuple(map(float, track_item['location'].split(',')))))
            loc2 = dict(zip(['lat', 'lng'], tuple(map(float, builder_helper.improved_location.split(',')))))
            distance_diff = get_geo_distance(loc1['lng'], loc1['lat'], loc2['lng'], loc2['lat'])

        coord_info = {
            'coordinate': track_item,
            'time': pytz.utc.localize(datetime.utcfromtimestamp(track_item['timestamp'])).strftime('%H:%M:%S'),
            'driver': {
                'expected_driver_route': driver.expected_driver_route,
                'current_path': driver.current_path,
            },
            'improved_location': builder_helper.improved_location,
            're_build_reason': builder_helper.bad_route_info and builder_helper.bad_route_info['re_build_reason'],
            'bad_route_meta': builder_helper.bad_route_info,
            'requests': google_requests_count['count'],
            'distance_diff': distance_diff,
        }
        coordinates_info.append(coord_info)

    return HttpResponse(json.dumps(coordinates_info))
