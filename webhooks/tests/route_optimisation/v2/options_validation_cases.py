from datetime import timedelta

from rest_framework import status
from rest_framework.test import APITestCase

from route_optimisation.const import OPTIMISATION_TYPES, HubOptions
from tasks.mixins.order_status import OrderStatus


class ExternalROOptionsValidationCase:
    @staticmethod
    def request(test_case: APITestCase, url, day, orders, drivers, driver_ids, hubs, merchants, skill_sets):
        raise NotImplementedError()

    @staticmethod
    def assert_response(test_case: APITestCase, resp, merchants):
        raise NotImplementedError()


class NoWorkingHours(ExternalROOptionsValidationCase):
    @staticmethod
    def request(test_case: APITestCase, url, day, orders, drivers, driver_ids, hubs, merchants, skill_sets):
        return test_case.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[_orders[0].order_id for _orders in orders.values()],
                member_ids=[_driver_ids[0] for _driver_ids in driver_ids.values()],
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=hubs[merchants[0]][0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
            ),
        ))

    @staticmethod
    def assert_response(test_case: APITestCase, resp, merchants):
        test_case.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        test_case.assertIn('This field is required', str(resp.data['errors']['options']['working_hours']))


class NoDrivers(ExternalROOptionsValidationCase):
    @staticmethod
    def request(test_case: APITestCase, url, day, orders, drivers, driver_ids, hubs, merchants, skill_sets):
        return test_case.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[_orders[0].order_id for _orders in orders.values()],
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=hubs[merchants[0]][0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))

    @staticmethod
    def assert_response(test_case: APITestCase, resp, merchants):
        test_case.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        test_case.assertIn('This field is required', str(resp.data['errors']['options']['member_ids']))


class EmptyDrivers(ExternalROOptionsValidationCase):
    @staticmethod
    def request(test_case: APITestCase, url, day, orders, drivers, driver_ids, hubs, merchants, skill_sets):
        return test_case.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(day),
            options=dict(
                re_optimise_assigned=False,
                member_ids=[],
                order_ids=[_orders[0].order_id for _orders in orders.values()],
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=hubs[merchants[0]][0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))

    @staticmethod
    def assert_response(test_case: APITestCase, resp, merchants):
        test_case.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        test_case.assertIn('No drivers passed', str(resp.data['errors']['options']['member_ids']))


class WrongDrivers(ExternalROOptionsValidationCase):
    @staticmethod
    def request(test_case: APITestCase, url, day, orders, drivers, driver_ids, hubs, merchants, skill_sets):
        return test_case.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(day),
            options=dict(
                re_optimise_assigned=False,
                member_ids=['bla'],
                order_ids=[_orders[0].order_id for _orders in orders.values()],
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=hubs[merchants[0]][0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))

    @staticmethod
    def assert_response(test_case: APITestCase, resp, merchants):
        test_case.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        test_case.assertIn('A valid integer is required', str(resp.data['errors']['options']['member_ids']))


class NonExistDriver(ExternalROOptionsValidationCase):
    @staticmethod
    def request(test_case: APITestCase, url, day, orders, drivers, driver_ids, hubs, merchants, skill_sets):
        return test_case.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(day),
            options=dict(
                re_optimise_assigned=False,
                member_ids=[123],
                order_ids=[_orders[0].order_id for _orders in orders.values()],
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=hubs[merchants[0]][0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))

    @staticmethod
    def assert_response(test_case: APITestCase, resp, merchants):
        test_case.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        test_case.assertIn('object does not exist', str(resp.data['errors']['options']['member_ids']))


class NoOrders(ExternalROOptionsValidationCase):
    @staticmethod
    def request(test_case: APITestCase, url, day, orders, drivers, driver_ids, hubs, merchants, skill_sets):
        return test_case.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(day),
            options=dict(
                re_optimise_assigned=False,
                member_ids=[_driver_ids[1] for _driver_ids in driver_ids.values()],
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))

    @staticmethod
    def assert_response(test_case: APITestCase, resp, merchants):
        test_case.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        test_case.assertIn('No orders passed', str(resp.data['errors']['options']['non_field_errors']))


class NoStartHubForMultipleMerchants(ExternalROOptionsValidationCase):
    @staticmethod
    def request(test_case: APITestCase, url, day, orders, drivers, driver_ids, hubs, merchants, skill_sets):
        return test_case.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(day),
            options=dict(
                re_optimise_assigned=False,
                member_ids=[_driver_ids[0] for _driver_ids in driver_ids.values()],
                start_place=HubOptions.EXTERNAL_START_HUB.hub_location,
                start_hub=hubs[merchants[0]][0].id,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))

    @staticmethod
    def assert_response(test_case: APITestCase, resp, merchants):
        test_case.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        if len(merchants) > 1:
            test_case.assertIn('You cannot set start hub for multiple merchants',
                               str(resp.data['errors']['options']['start_hub']))
        else:
            test_case.assertIn('No orders passed', str(resp.data['errors']['options']['non_field_errors']))


