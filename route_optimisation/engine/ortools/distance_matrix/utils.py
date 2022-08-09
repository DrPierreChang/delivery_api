import asyncio

from route_optimisation.engine.dima import dima_cache
from route_optimisation.engine.utils import filter_from_indexes
from routing.google import GoogleClient


class LocationsList(list):
    def call_directions(self, optimize_waypoints=False):
        origin, waypoints, destination = self[0], self[1:-1], self[-1]
        return dima_cache.pure_directions_request(
            origin, destination, waypoints=waypoints, optimize_waypoints=optimize_waypoints, track_merchant=True
        )

    def filter_from_indices(self, indices):
        return LocationsList(filter_from_indexes(self, indices))


def take_matrix_value(elem):
    result = {
        'duration': elem['duration']['value'],
        'distance': elem['distance']['value'],
    }
    polyline = GoogleClient.glue_polylines(elem.get('steps', []))
    if polyline:
        result['polyline'] = polyline

    return result


# TODO: after moving to python>=3.7 consider using asyncio.run()
class EnsureEventLoopExists:
    def __init__(self):
        self.close_loop = False
        self.loop = None

    def __enter__(self):
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError as ex:
            if "There is no current event loop in thread" in ex.args[0]:
                self.close_loop = True
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)
            else:
                raise
        return self.loop

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.close_loop and self.loop is not None:
            asyncio.set_event_loop(None)
            self.loop.close()
