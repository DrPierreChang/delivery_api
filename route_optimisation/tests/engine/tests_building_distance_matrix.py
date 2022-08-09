from collections import defaultdict

from rest_framework.test import APITestCase

from merchant.factories import MerchantFactory
from radaro_utils.helpers import use_signal_receiver
from radaro_utils.signals import google_api_request_event
from route_optimisation.engine.dima import set_dima_cache
from route_optimisation.engine.ortools.distance_matrix import DistanceMatrixBuilder
from route_optimisation.engine.utils import to_dict_point
from route_optimisation.tests.test_utils.distance_matrix import LocalCacheDiMa
from routing.context_managers import GoogleApiRequestsTracker
from routing.google import ApiName
from routing.google.registry import merchant_registry


class DistanceMatrixBuildingTestCase(APITestCase):
    @classmethod
    def setUpClass(cls):
        super(DistanceMatrixBuildingTestCase, cls).setUpClass()
        cls.eurasia_locations = [
            '53.895341, 27.555138', '53.946616, 27.582595', '53.936808, 27.471752', '53.884533, 27.588595',
            '53.890533, 27.602595', '53.894533, 27.592595', '53.903333, 27.532595', '53.912333, 27.572595',
            '53.895333, 27.531595', '53.873333, 27.582595', '53.923333, 27.512595', '53.921333, 27.562595',
            '53.893333, 27.552595',
        ]
        cls.australia_locations = [
            '-37.880044, 145.019158', '-37.880044, 145.019118', '-37.880044, 145.019128',
        ]
        cls.new_zealand_locations = [
            '-43.536771, 172.641985', '-43.536671, 172.642985', '-43.536571, 172.643985',
        ]
        cls.south_america_locations = [
            '4.692019, -74.075305', '4.734038, -74.068889', '5.823610, -73.025097', '5.839101, -73.033694',
        ]
        cls.merchant = MerchantFactory()

    def build_test_distance_matrix(self, locations, directions_api_calls=None, dima_api_calls=None):
        req_count = defaultdict(int)

        def count_google_request(api_name, *args, **kwargs):
            req_count[api_name] += 1

        points = map(lambda loc: to_dict_point(loc, x_y=False), locations)
        dima_cache = LocalCacheDiMa()
        with use_signal_receiver(google_api_request_event, count_google_request), set_dima_cache(dima_cache):
            with GoogleApiRequestsTracker(limit=60) as tracker:
                builder = DistanceMatrixBuilder(points)
                builder.build_via_directions_api()
            print(tracker.stat)
            dima_cache.cache.clear()

        if directions_api_calls is not None:
            self.assertGreaterEqual(directions_api_calls, req_count[ApiName.DIRECTIONS])
        if dima_api_calls is not None:
            self.assertGreaterEqual(dima_api_calls, req_count[ApiName.DIMA])
        return builder

    def test_locations_on_one_continent(self):
        with merchant_registry.suspend_warning():
            builder = self.build_test_distance_matrix(self.new_zealand_locations, 1, 0)
            self.assertEqual(1, len(builder.components))
            self.assertEqual(len(self.new_zealand_locations)**2, len(builder.matrix))

            builder = self.build_test_distance_matrix(self.eurasia_locations, 7, 0)
            self.assertEqual(1, len(builder.components))
            self.assertEqual(len(self.eurasia_locations)**2, len(builder.matrix))

    def test_locations_on_two_continent(self):
        locations = self.australia_locations + self.eurasia_locations
        with merchant_registry.suspend_warning():
            builder = self.build_test_distance_matrix(locations[:20], 15, 28)
            self.assertEqual(2, len(builder.components))
            builder = self.build_test_distance_matrix(locations[:15], 15, 21)
            self.assertEqual(2, len(builder.components))
            builder = self.build_test_distance_matrix(locations[:10], 8, 15)
            self.assertEqual(2, len(builder.components))
            builder = self.build_test_distance_matrix(locations[:8], 7, 10)
            self.assertEqual(2, len(builder.components))
            builder = self.build_test_distance_matrix(locations[:4], 3, 4)
            self.assertEqual(2, len(builder.components))
            builder = self.build_test_distance_matrix(locations[:3], 1, 0)
            self.assertEqual(1, len(builder.components))

    def test_locations_on_three_continent(self):
        locations = self.australia_locations + self.south_america_locations + self.eurasia_locations
        with merchant_registry.suspend_warning():
            builder = self.build_test_distance_matrix(locations[:], 25, 38)
        self.assertEqual(3, len(builder.components))
