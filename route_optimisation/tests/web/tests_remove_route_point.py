from operator import itemgetter

from django.test import override_settings

from rest_framework import status
from rest_framework.test import APITestCase

from route_optimisation.const import OPTIMISATION_TYPES, RoutePointKind

from .api_settings import APISettings
from .mixins import ORToolsMixin
from .optimisation_expectation import OptimisationExpectation


@override_settings(ORTOOLS_SEARCH_TIME_LIMIT=1, ORTOOLS_SEARCH_TIME_LIMIT_WITH_PICKUP=1)
class RemoveRoutePointTestCase(ORToolsMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.manager)
        self.settings = APISettings(OPTIMISATION_TYPES.ADVANCED, self._day, self.merchant.timezone,
                                    self.merchant, self.manager)
        self.settings.hub('-37.869197,144.820283', hub_id=1)
        self.settings.hub('-37.868197,144.820183', hub_id=2)
        self.settings.driver(member_id=1, start_hub=1, end_hub=1, capacity=15)
        self.driver = self.settings.drivers_map[1]
        self.settings.order(1, '-37.6780953, 145.1290807', pickup_address='-37.926451, 144.998992')
        self.settings.order(2, '-37.926451, 144.998992', pickup_address='-37.926451, 144.998992')
        self.settings.order(3, '-35.5418094, 144.9643013')
        self.settings.order(4, '-37.9202176, 145.2230781')
        self.expectation = OptimisationExpectation(skipped_orders=0)

    def test_do_not_return_deleted_order(self):
        self.run_optimisation(self.settings, self.expectation)

        self.client.force_authenticate(self.driver)
        self.assert_route_points_numbers(self.get_driver_route(), {2, 3, 4, 5}, {1, 6})

        self.client.force_authenticate(self.manager)
        orders = list(self.settings.orders_map.values())
        self.delete_route_point(endpoint_base=self.orders_url, object_id=orders[0].id)

        self.client.force_authenticate(self.driver)
        self.assert_route_points_numbers(self.get_driver_route(), {2, 3, 4}, {1, 5})

    def test_do_not_return_deleted_hub(self):
        self.settings.set_end_place(hub=2)
        self.run_optimisation(self.settings, self.expectation)

        self.client.force_authenticate(self.driver)
        self.assert_route_points_numbers(self.get_driver_route(), {2, 3, 4, 5}, {1, 6})

        self.client.force_authenticate(self.manager)
        self.delete_route_point(endpoint_base=self.hubs_url, object_id=self.settings.hubs_map[2].id)

        self.client.force_authenticate(self.driver)
        self.assert_route_points_numbers(self.get_driver_route(), {2, 3, 4, 5}, {1})

    def test_unassign_order(self):
        opt_id = self.run_optimisation(self.settings, self.expectation)
        self.remove_optimisation(opt_id, unassign=True)
        opt_id = self.run_optimisation(self.settings, self.expectation)
        self.remove_optimisation(opt_id, unassign=True)
        self.run_optimisation(self.settings, self.expectation)

        self.client.force_authenticate(self.driver)
        self.assert_route_points_numbers(self.get_driver_route(), {2, 3, 4, 5}, {1, 6})

        orders = list(self.settings.orders_map.values())
        self.client.put('{url}{id}/status/'.format(url=self.orders_url, id=orders[0].id), {'status': 'not_assigned'})
        self.assert_route_points_numbers(self.get_driver_route(), {2, 3, 4}, {1, 5})

        self.client.force_authenticate(self.manager)
        self.client.patch('{url}{id}/'.format(url=self.orders_url, id=orders[1].id), {'status': 'not_assigned'})

        ro_events_count_after_unassign = 0
        get = self.client.get('/api/web/dev/new-events/')
        for e in get.json()['events']:
            if e['content_type'] == 'routeoptimisation' and e['event'] == 'model_changed' \
                    and e['obj_dump'] == {'old_values': {}, 'new_values': {}}:
                ro_events_count_after_unassign += 1
        self.assertEqual(ro_events_count_after_unassign, 2)

        self.client.force_authenticate(self.driver)
        self.assert_route_points_numbers(self.get_driver_route(), {2, 3}, {1, 4})

    def test_remove_pickup(self):
        self.merchant.use_pick_up_status = True
        self.merchant.save()
        self.run_optimisation(self.settings, self.expectation)

        self.client.force_authenticate(self.driver)
        self.assert_route_points_numbers(self.get_driver_route(), {2, 3, 4, 5}, {1, 6})

        pickups_count = self.ro_object.routes.first().points.all().filter(point_kind=RoutePointKind.PICKUP).count()
        self.assertEqual(pickups_count, 2)

        orders = list(self.settings.orders_map.values())
        self.client.force_authenticate(self.manager)
        resp = self.client.patch('{url}{id}/'.format(url=self.orders_url, id=orders[0].id), {'pickup_address': None})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(self.driver)
        self.assert_route_points_numbers(self.get_driver_route(), {2, 3, 4, 5}, {1, 6})
        pickups_count = self.ro_object.routes.first().points.all().filter(point_kind=RoutePointKind.PICKUP).count()
        self.assertEqual(pickups_count, 1)

    def get_driver_route(self):
        resp = self.get_legacy_driver_routes()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return resp.data['results'][0]

    def delete_route_point(self, endpoint_base, object_id):
        resp = self.client.delete('{url}{id}/'.format(url=endpoint_base, id=object_id))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def assert_route_points_numbers(self, driver_route, orders_numbers, hubs_numbers):
        orders, hubs = driver_route['route_points_orders'], driver_route['route_points_hubs']
        self.assertEqual(len(orders), len(orders_numbers))
        self.assertEqual(orders_numbers, set(map(itemgetter('number'), orders)))
        self.assertEqual(len(hubs), len(hubs_numbers))
        self.assertEqual(hubs_numbers, set(map(itemgetter('number'), hubs)))