class NoDefaultHubs(ExternalROOptionsValidationCase):
    @staticmethod
    def request(test_case: APITestCase, url, day, orders, drivers, driver_ids, hubs, merchants, skill_sets):
        return test_case.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[_orders[0].order_id for _orders in orders.values()],
                member_ids=[_driver_ids[0] for _driver_ids in driver_ids.values()],
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))

    @staticmethod
    def assert_response(test_case: APITestCase, resp, merchants):
        test_case.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        test_case.assertIn('has no default start hub', str(resp.data['errors']['options']['member_ids']))


class WrongDay(ExternalROOptionsValidationCase):
    @staticmethod
    def request(test_case: APITestCase, url, day, orders, drivers, driver_ids, hubs, merchants, skill_sets):
        return test_case.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(day + timedelta(days=1)),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[_orders[0].order_id for _orders in orders.values()],
                member_ids=[_driver_ids[0] for _driver_ids in driver_ids.values()],
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))

    @staticmethod
    def assert_response(test_case: APITestCase, resp, merchants):
        test_case.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        test_case.assertIn('does not matching with the optimisation day',
                           str(resp.data['errors']['options']['order_ids']))


class NoAssignedDrivers(ExternalROOptionsValidationCase):
    @staticmethod
    def request(test_case: APITestCase, url, day, orders, drivers, driver_ids, hubs, merchants, skill_sets):
        for merchant in merchants:
            orders[merchant][0].driver = drivers[merchant][0]
            orders[merchant][0].status = OrderStatus.ASSIGNED
            orders[merchant][0].save()
        resp = test_case.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[_orders[0].order_id for _orders in orders.values()],
                member_ids=[_driver_ids[1] for _driver_ids in driver_ids.values()],
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        for merchant in merchants:
            orders[merchant][0].driver = None
            orders[merchant][0].status = OrderStatus.NOT_ASSIGNED
            orders[merchant][0].save()
        return resp

    @staticmethod
    def assert_response(test_case: APITestCase, resp, merchants):
        test_case.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        test_case.assertIn('No driver assigned to order with order_id',
                           str(resp.data['errors']['options']['order_ids'][0]))


class NoDriverWithOrderSkillSets(ExternalROOptionsValidationCase):
    @staticmethod
    def request(test_case: APITestCase, url, day, orders, drivers, driver_ids, hubs, merchants, skill_sets):
        for merchant in merchants:
            orders[merchant][0].driver = drivers[merchant][1]
            orders[merchant][0].status = OrderStatus.ASSIGNED
            orders[merchant][0].save()
            orders[merchant][0].skill_sets.set((skill_sets[merchant][0].id, ))
        resp = test_case.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[_orders[0].order_id for _orders in orders.values()],
                member_ids=[_driver_ids[1] for _driver_ids in driver_ids.values()],
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '23:00:00'},
            ),
        ))
        for merchant in merchants:
            orders[merchant][0].driver = None
            orders[merchant][0].status = OrderStatus.NOT_ASSIGNED
            orders[merchant][0].save()
            orders[merchant][0].skill_sets.clear()
        return resp

    @staticmethod
    def assert_response(test_case: APITestCase, resp, merchants):
        test_case.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        test_case.assertIn('No drivers with skills matching order',
                           str(resp.data['errors']['options']['order_ids'][0]))


class NoAvailableDrivers(ExternalROOptionsValidationCase):
    @staticmethod
    def request(test_case: APITestCase, url, day, orders, drivers, driver_ids, hubs, merchants, skill_sets):
        for merchant in merchants:
            orders[merchant][0].driver = drivers[merchant][1]
            orders[merchant][0].status = OrderStatus.ASSIGNED
            orders[merchant][0].save()
            orders[merchant][0].skill_sets.set((skill_sets[merchant][0].id, ))
            drivers[merchant][1].skill_sets.set((skill_sets[merchant][0].id, ))
        resp = test_case.client.post(url, dict(
            type=OPTIMISATION_TYPES.ADVANCED,
            day=str(day),
            options=dict(
                re_optimise_assigned=False,
                order_ids=[_orders[0].order_id for _orders in orders.values()],
                member_ids=[_driver_ids[1] for _driver_ids in driver_ids.values()],
                start_place=HubOptions.EXTERNAL_START_HUB.default_hub,
                end_place=HubOptions.EXTERNAL_END_HUB.default_hub,
                use_vehicle_capacity=True,
                working_hours={'lower': '01:00:00', 'upper': '05:00:00'},
            ),
        ))
        for merchant in merchants:
            orders[merchant][0].driver = None
            orders[merchant][0].status = OrderStatus.NOT_ASSIGNED
            orders[merchant][0].save()
            orders[merchant][0].skill_sets.clear()
            drivers[merchant][1].skill_sets.clear()
        return resp

    @staticmethod
    def assert_response(test_case: APITestCase, resp, merchants):
        test_case.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        test_case.assertIn('There are no available drivers', str(resp.data['errors']['options']['member_ids'][0]))
